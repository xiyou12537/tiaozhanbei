"""Build a globally ordered physical execution plan for virtual QPUs."""

from __future__ import annotations

import re
from collections import deque
from typing import Any


class ChipRoutingError(RuntimeError):
    """A requested virtual chip cannot host or route a partition circuit."""


_QREG = re.compile(r"qreg\s+q\[(\d+)]\s*;")
_SINGLE = re.compile(r"(x|ry\([^)]+\))\s+q\[(\d+)]\s*;")
_CX = re.compile(r"cx\s+q\[(\d+)]\s*,\s*q\[(\d+)]\s*;")


def route_partition_circuits(
    *,
    qasm_content: str,
    partitions: list[list[int]],
    virtual_node_mapping: list[dict[str, Any]],
    chips: list[dict[str, Any]],
    initial_layout_method: str,
    routing_method: str,
) -> dict[str, Any]:
    """Route the complete circuit into one globally ordered execution plan.

    Each virtual chip has a local physical address space ``0..N-1``.  Plan
    entries include layout snapshots so the simulator can reject a plan with a
    deleted SWAP rather than silently executing a different logical circuit.
    """
    if initial_layout_method != "identity":
        raise ChipRoutingError("unsupported_initial_layout_method")
    if routing_method != "shortest_path_swap":
        raise ChipRoutingError("unsupported_routing_method")

    operations = _parse_qasm(qasm_content)
    partition_for_qubit = {
        qubit: f"P{index + 1}" for index, qubits in enumerate(partitions) for qubit in qubits
    }
    assigned_node = {item["partition_id"]: item["virtual_node_id"] for item in virtual_node_mapping}
    chip_by_node = {chip["virtual_qpu_id"]: chip for chip in chips}
    if set(assigned_node.values()) != set(chip_by_node):
        raise ChipRoutingError("physical_chip_assignment_mismatch")

    states: dict[str, dict[str, Any]] = {}
    for index, logical_qubits in enumerate(partitions, start=1):
        partition_id = f"P{index}"
        node_id = assigned_node.get(partition_id)
        if node_id is None:
            raise ChipRoutingError("physical_chip_assignment_mismatch")
        chip = chip_by_node[node_id]
        physical_count = int(chip["physical_qubit_count"])
        if physical_count < len(logical_qubits):
            raise ChipRoutingError(f"physical_qubit_insufficient:{node_id}")
        adjacency = _adjacency(physical_count, chip.get("physical_coupling_map", []))
        layout = {logical: physical for physical, logical in enumerate(sorted(logical_qubits))}
        states[partition_id] = {
            "partition_id": partition_id,
            "virtual_qpu_id": node_id,
            "logical_qubits": list(logical_qubits),
            "physical_qubit_count": physical_count,
            "physical_coupling_map": _normalise_edges(chip.get("physical_coupling_map", [])),
            "adjacency": adjacency,
            "initial_layout": dict(layout),
            "layout": layout,
            "reverse_layout": {physical: logical for logical, physical in layout.items()},
            "original_operations": [],
            "routed_operations": [],
            "evidence": [],
        }

    plan: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    abstract_swap_count = 0
    original_local_two_qubit_count = 0
    routed_local_two_qubit_operation_count = 0
    cross_partition_gate_count = 0

    def append_step(
        *,
        original_gate_index: int,
        operation: str,
        scope: str,
        partition_ids: list[str],
        logical_qubits: list[int],
        physical_qubits: list[int],
        angle: float | None = None,
        physical_edge_is_valid: bool | None = None,
    ) -> dict[str, Any]:
        step = {
            "execution_index": len(plan),
            "original_gate_index": original_gate_index,
            "operation": operation,
            "scope": scope,
            "partition_ids": partition_ids,
            "virtual_qpu_ids": [states[partition_id]["virtual_qpu_id"] for partition_id in partition_ids],
            "logical_qubits": logical_qubits,
            "physical_qubits": physical_qubits,
            "physical_edge_is_valid": physical_edge_is_valid,
            "logical_to_physical_layout_before": _all_layouts(states),
            "logical_to_physical_layout_after": None,
        }
        if angle is not None:
            step["angle"] = angle
        plan.append(step)
        return step

    for gate_index, operation in enumerate(operations):
        logical_qubits = operation["qubits"]
        source_partition = partition_for_qubit[logical_qubits[0]]
        target_partition = partition_for_qubit[logical_qubits[-1]]
        if operation["gate"] != "cx" or source_partition == target_partition:
            state = states[source_partition]
            state["original_operations"].append(operation)
            if operation["gate"] != "cx":
                physical = state["layout"][logical_qubits[0]]
                step = append_step(
                    original_gate_index=gate_index,
                    operation=operation["gate"],
                    scope="intra_qpu",
                    partition_ids=[source_partition],
                    logical_qubits=logical_qubits,
                    physical_qubits=[physical],
                    angle=operation.get("angle"),
                )
                state["routed_operations"].append(step)
                step["logical_to_physical_layout_after"] = _all_layouts(states)
                continue

            original_local_two_qubit_count += 1
            control, target = logical_qubits
            control_physical, target_physical = state["layout"][control], state["layout"][target]
            path = _shortest_path(state["adjacency"], control_physical, target_physical)
            if path is None:
                raise ChipRoutingError(f"physical_coupling_disconnected:{state['virtual_qpu_id']}")
            swap_positions: list[int] = []
            swap_path: list[list[int]] = []
            for source, destination in zip(path[:-2], path[1:-1]):
                step = append_step(
                    original_gate_index=gate_index,
                    operation="swap",
                    scope="intra_qpu",
                    partition_ids=[source_partition],
                    logical_qubits=[
                        state["reverse_layout"].get(source, -1),
                        state["reverse_layout"].get(destination, -1),
                    ],
                    physical_qubits=[source, destination],
                    physical_edge_is_valid=destination in state["adjacency"][source],
                )
                swap_positions.append(step["execution_index"])
                swap_path.append([source, destination])
                _swap_layout(state["layout"], state["reverse_layout"], source, destination)
                step["logical_to_physical_layout_after"] = _all_layouts(states)
                state["routed_operations"].append(step)
                abstract_swap_count += 1
                routed_local_two_qubit_operation_count += 1
            final_control, final_target = state["layout"][control], state["layout"][target]
            valid_edge = final_target in state["adjacency"][final_control]
            if not valid_edge:
                raise ChipRoutingError(f"physical_coupling_disconnected:{state['virtual_qpu_id']}")
            step = append_step(
                original_gate_index=gate_index,
                operation="cx",
                scope="intra_qpu",
                partition_ids=[source_partition],
                logical_qubits=[control, target],
                physical_qubits=[final_control, final_target],
                physical_edge_is_valid=True,
            )
            step["logical_to_physical_layout_after"] = _all_layouts(states)
            state["routed_operations"].append(step)
            routed_local_two_qubit_operation_count += 1
            item = {
                "partition_id": source_partition,
                "virtual_qpu_id": state["virtual_qpu_id"],
                "gate_index": gate_index,
                "gate": "cx",
                "logical_qubits": [control, target],
                "initial_physical_qubits": [control_physical, target_physical],
                "final_physical_qubits": [final_control, final_target],
                "routing_status": "direct" if not swap_positions else "routed",
                "path": path,
                "swap_positions": swap_positions,
                "swap_path": swap_path,
            }
            state["evidence"].append(item)
            evidence.append(item)
            continue

        cross_partition_gate_count += 1
        physical_locations = [
            states[source_partition]["layout"][logical_qubits[0]],
            states[target_partition]["layout"][logical_qubits[1]],
        ]
        step = append_step(
            original_gate_index=gate_index,
            operation="cx",
            scope="inter_qpu",
            partition_ids=[source_partition, target_partition],
            logical_qubits=logical_qubits,
            physical_qubits=physical_locations,
        )
        step["logical_to_physical_layout_after"] = _all_layouts(states)

    partition_chip_routing = []
    for state in states.values():
        partition_chip_routing.append(
            {
                "partition_id": state["partition_id"],
                "virtual_qpu_id": state["virtual_qpu_id"],
                "logical_qubits": state["logical_qubits"],
                "physical_qubit_count": state["physical_qubit_count"],
                "physical_coupling_map": state["physical_coupling_map"],
                "logical_to_physical_initial": _layout_rows(state["initial_layout"]),
                "logical_to_physical_final": _layout_rows(state["layout"]),
                "original_operation_count": len(state["original_operations"]),
                "routed_operation_count": len(state["routed_operations"]),
                "original_two_qubit_operation_count": len(state["evidence"]),
                "routed_two_qubit_operation_count": sum(
                    item["operation"] in {"swap", "cx"} for item in state["routed_operations"]
                ),
                "routed_gate_sequence": [
                    {"gate": item["operation"], "physical_qubits": item["physical_qubits"]}
                    for item in state["routed_operations"]
                ],
                "two_qubit_routing_evidence": state["evidence"],
            }
        )
    return {
        "partition_chip_routing": partition_chip_routing,
        "two_qubit_routing_evidence": evidence,
        "routed_execution_plan": plan,
        "original_two_qubit_operation_count": original_local_two_qubit_count,
        "routed_two_qubit_operation_count": routed_local_two_qubit_operation_count,
        "cross_partition_gate_count": cross_partition_gate_count,
        "intra_chip_routing_cost": {
            "abstract_swap_count": abstract_swap_count,
            "routed_two_qubit_operation_count": routed_local_two_qubit_operation_count,
            "native_two_qubit_gate_equivalent_count": original_local_two_qubit_count + 3 * abstract_swap_count,
        },
    }


def _parse_qasm(qasm_content: str) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for raw_line in qasm_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("OPENQASM", "include", "//")) or _QREG.fullmatch(line):
            continue
        cx = _CX.fullmatch(line)
        if cx:
            operations.append({"gate": "cx", "qubits": [int(cx.group(1)), int(cx.group(2))]})
            continue
        single = _SINGLE.fullmatch(line)
        if single:
            gate = single.group(1)
            angle = float(gate[3:-1]) if gate.startswith("ry(") else None
            operations.append({"gate": "ry" if angle is not None else gate, "qubits": [int(single.group(2))], "angle": angle})
            continue
        raise ChipRoutingError(f"unsupported_qasm_for_routing:{line}")
    return operations


def _normalise_edges(edges: list[dict[str, int]]) -> list[dict[str, int]]:
    return [{"source": int(edge["source"]), "target": int(edge["target"])} for edge in edges]


def _adjacency(physical_count: int, edges: list[dict[str, int]]) -> dict[int, set[int]]:
    adjacency = {index: set() for index in range(physical_count)}
    for edge in edges:
        source, target = int(edge["source"]), int(edge["target"])
        if source == target or source not in adjacency or target not in adjacency:
            raise ChipRoutingError("invalid_physical_coupling_map")
        adjacency[source].add(target)
        adjacency[target].add(source)
    return adjacency


def _shortest_path(adjacency: dict[int, set[int]], source: int, target: int) -> list[int] | None:
    queue: deque[list[int]] = deque([[source]])
    visited = {source}
    while queue:
        path = queue.popleft()
        if path[-1] == target:
            return path
        for neighbor in sorted(adjacency[path[-1]]):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append([*path, neighbor])
    return None


def _swap_layout(layout: dict[int, int], reverse_layout: dict[int, int], source: int, target: int) -> None:
    source_logical, target_logical = reverse_layout.get(source), reverse_layout.get(target)
    if source_logical is not None:
        layout[source_logical] = target
        reverse_layout[target] = source_logical
    else:
        reverse_layout.pop(target, None)
    if target_logical is not None:
        layout[target_logical] = source
        reverse_layout[source] = target_logical
    else:
        reverse_layout.pop(source, None)


def _layout_rows(layout: dict[int, int]) -> list[dict[str, int]]:
    return [{"logical_qubit": logical, "physical_qubit": physical} for logical, physical in sorted(layout.items())]


def _all_layouts(states: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, int]]]:
    return {partition_id: _layout_rows(state["layout"]) for partition_id, state in sorted(states.items())}
