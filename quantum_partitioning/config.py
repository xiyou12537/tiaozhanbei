"""
Configuration constants and type definitions for the quantum circuit
partitioning optimization framework.

All magic numbers, gate type classifications, and tuning parameters
should be defined here so they can be adjusted from a single place.
"""

from __future__ import annotations

from typing import Union, List, Dict, Tuple

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# A gate is represented as [name, qubit, ...] or [name, qubit, qubit]
Gate = List[Union[str, int]]

# Partition: a list of qubit indices assigned to one compute node
Partition = List[int]

# Mapping from qubit index -> partition id (string "P1", "P2", ...)
QubitToPartition = Dict[int, str]

# Mapping from partition id -> chip id (string "T1", "T2", ...)
PartitionToChip = Dict[str, str]

# A result from the partitioning pipeline
PartitionResult = Tuple[List[Partition], List[Gate], int, int]
#  (partitions,     optimized_gates, teleportations, global_gates)

# ---------------------------------------------------------------------------
# Gate-type classification sets
# ---------------------------------------------------------------------------

SINGLE_QUBIT_GATES = frozenset({
    'x', 'y', 'z', 'h', 's', 't', 'sdg', 'tdg', 'rx', 'ry', 'rz',
    'id', 'u1', 'u2', 'u3', 'p', 'sx',
})

TWO_QUBIT_GATES = frozenset({
    'cx', 'cz', 'swap', 'iswap', 'rzz', 'rxx', 'ryy', 'rzx',
    'ecr', 'cp',
})

# Gate types that this framework models as remote-swap markers
RSWAP_GATE = 'rswap'

# Single-qubit gates that commute past a CNOT control qubit
SINGLE_QUBIT_COMMUTING_WITH_CX_CONTROL = frozenset({
    't', 'tdg', 'z', 'h', 's', 'sdg',
})

# Single-qubit gates that commute past a CNOT target qubit
SINGLE_QUBIT_COMMUTING_WITH_CX_TARGET = frozenset({
    'x', 'rx',
})

# ---------------------------------------------------------------------------
# Default hyper-parameters
# ---------------------------------------------------------------------------

DEFAULT_B1 = 10          # base for interaction score in partition scoring
DEFAULT_B2 = 2           # base for span penalty in partition scoring
DEFAULT_ALPHA = 3        # weight for mergeability vs return penalty
DEFAULT_BETA = 1         # weight for return penalty vs mergeability

DEFAULT_NUM_PARTITIONS = 2
DEFAULT_MAX_IMBALANCE = 1

# Multi-start search
DEFAULT_NUM_STARTS = 15   # top-k qubits used as partition seeds

# Grid search defaults
DEFAULT_B1_RANGE = list(range(1, 21))
DEFAULT_B2_RANGE = list(range(1, 21))

# Remote swap optimisation
DEFAULT_SWAP_MAX_ITERATIONS = 200
DEFAULT_SWAP_TOP_K = 5

# Simulated annealing (gate ordering)
DEFAULT_SA_ALPHA = 4
DEFAULT_SA_BETA = 1
