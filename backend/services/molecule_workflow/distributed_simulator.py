from __future__ import annotations

import math
import re
from typing import Any

import numpy as np


class DistributedSimulationError(RuntimeError):
    """Raised when a partitioned logical simulation plan is incomplete or invalid."""


class LogicalVirtualQPUSimulator:
    """Execute an Ry-CX circuit as a tensor ordered by mapped virtual QPU nodes.

    This is an exact logical simulator, not hardware execution.  The partition and
    virtual-node mapping determine tensor-axis placement, gate locality and every
    recorded cross-node contraction.  Energy is evaluated from the resulting
    partition-aware tensor rather than copied from an unpartitioned execution.
    """

    _RY_PATTERN = re.compile(r"ry\(([^)]+)\)\s+q\[(\d+)]\s*;")
    _RZ_PATTERN = re.compile(r"rz\(([^)]+)\)\s+q\[(\d+)]\s*;")
    _X_PATTERN = re.compile(r"x\s+q\[(\d+)]\s*;")
    _H_PATTERN = re.compile(r"h\s+q\[(\d+)]\s*;")
    _S_PATTERN = re.compile(r"s\s+q\[(\d+)]\s*;")
    _SDG_PATTERN = re.compile(r"sdg\s+q\[(\d+)]\s*;")
    _CX_PATTERN = re.compile(r"cx\s+q\[(\d+)]\s*,\s*q\[(\d+)]\s*;")

    def execute(
        self,
        *,
        qasm_content: str | None = None,
        routed_execution_plan: list[dict[str, Any]] | None = None,
        qubit_count: int,
        pauli_terms: list[dict[str, Any]],
        partitions: list[list[int]],
        virtual_node_mapping: list[dict[str, Any]],
    ) -> dict[str, Any]:
        qubit_to_partition, partition_to_node, axis_order = self._validate_plan(
            qubit_count,
            partitions,
            virtual_node_mapping,
        )
        state = np.zeros((2,) * qubit_count, dtype=complex)
        state[(0,) * qubit_count] = 1.0
        qubit_to_axis = {qubit: axis for axis, qubit in enumerate(axis_order)}
        if routed_execution_plan is not None:
            execution = self._execute_routed_plan(
                state=state,
                qubit_to_axis=qubit_to_axis,
                routed_execution_plan=routed_execution_plan,
                partition_to_node=partition_to_node,
            )
            state = execution["state"]
            communication_events = execution["communication_events"]
            local_gate_count = execution["local_gate_count"]
            actual_routed_plan_consumption = True
            final_layouts = execution["final_layouts"]
        else:
            if qasm_content is None:
                raise DistributedSimulationError("A QASM circuit or routed execution plan is required.")
            operations = self._parse_qasm(qasm_content, qubit_count)
            communication_events = []
            local_gate_count = 0
            actual_routed_plan_consumption = False
            final_layouts = None
        for gate_index, operation in enumerate(operations if routed_execution_plan is None else []):
            if operation["gate"] in {"x", "h", "s", "sdg", "ry", "rz"}:
                qubit = operation["qubits"][0]
                state = self._apply_matrix(state, self._single_qubit_matrix(operation["gate"], operation.get("angle")), [qubit_to_axis[qubit]])
                local_gate_count += 1
                continue

            control, target = operation["qubits"]
            control_partition = qubit_to_partition[control]
            target_partition = qubit_to_partition[target]
            if control_partition == target_partition:
                local_gate_count += 1
            else:
                communication_events.append(
                    {
                        "gate_index": gate_index,
                        "gate": "cx",
                        "control_qubit": control,
                        "target_qubit": target,
                        "source_partition_id": control_partition,
                        "target_partition_id": target_partition,
                        "source_virtual_node_id": partition_to_node[control_partition],
                        "target_virtual_node_id": partition_to_node[target_partition],
                    }
                )
            cx_matrix = np.asarray(
                [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
                dtype=complex,
            )
            state = self._apply_matrix(
                state,
                cx_matrix,
                [qubit_to_axis[control], qubit_to_axis[target]],
            )

        energy, term_expectations = self._evaluate_energy(
            state,
            pauli_terms,
            qubit_to_axis,
        )
        return {
            "energy_hartree": energy,
            "cross_partition_communication_count": len(communication_events),
            "communication_events": communication_events,
            "local_gate_count": local_gate_count,
            "state_norm": float(np.vdot(state.reshape(-1), state.reshape(-1)).real),
            "term_expectations": term_expectations,
            "axis_order_by_virtual_node": axis_order,
            "actual_partition_consumption": True,
            "actual_routed_plan_consumption": actual_routed_plan_consumption,
            "final_logical_to_physical_layout": final_layouts,
            "simulation_strategy": "mapped_partition_tensor_contraction",
        }

    def _execute_routed_plan(
        self,
        *,
        state: np.ndarray,
        qubit_to_axis: dict[int, int],
        routed_execution_plan: list[dict[str, Any]],
        partition_to_node: dict[str, str],
    ) -> dict[str, Any]:
        if not routed_execution_plan:
            raise DistributedSimulationError("routed_execution_plan is empty")
        current_layouts = self._normalise_layouts(routed_execution_plan[0].get("logical_to_physical_layout_before"))
        communication_events: list[dict[str, Any]] = []
        local_gate_count = 0
        for expected_index, step in enumerate(routed_execution_plan):
            if step.get("execution_index") != expected_index:
                raise DistributedSimulationError("routed_execution_plan_execution_index_mismatch")
            before = self._normalise_layouts(step.get("logical_to_physical_layout_before"))
            if before != current_layouts:
                raise DistributedSimulationError("routed_execution_plan_layout_mismatch")
            operation = step.get("operation")
            logical_qubits = step.get("logical_qubits", [])
            physical_qubits = step.get("physical_qubits", [])
            partition_ids = step.get("partition_ids", [])
            if operation == "swap":
                if len(partition_ids) != 1 or len(physical_qubits) != 2:
                    raise DistributedSimulationError("routed_execution_plan_invalid_swap")
                self._swap_layout(current_layouts[partition_ids[0]], physical_qubits[0], physical_qubits[1])
                local_gate_count += 1
            elif operation in {"x", "h", "s", "sdg", "ry", "rz", "cx"} and step.get("scope") == "intra_qpu":
                if len(partition_ids) != 1:
                    raise DistributedSimulationError("routed_execution_plan_invalid_intra_qpu_gate")
                layout = current_layouts[partition_ids[0]]
                reverse_layout = {physical: logical for logical, physical in layout.items()}
                resolved_logical = [reverse_layout.get(physical) for physical in physical_qubits]
                if None in resolved_logical or resolved_logical != logical_qubits:
                    raise DistributedSimulationError("routed_execution_plan_layout_mismatch")
                if operation != "cx":
                    state = self._apply_matrix(state, self._single_qubit_matrix(operation, step.get("angle")), [qubit_to_axis[logical_qubits[0]]])
                else:
                    if step.get("physical_edge_is_valid") is not True:
                        raise DistributedSimulationError("routed_execution_plan_invalid_physical_edge")
                    state = self._apply_cx(state, qubit_to_axis, logical_qubits)
                local_gate_count += 1
            elif operation == "cx" and step.get("scope") == "inter_qpu":
                if len(partition_ids) != 2 or len(logical_qubits) != 2:
                    raise DistributedSimulationError("routed_execution_plan_invalid_inter_qpu_gate")
                communication_events.append(
                    {
                        "gate_index": step["original_gate_index"],
                        "gate": "cx",
                        "control_qubit": logical_qubits[0],
                        "target_qubit": logical_qubits[1],
                        "source_partition_id": partition_ids[0],
                        "target_partition_id": partition_ids[1],
                        "source_virtual_node_id": partition_to_node[partition_ids[0]],
                        "target_virtual_node_id": partition_to_node[partition_ids[1]],
                    }
                )
                state = self._apply_cx(state, qubit_to_axis, logical_qubits)
            else:
                raise DistributedSimulationError("routed_execution_plan_unsupported_operation")
            after = self._normalise_layouts(step.get("logical_to_physical_layout_after"))
            if after != current_layouts:
                raise DistributedSimulationError("routed_execution_plan_layout_mismatch")
        return {
            "state": state,
            "communication_events": communication_events,
            "local_gate_count": local_gate_count,
            "final_layouts": {
                partition_id: [
                    {"logical_qubit": logical, "physical_qubit": physical}
                    for logical, physical in sorted(layout.items())
                ]
                for partition_id, layout in sorted(current_layouts.items())
            },
        }

    @staticmethod
    def _single_qubit_matrix(operation: str, angle: float | None = None) -> np.ndarray:
        if operation == "x": return np.asarray([[0, 1], [1, 0]], dtype=complex)
        if operation == "h": return np.asarray([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2.0)
        if operation == "s": return np.asarray([[1, 0], [0, 1j]], dtype=complex)
        if operation == "sdg": return np.asarray([[1, 0], [0, -1j]], dtype=complex)
        if operation == "ry":
            value = float(angle); return np.asarray([[math.cos(value / 2), -math.sin(value / 2)], [math.sin(value / 2), math.cos(value / 2)]], dtype=complex)
        if operation == "rz":
            value = float(angle); return np.asarray([[np.exp(-0.5j * value), 0], [0, np.exp(0.5j * value)]], dtype=complex)
        raise DistributedSimulationError("routed_execution_plan_unsupported_operation")

    @staticmethod
    def _normalise_layouts(value: Any) -> dict[str, dict[int, int]]:
        if not isinstance(value, dict):
            raise DistributedSimulationError("routed_execution_plan_missing_layout")
        try:
            return {
                str(partition_id): {int(row["logical_qubit"]): int(row["physical_qubit"]) for row in rows}
                for partition_id, rows in value.items()
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise DistributedSimulationError("routed_execution_plan_invalid_layout") from exc

    @staticmethod
    def _swap_layout(layout: dict[int, int], source: int, target: int) -> None:
        reverse_layout = {physical: logical for logical, physical in layout.items()}
        source_logical, target_logical = reverse_layout.get(source), reverse_layout.get(target)
        if source_logical is not None:
            layout[source_logical] = target
        if target_logical is not None:
            layout[target_logical] = source

    def _apply_cx(self, state: np.ndarray, qubit_to_axis: dict[int, int], qubits: list[int]) -> np.ndarray:
        matrix = np.asarray([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex)
        return self._apply_matrix(state, matrix, [qubit_to_axis[qubits[0]], qubit_to_axis[qubits[1]]])

    @staticmethod
    def _validate_plan(
        qubit_count: int,
        partitions: list[list[int]],
        virtual_node_mapping: list[dict[str, Any]],
    ) -> tuple[dict[int, str], dict[str, str], list[int]]:
        qubit_to_partition: dict[int, str] = {}
        partition_qubits: dict[str, list[int]] = {}
        for partition_index, qubits in enumerate(partitions, start=1):
            partition_id = f"P{partition_index}"
            partition_qubits[partition_id] = list(qubits)
            for qubit in qubits:
                if qubit in qubit_to_partition:
                    raise DistributedSimulationError(f"量子比特 {qubit} 被重复分配到多个分区。")
                qubit_to_partition[qubit] = partition_id
        if set(qubit_to_partition) != set(range(qubit_count)):
            raise DistributedSimulationError("分区方案必须且只能覆盖全部映射后量子比特。")

        partition_to_node: dict[str, str] = {}
        for assignment in virtual_node_mapping:
            partition_id = assignment["partition_id"]
            virtual_node_id = assignment["virtual_node_id"]
            if partition_id in partition_to_node:
                raise DistributedSimulationError(f"分区 {partition_id} 被重复映射。")
            if assignment.get("qubits") != partition_qubits.get(partition_id):
                raise DistributedSimulationError(f"虚拟节点 {virtual_node_id} 的量子比特与分区方案不一致。")
            partition_to_node[partition_id] = virtual_node_id
        if set(partition_to_node) != set(partition_qubits):
            raise DistributedSimulationError("每个逻辑分区都必须映射到一个虚拟 QPU 节点。")

        axis_order: list[int] = []
        for assignment in sorted(virtual_node_mapping, key=lambda item: item["virtual_node_id"]):
            axis_order.extend(sorted(assignment["qubits"]))
        return qubit_to_partition, partition_to_node, axis_order

    def _parse_qasm(self, qasm_content: str, qubit_count: int) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        declared_qubits: int | None = None
        for raw_line in qasm_content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("OPENQASM") or line.startswith("include"):
                continue
            register_match = re.fullmatch(r"qreg\s+q\[(\d+)]\s*;", line)
            if register_match:
                declared_qubits = int(register_match.group(1))
                continue
            ry_match = self._RY_PATTERN.fullmatch(line)
            if ry_match:
                operations.append(
                    {
                        "gate": "ry",
                        "angle": float(ry_match.group(1)),
                        "qubits": [int(ry_match.group(2))],
                    }
                )
                continue
            rz_match = self._RZ_PATTERN.fullmatch(line)
            if rz_match:
                operations.append({"gate": "rz", "angle": float(rz_match.group(1)), "qubits": [int(rz_match.group(2))]})
                continue
            x_match = self._X_PATTERN.fullmatch(line)
            if x_match:
                operations.append({"gate": "x", "qubits": [int(x_match.group(1))]})
                continue
            matched_single = False
            for gate, pattern in (("h", self._H_PATTERN), ("s", self._S_PATTERN), ("sdg", self._SDG_PATTERN)):
                single_match = pattern.fullmatch(line)
                if single_match:
                    operations.append({"gate": gate, "qubits": [int(single_match.group(1))]})
                    matched_single = True
                    break
            if matched_single:
                continue
            cx_match = self._CX_PATTERN.fullmatch(line)
            if cx_match:
                operations.append(
                    {
                        "gate": "cx",
                        "qubits": [int(cx_match.group(1)), int(cx_match.group(2))],
                    }
                )
                continue
            raise DistributedSimulationError(f"logical_virtual_qpu 暂不支持 QASM 语句：{line}")
        if declared_qubits != qubit_count:
            raise DistributedSimulationError("QASM 量子寄存器规模与 Hamiltonian 不一致。")
        return operations

    @staticmethod
    def _apply_matrix(state: np.ndarray, matrix: np.ndarray, axes: list[int]) -> np.ndarray:
        moved = np.moveaxis(state, axes, list(range(len(axes))))
        updated = matrix @ moved.reshape(1 << len(axes), -1)
        restored = updated.reshape(moved.shape)
        return np.moveaxis(restored, list(range(len(axes))), axes)

    def _evaluate_energy(
        self,
        state: np.ndarray,
        pauli_terms: list[dict[str, Any]],
        qubit_to_axis: dict[int, int],
    ) -> tuple[float, list[dict[str, Any]]]:
        pauli_matrices = {
            "X": np.asarray([[0, 1], [1, 0]], dtype=complex),
            "Y": np.asarray([[0, -1j], [1j, 0]], dtype=complex),
            "Z": np.asarray([[1, 0], [0, -1]], dtype=complex),
        }
        energy = 0.0
        expectations: list[dict[str, Any]] = []
        flattened_state = state.reshape(-1)
        for term in pauli_terms:
            transformed = state
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split():
                    gate = token[0]
                    qubit = int(token[1:])
                    if gate not in pauli_matrices or qubit not in qubit_to_axis:
                        raise DistributedSimulationError(f"无效 Pauli 项：{term['pauli_string']}")
                    transformed = self._apply_matrix(
                        transformed,
                        pauli_matrices[gate],
                        [qubit_to_axis[qubit]],
                    )
            expectation = float(np.vdot(flattened_state, transformed.reshape(-1)).real)
            contribution = float(term["coefficient"]) * expectation
            energy += contribution
            expectations.append(
                {
                    "pauli_string": term["pauli_string"],
                    "expectation_value": expectation,
                    "energy_contribution_hartree": contribution,
                }
            )
        return float(energy), expectations
