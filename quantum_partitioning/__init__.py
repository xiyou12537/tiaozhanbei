"""
Quantum circuit partitioning toolkit.

This package intentionally avoids importing heavy submodules at import time.
Callers can still use ``from quantum_partitioning import ...`` and the symbols
will be resolved lazily on first access.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "DEFAULT_ALPHA": "config",
    "DEFAULT_BETA": "config",
    "DEFAULT_B1": "config",
    "DEFAULT_B2": "config",
    "DEFAULT_NUM_PARTITIONS": "config",
    "DEFAULT_MAX_IMBALANCE": "config",
    "PartitionResult": "config",
    "Gate": "config",
    "QubitToPartition": "config",
    "PartitionToChip": "config",
    "load_qasm_file": "qasm_io",
    "load_qasm_string": "qasm_io",
    "gates_to_qasm": "qasm_io",
    "circuit_to_gate_list": "qasm_io",
    "remove_single_qubit_gates": "circuit_utils",
    "extract_qubits": "circuit_utils",
    "compute_qubit_lifetimes": "circuit_utils",
    "compute_qubit_gate_map": "circuit_utils",
    "compute_interaction_matrix": "circuit_utils",
    "evaluate_global_gates_all_partitions": "circuit_utils",
    "PartitionScheme": "partitioning",
    "GreedyPartitioner": "partitioning",
    "grid_search_partitioning": "partitioning",
    "run_partitioning_pipeline": "partitioning",
    "compute_partition_score": "partitioning",
    "build_partition_interaction_graph": "chip_mapping",
    "parse_target_topology": "chip_mapping",
    "parse_target_topology_from_string": "chip_mapping",
    "find_chip_mapping": "chip_mapping",
    "compute_epr_cost": "chip_mapping",
    "compute_total_epr_cost": "chip_mapping",
    "optimize_remote_swaps": "swap_optimization",
    "apply_swap_events_to_gates": "swap_optimization",
    "apply_rswap_semantics": "swap_optimization",
    "select_swap_candidates": "swap_optimization",
    "find_best_swap_insertion": "swap_optimization",
    "TeleportationGrouper": "teleportation",
    "compute_teleportation_cost": "teleportation",
    "GateOrderOptimizer": "gate_ordering",
    "optimize_gate_order_all_partitions": "gate_ordering",
    "can_swap": "gate_commutation",
}

__all__ = sorted(_EXPORTS.keys())


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'quantum_partitioning' has no attribute '{name}'")

    module = import_module(f".{_EXPORTS[name]}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(list(globals().keys()) + __all__)
