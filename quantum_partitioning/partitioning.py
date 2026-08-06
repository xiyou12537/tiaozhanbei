"""
Quantum circuit partitioning via greedy multi-start search with
hyper-parameter grid search.

The partitioning problem: given a circuit (as a gate list) and a target
number of compute nodes *k*, assign each qubit to exactly one partition
such that the number of cross-partition (global) gates is minimised.

We use a greedy expansion heuristic:
    1. Seed a partition with a high-activity qubit.
    2. Greedily add qubits that maximise interaction with the growing
       partition while minimising schedule-span (colour-segment count).
    3. Repeat for remaining partitions.
    4. Evaluate the result by optimising gate order and counting
       teleportations.

The search is repeated from multiple starting seeds (top-K qubits by
gate count), and a hyper-parameter grid search over (b1, b2) can be
enabled to tune the score function.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from .config import (
    DEFAULT_B1,
    DEFAULT_B2,
    DEFAULT_ALPHA,
    DEFAULT_BETA,
    DEFAULT_B1_RANGE,
    DEFAULT_B2_RANGE,
    DEFAULT_MAX_IMBALANCE,
    DEFAULT_NUM_PARTITIONS,
    DEFAULT_NUM_STARTS,
    PartitionResult,
)
from .circuit_utils import (
    compute_coloured_sequence,
    compute_interaction_matrix,
    compute_qubit_gate_map,
    count_colour_segments,
    evaluate_global_gates_all_partitions,
)
from .gate_ordering import optimize_gate_order_all_partitions


# ---------------------------------------------------------------------------
# Score function
# ---------------------------------------------------------------------------

def compute_partition_score(
    inter_score: float,
    span: float,
    b1: float = DEFAULT_B1,
    b2: float = DEFAULT_B2,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> float:
    """Score a candidate qubit for addition to a partition.

    Higher scores are better.  The score balances:
    - *inter_score*: interaction count with the current partition
      (encourages locality).
    - *span*: colour-segment count (penalises temporal spreading).

    Formula: ``alpha * inter_score * ln(b1) - beta * span * ln(b2)``

    Args:
        inter_score: Number of interactions with the partition.
        span: Colour-segment count (schedule fragmentation).
        b1: Base for interaction reward.
        b2: Base for span penalty.
        alpha: Interaction weight.
        beta: Span penalty weight.

    Returns:
        Numeric score (may be negative).
    """
    return alpha * inter_score * math.log(b1) - beta * span * math.log(b2)


# ---------------------------------------------------------------------------
# Partitioner
# ---------------------------------------------------------------------------

@dataclass
class PartitionScheme:
    """Result of a single partitioning run."""

    partitions: List[List[int]]
    optimized_gates: List[Gate]
    teleportations: int
    global_gates: int


class GreedyPartitioner:
    """Multi-start greedy partitioner.

    Args:
        gates: Gate list.
        qubits: Sorted list of all qubit indices.
        num_partitions: Target number of partitions.
        max_imbalance: Maximum allowed size difference between partitions.
        b1: Base for interaction score.
        b2: Base for span penalty.
        alpha: Interaction weight.
        beta: Span penalty weight.
        num_starts: Number of top qubits to try as first-partition seeds.
    """

    def __init__(
        self,
        gates: List[Gate],
        qubits: List[int],
        num_partitions: int = DEFAULT_NUM_PARTITIONS,
        max_imbalance: int = DEFAULT_MAX_IMBALANCE,
        b1: float = DEFAULT_B1,
        b2: float = DEFAULT_B2,
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA,
        num_starts: int = DEFAULT_NUM_STARTS,
    ):
        self._gates = gates
        self._qubits = qubits
        self._num_partitions = num_partitions
        self._max_imbalance = max_imbalance
        self._b1 = b1
        self._b2 = b2
        self._alpha = alpha
        self._beta = beta
        self._num_starts = num_starts

        # Pre-compute once
        self._qubit_gate_map = compute_qubit_gate_map(gates)
        self._interaction = compute_interaction_matrix(gates)
        self._target_size = len(qubits) // num_partitions

    def run(self) -> Optional[PartitionScheme]:
        """Run the multi-start greedy search.

        Returns:
            The best ``PartitionScheme`` found, or ``None`` if all
            starts failed.
        """
        # Select seed candidates: top-K qubits by gate count
        sorted_by_activity = sorted(
            self._qubit_gate_map.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        # Filter out the -1 key (local gates) if present
        candidate_starts = [
            q for q, _ in sorted_by_activity[:self._num_starts] if q != -1
        ]

        best_scheme: Optional[PartitionScheme] = None
        best_teleport = float("inf")
        best_global = float("inf")

        for seed in candidate_starts:
            partitions = self._build_partitions_from_seed(seed)
            if partitions is None:
                continue

            # Evaluate (uses gate-ordering defaults: alpha=4, beta=1,
            # matching the original optimize_gate_order_with_sa behaviour)
            optimized_gates, teleportations = optimize_gate_order_all_partitions(
                self._gates, partitions
            )
            global_gates = evaluate_global_gates_all_partitions(
                partitions, optimized_gates
            )

            if (
                teleportations < best_teleport
                or (teleportations == best_teleport and global_gates < best_global)
            ):
                best_scheme = PartitionScheme(
                    partitions=partitions,
                    optimized_gates=optimized_gates,
                    teleportations=teleportations,
                    global_gates=global_gates,
                )
                best_teleport = teleportations
                best_global = global_gates

        return best_scheme

    # ── Internal: build partitions from a single seed ────────────────

    def _build_partitions_from_seed(
        self, seed: int
    ) -> Optional[List[List[int]]]:
        """Build a full set of partitions starting from *seed*."""
        unassigned: Set[int] = set(self._qubits)

        partitions: List[List[int]] = []

        # First partition: expanded from seed
        first = [seed]
        unassigned.discard(seed)
        self._expand_partition(first, unassigned)
        partitions.append(first)

        # Remaining partitions
        for _ in range(self._num_partitions - 1):
            if not unassigned:
                break

            # Pick the unassigned qubit with most gates as next seed
            next_seed = max(
                unassigned,
                key=lambda q: len(self._qubit_gate_map.get(q, [])),
            )
            part = [next_seed]
            unassigned.discard(next_seed)
            self._expand_partition(part, unassigned)
            partitions.append(part)

        # Assign remainder qubits one at a time.  Every partition starts at
        # the integer-division base size and can receive at most one extra
        # qubit, so the final size difference cannot exceed one.
        if len(partitions) < self._num_partitions:
            partitions.append(list(unassigned))
        else:
            for q in sorted(unassigned):
                eligible_indices = [
                    index
                    for index, partition in enumerate(partitions)
                    if len(partition) == self._target_size
                ]
                if not eligible_indices:
                    return None
                best_index = max(
                    eligible_indices,
                    key=lambda index: self._score_remainder_assignment(
                        q, partitions[index]
                    ),
                )
                partitions[best_index].append(q)

        return partitions

    def _score_remainder_assignment(self, qubit: int, partition: List[int]) -> float:
        """Score a remainder qubit against one eligible base-size partition."""
        interaction_score = sum(
            self._interaction.get(qubit, {}).get(other, 0)
            for other in partition
        )
        current_span = count_colour_segments(
            compute_coloured_sequence(self._qubit_gate_map, partition)
        )
        candidate_span = count_colour_segments(
            compute_coloured_sequence(self._qubit_gate_map, partition + [qubit])
        )
        return compute_partition_score(
            interaction_score,
            candidate_span - current_span,
            b1=self._b1,
            b2=self._b2,
            alpha=self._alpha,
            beta=self._beta,
        )

    def _expand_partition(
        self, partition: List[int], unassigned: Set[int]
    ) -> None:
        """Greedily expand *partition* until it reaches target size."""
        target = min(
            self._target_size,
            len(partition) + len(unassigned),
        )

        while len(partition) < target and unassigned:
            best_q: Optional[int] = None
            best_score = float("-inf")

            for q in unassigned:
                inter_score = sum(
                    self._interaction.get(q, {}).get(other, 0)
                    for other in partition
                )
                colour_seq = compute_coloured_sequence(
                    self._qubit_gate_map, partition + [q]
                )
                colour_seg = count_colour_segments(colour_seq)

                score = compute_partition_score(
                    inter_score,
                    colour_seg,
                    b1=self._b1,
                    b2=self._b2,
                    alpha=self._alpha,
                    beta=self._beta,
                )
                if score > best_score:
                    best_score = score
                    best_q = q

            if best_q is None:
                break

            partition.append(best_q)
            unassigned.discard(best_q)


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------

def grid_search_partitioning(
    gates: List[Gate],
    qubits: List[int],
    num_partitions: int = DEFAULT_NUM_PARTITIONS,
    b1_list: Optional[List[float]] = None,
    b2_list: Optional[List[float]] = None,
    max_imbalance: int = DEFAULT_MAX_IMBALANCE,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> Tuple[Optional[PartitionScheme], float, float]:
    """Search over (b1, b2) hyper-parameter grid for the best partition.

    Args:
        gates: Gate list.
        qubits: Qubit list.
        num_partitions: Target partition count.
        b1_list: Values of *b1* to try (default: 1..20).
        b2_list: Values of *b2* to try (default: 1..20).
        max_imbalance: Max partition size difference.
        alpha: Interaction weight.
        beta: Span penalty weight.

    Returns:
        ``(best_scheme, best_b1, best_b2)``.  The scheme may be
        ``None`` if no valid partition was found.
    """
    if b1_list is None:
        b1_list = DEFAULT_B1_RANGE
    if b2_list is None:
        b2_list = DEFAULT_B2_RANGE

    best_scheme: Optional[PartitionScheme] = None
    best_teleport = float("inf")
    best_global = float("inf")
    best_b1 = b1_list[0]
    best_b2 = b2_list[0]

    # Collect results for parameter landscape visualisation
    teleport_grid: Dict[Tuple[float, float], int] = {}

    for b1 in b1_list:
        for b2 in b2_list:
            partitioner = GreedyPartitioner(
                gates=gates,
                qubits=qubits,
                num_partitions=num_partitions,
                max_imbalance=max_imbalance,
                b1=b1,
                b2=b2,
                alpha=alpha,
                beta=beta,
            )
            scheme = partitioner.run()
            if scheme is None:
                continue

            teleport_grid[(b1, b2)] = scheme.teleportations

            if (
                scheme.teleportations < best_teleport
                or (scheme.teleportations == best_teleport
                    and scheme.global_gates < best_global)
            ):
                best_scheme = scheme
                best_teleport = scheme.teleportations
                best_global = scheme.global_gates
                best_b1 = b1
                best_b2 = b2

    return best_scheme, best_b1, best_b2


# ---------------------------------------------------------------------------
# Top-level pipeline entry point (replaces ``genetic_multi_partitioning``)
# ---------------------------------------------------------------------------

def run_partitioning_pipeline(
    gates: List[Gate],
    qubits: List[int],
    num_partitions: int = DEFAULT_NUM_PARTITIONS,
    max_imbalance: int = DEFAULT_MAX_IMBALANCE,
    search: bool = False,
    b1_list: Optional[List[float]] = None,
    b2_list: Optional[List[float]] = None,
    b1: float = DEFAULT_B1,
    b2: float = DEFAULT_B2,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> Tuple[Optional[PartitionScheme], Optional[float], Optional[float]]:
    """Run the full partitioning pipeline.

    Args:
        gates: Gate list (multi-qubit gates only recommended).
        qubits: Sorted qubit index list.
        num_partitions: Number of compute nodes.
        max_imbalance: Max size imbalance between partitions.
        search: If ``True``, run grid search over (b1, b2).
        b1_list: b1 values for grid search.
        b2_list: b2 values for grid search.
        b1: b1 value when ``search=False``.
        b2: b2 value when ``search=False``.
        alpha: Interaction weight.
        beta: Span penalty weight.

    Returns:
        ``(scheme, b1_used, b2_used)``.  *scheme* is a
        ``PartitionScheme`` or ``None``.
    """
    if search:
        if b1_list is None:
            b1_list = DEFAULT_B1_RANGE
        if b2_list is None:
            b2_list = DEFAULT_B2_RANGE

        scheme, best_b1, best_b2 = grid_search_partitioning(
            gates=gates,
            qubits=qubits,
            num_partitions=num_partitions,
            b1_list=b1_list,
            b2_list=b2_list,
            max_imbalance=max_imbalance,
            alpha=alpha,
            beta=beta,
        )
        return scheme, best_b1, best_b2
    else:
        partitioner = GreedyPartitioner(
            gates=gates,
            qubits=qubits,
            num_partitions=num_partitions,
            max_imbalance=max_imbalance,
            b1=b1,
            b2=b2,
            alpha=alpha,
            beta=beta,
        )
        scheme = partitioner.run()
        return scheme, b1, b2
