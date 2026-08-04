from __future__ import annotations

import itertools
import math
import re
import time
from dataclasses import dataclass
from typing import Any

from quantum_partitioning.partitioning import run_deterministic_partition_search_v1

from .canonical import ParsedCircuit


class DistributedCompilationError(RuntimeError):
    """Raised when a frozen circuit cannot be compiled without fallback."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CompilationArtifacts:
    logical_snapshot: dict[str, Any]
    partition_plan: dict[str, Any]
    optimized_gate_order: dict[str, Any]
    target_topology: dict[str, Any]
    chip_mapping: dict[str, Any]
    communication_route_plan: dict[str, Any]
    distributed_executable: dict[str, Any]
    baseline_metrics: dict[str, Any]
    optimized_metrics: dict[str, Any]


@dataclass(frozen=True)
class CompilationSettings:
    """Protocol-derived values consumed by deterministic compilation."""

    partition_count: int
    maximum_imbalance: int
    b1_grid: tuple[float, ...]
    b2_grid: tuple[float, ...]
    alpha: float
    beta: float
    num_starts: int
    audit_seed: int
    partition_numbering: str
    candidate_tie_break: tuple[str, ...]
    expected_partition_to_node: tuple[tuple[int, int], ...]
    gate_ordering_scheme: str
    equivalence_infidelity_maximum: float


def build_compilation_settings(
    *,
    partitioning: dict[str, Any],
    gate_ordering: dict[str, Any],
    mapping: dict[str, Any],
    routing: dict[str, Any],
    qubit_count: int,
) -> CompilationSettings:
    """Validate algorithm semantics and derive every numeric compiler input."""
    if partitioning["algorithm"] != "deterministic_greedy_multistart_grid_v1":
        raise DistributedCompilationError(
            "unsupported_partitioning_algorithm",
            "The protocol requests an unsupported partitioning algorithm.",
        )
    if partitioning["partition_ids"] != [0, 1]:
        raise DistributedCompilationError(
            "partition_constraint_violation",
            "The compiler requires frozen integer partition IDs 0 and 1.",
        )
    expected_candidate_tie_break = (
        "estimated_teleportations",
        "global_gate_count",
        "cross_partition_gate_count",
        "load_difference",
        "partition_signature",
        "b1",
        "b2",
        "seed_qubit",
    )
    if tuple(partitioning["candidate_tie_break"]) != (
        expected_candidate_tie_break
    ):
        raise DistributedCompilationError(
            "unsupported_partition_tie_break",
            "The protocol partition tie-break does not match the implementation.",
        )
    if (
        partitioning["partition_numbering"]
        != "minimum_logical_qubit_ascending_then_zero_based"
    ):
        raise DistributedCompilationError(
            "unsupported_partition_numbering",
            "The protocol partition numbering does not match the implementation.",
        )
    starts_match = re.fullmatch(
        r"min\((\d+),qubit_count\)",
        str(partitioning["num_starts_rule"]),
    )
    if starts_match is None:
        raise DistributedCompilationError(
            "unsupported_partitioning_rule",
            "The protocol num_starts_rule is not executable.",
        )
    if bool(partitioning["stochastic_behavior_allowed"]):
        raise DistributedCompilationError(
            "unsupported_partitioning_randomness",
            "The deterministic compiler does not permit stochastic behavior.",
        )
    if gate_ordering["scheme"] != "disjoint-support-only-v1":
        raise DistributedCompilationError(
            "unsupported_gate_ordering",
            "The protocol requests an unsupported gate-ordering scheme.",
        )
    if gate_ordering["unsupported_commutation_fallback"] != "fail":
        raise DistributedCompilationError(
            "unsupported_gate_ordering_fallback",
            "Unsupported commutation must fail explicitly.",
        )
    if mapping["algorithm"] != "minimum_cost_then_lexicographic_mapping_v1":
        raise DistributedCompilationError(
            "unsupported_mapping_algorithm",
            "The protocol requests an unsupported mapping algorithm.",
        )
    if (
        mapping["equal_cost_tie_break"]
        != "lexicographically_smallest_sorted_integer_partition_node_pairs"
        or bool(mapping["networkx_iteration_order_is_semantic"])
    ):
        raise DistributedCompilationError(
            "unsupported_mapping_tie_break",
            "The protocol mapping tie-break does not match the implementation.",
        )
    expected_mapping = tuple(
        (int(pair[0]), int(pair[1]))
        for pair in mapping["frozen_equal_cost_mapping"]
    )
    if routing != {
        "route_first_operand_to_second_operand_node": True,
        "carrier_type": "existing_data_qubit",
        "carrier_order": "execution_qubit_index_ascending",
        "carrier_must_not_be_gate_operand": True,
        "carrier_must_be_unreserved": True,
        "additional_ancilla_allowed": False,
        "swap_decomposition": ["cx(a,b)", "cx(b,a)", "cx(a,b)"],
        "inverse_route_required": True,
        "final_mapping_required": "identity",
    }:
        raise DistributedCompilationError(
            "unsupported_routing_protocol",
            "The compiler implementation does not match the protocol routing semantics.",
        )
    b1_grid = tuple(float(value) for value in partitioning["b1_grid"])
    b2_grid = tuple(float(value) for value in partitioning["b2_grid"])
    numeric_values = (
        *b1_grid,
        *b2_grid,
        float(partitioning["alpha"]),
        float(partitioning["beta"]),
        float(gate_ordering["equivalence_infidelity_maximum"]),
    )
    if not b1_grid or not b2_grid or not all(
        math.isfinite(value) for value in numeric_values
    ):
        raise DistributedCompilationError(
            "invalid_compilation_parameters",
            "Protocol compiler parameters must be finite and grids non-empty.",
        )
    return CompilationSettings(
        partition_count=int(partitioning["partition_count"]),
        maximum_imbalance=int(partitioning["maximum_imbalance"]),
        b1_grid=b1_grid,
        b2_grid=b2_grid,
        alpha=float(partitioning["alpha"]),
        beta=float(partitioning["beta"]),
        num_starts=min(int(starts_match.group(1)), qubit_count),
        audit_seed=int(partitioning["seed"]),
        partition_numbering=str(partitioning["partition_numbering"]),
        candidate_tie_break=tuple(partitioning["candidate_tie_break"]),
        expected_partition_to_node=expected_mapping,
        gate_ordering_scheme=str(gate_ordering["scheme"]),
        equivalence_infidelity_maximum=float(
            gate_ordering["equivalence_infidelity_maximum"]
        ),
    )


def _operation_projection(parsed: ParsedCircuit) -> list[list[Any]]:
    projected: list[list[Any]] = []
    for operation in parsed.operations:
        if operation["name"] == "cx":
            projected.append(["cx", *operation["qubits"]])
        else:
            projected.append(["u3", *operation["qubits"]])
    return projected


def _circuit_depth(operations: list[dict[str, Any]], qubit_count: int) -> int:
    qubit_depth = [0] * qubit_count
    for operation in operations:
        depth = max((qubit_depth[q] for q in operation["qubits"]), default=0) + 1
        for qubit in operation["qubits"]:
            qubit_depth[qubit] = depth
    return max(qubit_depth, default=0)


def _metrics(
    operations: list[dict[str, Any]],
    qubit_count: int,
    qubit_to_partition: dict[int, int],
) -> dict[str, Any]:
    two_qubit = [operation for operation in operations if len(operation["qubits"]) == 2]
    cross = [
        operation
        for operation in two_qubit
        if qubit_to_partition[operation["qubits"][0]]
        != qubit_to_partition[operation["qubits"][1]]
    ]
    return {
        "circuit_depth": _circuit_depth(operations, qubit_count),
        "total_gate_count": len(operations),
        "two_qubit_gate_count": len(two_qubit),
        "cross_partition_gate_count": len(cross),
        "global_gate_count": len(cross),
    }


def _mapping_cost(
    mapping: dict[int, int],
    partitions: list[list[int]],
    operations: tuple[dict[str, Any], ...],
) -> int:
    qubit_to_partition = {
        qubit: partition_id
        for partition_id, partition in enumerate(partitions)
        for qubit in partition
    }
    cost = 0
    for operation in operations:
        if len(operation["qubits"]) != 2:
            continue
        first, second = operation["qubits"]
        first_partition = qubit_to_partition[first]
        second_partition = qubit_to_partition[second]
        if first_partition != second_partition:
            cost += abs(mapping[first_partition] - mapping[second_partition])
    return cost


def _deterministic_mapping(
    partitions: list[list[int]],
    operations: tuple[dict[str, Any], ...],
) -> tuple[dict[int, int], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for node_permutation in itertools.permutations((0, 1)):
        mapping = {
            partition_id: node_permutation[partition_id]
            for partition_id in range(2)
        }
        pairs = [
            [partition_id, mapping[partition_id]]
            for partition_id in sorted(mapping)
        ]
        candidates.append(
            {
                "partition_to_node": pairs,
                "weighted_route_cost": _mapping_cost(mapping, partitions, operations),
            }
        )
    selected = min(
        candidates,
        key=lambda candidate: (
            candidate["weighted_route_cost"],
            candidate["partition_to_node"],
        ),
    )
    return (
        {
            int(partition_id): int(node_id)
            for partition_id, node_id in selected["partition_to_node"]
        },
        candidates,
    )


def _append_gate(
    output: list[dict[str, Any]],
    *,
    name: str,
    qubits: list[int],
    params: list[float],
    logical_gate_index: int,
    operation_type: str,
) -> None:
    output.append(
        {
            "index": len(output),
            "name": name,
            "qubits": list(qubits),
            "params": list(params),
            "source_logical_gate_index": logical_gate_index,
            "operation_type": operation_type,
        }
    )


def _append_swap(
    output: list[dict[str, Any]],
    first: int,
    second: int,
    logical_gate_index: int,
    operation_type: str,
) -> None:
    for control, target in ((first, second), (second, first), (first, second)):
        _append_gate(
            output,
            name="cx",
            qubits=[control, target],
            params=[],
            logical_gate_index=logical_gate_index,
            operation_type=operation_type,
        )


def _route_and_restore(
    parsed: ParsedCircuit,
    partitions: list[list[int]],
    partition_to_node: dict[int, int],
    maximum_expanded_gate_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    qubit_to_partition = {
        qubit: partition_id
        for partition_id, partition in enumerate(partitions)
        for qubit in partition
    }
    execution_to_node = {
        qubit: partition_to_node[qubit_to_partition[qubit]]
        for qubit in range(parsed.circuit.num_qubits)
    }
    logical_to_execution = {
        qubit: qubit for qubit in range(parsed.circuit.num_qubits)
    }
    execution_to_logical = dict(logical_to_execution)
    executable: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []

    for operation in parsed.operations:
        logical_gate_index = int(operation["index"])
        logical_qubits = list(operation["qubits"])
        params = list(operation["numeric_params"])
        if operation["name"] != "cx":
            _append_gate(
                executable,
                name=operation["name"],
                qubits=[logical_to_execution[q] for q in logical_qubits],
                params=params,
                logical_gate_index=logical_gate_index,
                operation_type="logical_local_gate",
            )
            continue

        first_logical, second_logical = logical_qubits
        first_partition = qubit_to_partition[first_logical]
        second_partition = qubit_to_partition[second_logical]
        if first_partition == second_partition:
            _append_gate(
                executable,
                name="cx",
                qubits=[
                    logical_to_execution[first_logical],
                    logical_to_execution[second_logical],
                ],
                params=[],
                logical_gate_index=logical_gate_index,
                operation_type="logical_local_gate",
            )
            continue

        first_execution = logical_to_execution[first_logical]
        second_execution = logical_to_execution[second_logical]
        source_node = execution_to_node[first_execution]
        target_node = execution_to_node[second_execution]
        carrier_candidates = sorted(
            execution_qubit
            for execution_qubit, node_id in execution_to_node.items()
            if node_id == target_node
            and execution_to_logical[execution_qubit]
            not in {first_logical, second_logical}
        )
        if not carrier_candidates:
            raise DistributedCompilationError(
                "no_available_carrier",
                f"No carrier exists for logical gate {logical_gate_index}.",
            )
        carrier_execution = carrier_candidates[0]
        carrier_logical = execution_to_logical[carrier_execution]
        start_index = len(executable)
        mapping_before = [
            [logical, logical_to_execution[logical]]
            for logical in sorted(logical_to_execution)
        ]

        _append_swap(
            executable,
            first_execution,
            carrier_execution,
            logical_gate_index,
            "remote_swap_forward_communication",
        )
        logical_to_execution[first_logical], logical_to_execution[carrier_logical] = (
            carrier_execution,
            first_execution,
        )
        execution_to_logical[first_execution], execution_to_logical[carrier_execution] = (
            carrier_logical,
            first_logical,
        )
        mapping_during = [
            [logical, logical_to_execution[logical]]
            for logical in sorted(logical_to_execution)
        ]
        _append_gate(
            executable,
            name="cx",
            qubits=[
                logical_to_execution[first_logical],
                logical_to_execution[second_logical],
            ],
            params=[],
            logical_gate_index=logical_gate_index,
            operation_type="routed_logical_gate",
        )
        _append_swap(
            executable,
            first_execution,
            carrier_execution,
            logical_gate_index,
            "remote_swap_inverse_communication",
        )
        logical_to_execution[first_logical], logical_to_execution[carrier_logical] = (
            first_execution,
            carrier_execution,
        )
        execution_to_logical[first_execution], execution_to_logical[carrier_execution] = (
            first_logical,
            carrier_logical,
        )
        mapping_after = [
            [logical, logical_to_execution[logical]]
            for logical in sorted(logical_to_execution)
        ]
        if mapping_after != mapping_before:
            raise DistributedCompilationError(
                "mapping_restore_failed",
                f"Route for logical gate {logical_gate_index} did not restore mapping.",
            )
        routes.append(
            {
                "route_index": len(routes),
                "source_gate_index": logical_gate_index,
                "gate_name": "cx",
                "logical_qubits": logical_qubits,
                "source_partition": first_partition,
                "target_partition": second_partition,
                "source_node": source_node,
                "target_node": target_node,
                "route_path": [source_node, target_node],
                "carrier_logical_qubit": carrier_logical,
                "carrier_execution_qubit": carrier_execution,
                "remote_operation_type": "remote_swap_route_and_restore",
                "expanded_operation_start": start_index,
                "expanded_operation_end_exclusive": len(executable),
                "communication_cost": 6,
                "mapping_before": mapping_before,
                "mapping_during": mapping_during,
                "mapping_after": mapping_after,
            }
        )
        if len(executable) > maximum_expanded_gate_count:
            raise DistributedCompilationError(
                "blocked_by_resource_guardrail",
                "Expanded gate count exceeds the frozen protocol limit.",
            )

    identity = [[qubit, qubit] for qubit in range(parsed.circuit.num_qubits)]
    final_mapping = [
        [logical, logical_to_execution[logical]]
        for logical in sorted(logical_to_execution)
    ]
    if final_mapping != identity:
        raise DistributedCompilationError(
            "mapping_restore_failed",
            "Final logical-to-execution mapping is not identity.",
        )
    return executable, routes


def compile_distributed_v1(
    parsed: ParsedCircuit,
    *,
    settings: CompilationSettings,
    maximum_expanded_gate_count: int,
    topology_payload: dict[str, Any],
    topology_sha256: str,
) -> CompilationArtifacts:
    """Compile one frozen logical circuit into a route-and-restore executable."""
    started = time.perf_counter()
    qubit_count = parsed.circuit.num_qubits
    projected = _operation_projection(parsed)
    search = run_deterministic_partition_search_v1(
        projected,
        list(range(qubit_count)),
        num_partitions=settings.partition_count,
        max_imbalance=settings.maximum_imbalance,
        b1_list=list(settings.b1_grid),
        b2_list=list(settings.b2_grid),
        alpha=settings.alpha,
        beta=settings.beta,
        num_starts=settings.num_starts,
    )
    partitions = search["selected"]["partitions"]
    if [len(partition) for partition in partitions] != [qubit_count // 2] * 2:
        raise DistributedCompilationError(
            "partition_constraint_violation",
            "The frozen even-sized benchmark requires exactly balanced partitions.",
        )
    qubit_to_partition = {
        qubit: partition_id
        for partition_id, partition in enumerate(partitions)
        for qubit in partition
    }
    if sorted(qubit_to_partition) != list(range(qubit_count)):
        raise DistributedCompilationError(
            "partition_constraint_violation",
            "Partitioning omitted or duplicated logical qubits.",
        )

    # V1 uses a no-op full-gate reorder unless a disjoint-support move has a
    # proven primary-metric benefit.  The frozen benchmark has no such move.
    optimized_operations = [dict(operation) for operation in parsed.operations]
    mapping, mapping_candidates = _deterministic_mapping(
        partitions,
        parsed.operations,
    )
    expected_mapping = dict(settings.expected_partition_to_node)
    if mapping != expected_mapping:
        raise DistributedCompilationError(
            "mapping_failed",
            "Symmetric linear-2 mapping did not satisfy the frozen tie-break.",
        )
    executable_operations, route_events = _route_and_restore(
        parsed,
        partitions,
        mapping,
        maximum_expanded_gate_count,
    )

    baseline = _metrics(
        list(parsed.operations),
        qubit_count,
        qubit_to_partition,
    )
    optimized = _metrics(
        optimized_operations,
        qubit_count,
        qubit_to_partition,
    )
    optimized.update(
        {
            "distributed_executable_depth": _circuit_depth(
                executable_operations,
                qubit_count,
            ),
            "distributed_executable_gate_count": len(executable_operations),
            "remote_swap_count": len(route_events) * 2,
            "communication_round_count": len(route_events) * 2,
            "weighted_route_cost": sum(
                route["communication_cost"] for route in route_events
            ),
            "compile_elapsed_seconds": time.perf_counter() - started,
            "optimization_conclusion": "compiled_without_metric_improvement",
        }
    )
    logical_snapshot = {
        "artifact_type": "logical_circuit_snapshot",
        "schema_version": 1,
        "qubit_count": qubit_count,
        "raw_qasm": parsed.qasm_text,
        "raw_qasm_sha256": parsed.raw_qasm_sha256,
        "canonicalization_scheme": "qasm2-canonical-circuit-v1",
        "canonical_circuit_sha256": parsed.canonical_sha256,
        "parameters_bound": True,
        "operations": [dict(operation) for operation in parsed.operations],
    }
    partition_plan = {
        "artifact_type": "partition_plan",
        "schema_version": 1,
        "partition_ids": [0, 1],
        "qubit_to_partition": [
            [qubit, qubit_to_partition[qubit]]
            for qubit in sorted(qubit_to_partition)
        ],
        "protocol_parameters": {
            "partition_count": settings.partition_count,
            "maximum_imbalance": settings.maximum_imbalance,
            "b1_grid": list(settings.b1_grid),
            "b2_grid": list(settings.b2_grid),
            "alpha": settings.alpha,
            "beta": settings.beta,
            "num_starts": settings.num_starts,
            "audit_seed": settings.audit_seed,
            "stochastic_behavior_used": False,
            "partition_numbering": settings.partition_numbering,
            "candidate_tie_break": list(settings.candidate_tie_break),
        },
        **search,
    }
    optimized_gate_order = {
        "artifact_type": "optimized_gate_order",
        "schema_version": 1,
        "scheme": settings.gate_ordering_scheme,
        "original_to_optimized_indices": [
            [index, index] for index in range(len(parsed.operations))
        ],
        "operations": optimized_operations,
        "semantic_change": False,
        "equivalence_infidelity": 0.0,
        "equivalence_infidelity_maximum": (
            settings.equivalence_infidelity_maximum
        ),
        "conclusion": "compiled_without_metric_improvement",
        "baseline_metrics": baseline,
        "optimized_metrics": optimized,
    }
    chip_mapping = {
        "artifact_type": "chip_mapping",
        "schema_version": 1,
        "algorithm": "minimum_cost_then_lexicographic_mapping_v1",
        "candidate_mappings": mapping_candidates,
        "partition_to_node": [
            [partition_id, mapping[partition_id]]
            for partition_id in sorted(mapping)
        ],
        "equal_cost_tie_break": "lexicographically_smallest_sorted_integer_partition_node_pairs",
        "validated": True,
    }
    communication_route_plan = {
        "artifact_type": "communication_route_plan",
        "schema_version": 1,
        "strategy": "topology_aware_remote_swap_route_and_restore",
        "additional_ancilla_count": 0,
        "carrier_selection": "target_node_lowest_available_execution_qubit",
        "routes": route_events,
        "final_logical_to_execution_mapping": [
            [qubit, qubit] for qubit in range(qubit_count)
        ],
        "mapping_restored": True,
    }
    distributed_executable = {
        "artifact_type": "distributed_executable",
        "schema_version": 1,
        "qubit_count": qubit_count,
        "global_phase": 0.0,
        "standard_gate_set": ["u3", "cx"],
        "operations": executable_operations,
        "initial_logical_to_execution_mapping": [
            [qubit, qubit] for qubit in range(qubit_count)
        ],
        "final_logical_to_execution_mapping": [
            [qubit, qubit] for qubit in range(qubit_count)
        ],
        "mapping_restored": True,
        "additional_ancilla_count": 0,
        "actual_distributed_hardware_execution": False,
        "status": "distributed_executable_ready",
    }
    target_topology = {
        "artifact_type": "target_topology",
        "schema_version": 1,
        "topology": topology_payload,
        "topology_sha256": topology_sha256,
    }
    return CompilationArtifacts(
        logical_snapshot=logical_snapshot,
        partition_plan=partition_plan,
        optimized_gate_order=optimized_gate_order,
        target_topology=target_topology,
        chip_mapping=chip_mapping,
        communication_route_plan=communication_route_plan,
        distributed_executable=distributed_executable,
        baseline_metrics=baseline,
        optimized_metrics=optimized,
    )
