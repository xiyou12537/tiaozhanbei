"""
Quantum Circuit Partitioning Optimisation Framework
===================================================

A library for partitioning quantum circuits across distributed
computing nodes, minimising inter-node quantum teleportation cost.

Quick start::

    from quantum_partitioning import (
        load_qasm_file,
        run_partitioning_pipeline,
        find_chip_mapping,
        compute_total_epr_cost,
    )

    # 1. Load a circuit
    num_qubits, gates = load_qasm_file("circuit.qasm")

    # 2. Partition into K compute nodes
    from quantum_partitioning.circuit_utils import (
        remove_single_qubit_gates,
        extract_qubits,
    )
    multi_gates = remove_single_qubit_gates(gates)
    qubits = extract_qubits(multi_gates)

    scheme, b1, b2 = run_partitioning_pipeline(
        multi_gates, qubits, num_partitions=4, search=True
    )

    # 3. Map partitions to physical chip topology
    from quantum_partitioning.chip_mapping import (
        build_partition_interaction_graph,
        parse_target_topology,
    )
    complete_g, _ = build_partition_interaction_graph(
        scheme.partitions, scheme.optimized_gates
    )
    target = parse_target_topology([(0,1),(1,2),(2,3),(3,0)])  # ring

    mapping, cost = find_chip_mapping(complete_g, target)
"""

from .config import (
    DEFAULT_ALPHA,
    DEFAULT_BETA,
    DEFAULT_B1,
    DEFAULT_B2,
    DEFAULT_NUM_PARTITIONS,
    DEFAULT_MAX_IMBALANCE,
    PartitionResult,
    Gate,
    QubitToPartition,
    PartitionToChip,
)

from .qasm_io import (
    load_qasm_file,
    load_qasm_string,
    gates_to_qasm,
    circuit_to_gate_list,
)

from .circuit_utils import (
    remove_single_qubit_gates,
    extract_qubits,
    compute_qubit_lifetimes,
    compute_qubit_gate_map,
    compute_interaction_matrix,
    evaluate_global_gates_all_partitions,
)

from .partitioning import (
    PartitionScheme,
    GreedyPartitioner,
    grid_search_partitioning,
    run_partitioning_pipeline,
    compute_partition_score,
)

from .chip_mapping import (
    build_partition_interaction_graph,
    parse_target_topology,
    parse_target_topology_from_string,
    find_chip_mapping,
    compute_epr_cost,
    compute_total_epr_cost,
)

from .swap_optimization import (
    optimize_remote_swaps,
    apply_swap_events_to_gates,
    apply_rswap_semantics,
    select_swap_candidates,
    find_best_swap_insertion,
)

from .teleportation import (
    TeleportationGrouper,
    compute_teleportation_cost,
)

from .gate_ordering import (
    GateOrderOptimizer,
    optimize_gate_order_all_partitions,
)

from .gate_commutation import can_swap

__all__ = [
    # Config
    "DEFAULT_ALPHA", "DEFAULT_BETA", "DEFAULT_B1", "DEFAULT_B2",
    "DEFAULT_NUM_PARTITIONS", "DEFAULT_MAX_IMBALANCE",
    # I/O
    "load_qasm_file", "load_qasm_string", "gates_to_qasm",
    "circuit_to_gate_list",
    # Utils
    "remove_single_qubit_gates", "extract_qubits",
    "compute_qubit_lifetimes", "compute_qubit_gate_map",
    "compute_interaction_matrix", "evaluate_global_gates_all_partitions",
    # Partitioning
    "PartitionScheme", "GreedyPartitioner",
    "grid_search_partitioning", "run_partitioning_pipeline",
    # Mapping
    "build_partition_interaction_graph",
    "parse_target_topology", "parse_target_topology_from_string",
    "find_chip_mapping", "compute_epr_cost", "compute_total_epr_cost",
    # Swap
    "optimize_remote_swaps", "apply_swap_events_to_gates",
    "apply_rswap_semantics",
    # Teleportation
    "TeleportationGrouper", "compute_teleportation_cost",
    # Gate ordering
    "GateOrderOptimizer", "optimize_gate_order_all_partitions",
    # Commutation
    "can_swap",
]
