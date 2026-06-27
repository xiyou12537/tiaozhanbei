"""
Unified teleportation cost engine for distributed quantum computing.

This module merges the duplicated teleportation-grouping logic that
previously appeared in both ``calculate_teleportation`` and
``optimize_gate_order_with_sa`` from the original codebase.

The core idea:
    When a two-qubit gate spans two partitions (a "global" gate),
    quantum teleportation is needed to bring the qubits together.
    Multiple global gates can share a single teleportation if they
    use the same teleported qubit and don't interfere with each other.

Algorithm overview (per partition pair):
    1. Identify all global (cross-partition) gates in temporal order.
    2. Greedily group them by shared teleportation qubit.
    3. A group of *k* gates costs:
       - *k = 1*: 1 teleportation (telegate protocol).
       - *k > 1*, qubit used later: 2 teleportations (teledata + return).
       - *k > 1*, qubit NOT used later: 1 teleportation (teledata only).
"""

from __future__ import annotations

from typing import List, Optional, Set
from dataclasses import dataclass, field

from .config import Gate, RSWAP_GATE


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GlobalGate:
    """A gate whose qubits span two partitions."""

    index: int
    """Position in the gate list."""

    qubits: Set[int]
    """Set of qubit indices involved in this gate."""


@dataclass
class TeleportationGroup:
    """A set of global gates that share a single teleportation operation."""

    teleport_qubit: int
    """The qubit that gets teleported."""

    gates: List[GlobalGate] = field(default_factory=list)
    """Global gates covered by this teleportation."""

    start_idx: int = -1
    """Earliest gate index in this group."""

    end_idx: int = -1
    """Latest gate index in this group."""


# ---------------------------------------------------------------------------
# Teleportation grouper
# ---------------------------------------------------------------------------

class TeleportationGrouper:
    """Group cross-partition gates into shared-teleportation clusters.

    This class identifies all global (cross-partition) gates and runs
    a greedy grouping algorithm.  The resulting groups can be used to
    compute the teleportation cost or to inform the gate-ordering
    optimiser.

    Args:
        gates: The full gate list for the circuit.
        partition1: Qubit indices in the first partition.
        partition2: Qubit indices in the second partition.
        alpha: Weight for mergeability score (higher = prefer merging).
        beta: Weight for return-teleport penalty (higher = penalise
            qubits that must be returned to their home partition).
    """

    def __init__(
        self,
        gates: List[Gate],
        partition1: List[int],
        partition2: List[int],
        alpha: float = 3.0,
        beta: float = 1.0,
    ):
        self._gates = gates
        self._p1: Set[int] = set(partition1)
        self._p2: Set[int] = set(partition2)
        self._alpha = alpha
        self._beta = beta

        # Identify all global gates (in temporal order)
        self._global_gates: List[GlobalGate] = self._find_global_gates()

        # Pre-compute rswap indices for fast interference checks
        self._rswap_indices: Set[int] = {
            i for i, g in enumerate(gates) if g[0] == RSWAP_GATE
        }

    # ── Public API ────────────────────────────────────────────────────

    @property
    def global_gate_count(self) -> int:
        """Number of cross-partition gates found."""
        return len(self._global_gates)

    def build_groups(self) -> List[TeleportationGroup]:
        """Run the greedy grouping algorithm.

        For each global gate (in temporal order), we either:
        1. Merge it into the best existing group (nearest in time,
           no interference, no time conflict), or
        2. Create a new group with the best-scoring teleport qubit.

        Returns:
            List of teleportation groups.
        """
        groups: List[TeleportationGroup] = []

        for gg in self._global_gates:
            idx = gg.index
            qubits = list(gg.qubits)

            # ── Step 1: Try to merge into an existing group ──
            best_group = self._find_best_merge_group(groups, gg, idx)

            if best_group is not None:
                best_group.gates.append(gg)
                best_group.end_idx = idx
            else:
                # ── Step 2: Create a new group ──
                best_tq = self._pick_best_teleport_qubit(qubits, idx, groups)
                if best_tq is not None:
                    groups.append(
                        TeleportationGroup(
                            teleport_qubit=best_tq,
                            gates=[gg],
                            start_idx=idx,
                            end_idx=idx,
                        )
                    )

        return groups

    def compute_cost(self) -> int:
        """Compute the total teleportation cost for the grouped gates.

        Returns:
            Total number of EPR pairs or teleportation operations required.
        """
        groups = self.build_groups()
        total = 0

        for group in groups:
            k = len(group.gates)
            tq = group.teleport_qubit

            if k == 1:
                # Single gate → telegate protocol (1 EPR pair)
                total += 1
            else:
                # Multiple gates → teledata protocol
                if self._used_later(group.end_idx, tq):
                    # Qubit needs to be returned → 2 EPR pairs
                    total += 2
                else:
                    # No return needed → 1 EPR pair
                    total += 1

        return total

    # ── Group-finding helpers ─────────────────────────────────────────

    def _find_best_merge_group(
        self,
        groups: List[TeleportationGroup],
        gg: GlobalGate,
        idx: int,
    ) -> Optional[TeleportationGroup]:
        """Find the best existing group to merge *gg* into.

        Returns ``None`` if no group is suitable.
        """
        best_group: Optional[TeleportationGroup] = None
        best_score = float("-inf")

        for group in groups:
            tq = group.teleport_qubit

            # rswap barrier: cannot merge across an rswap gate
            if any(
                r in self._rswap_indices
                for r in range(group.end_idx + 1, idx)
            ):
                continue

            # Must share the teleported qubit
            if tq not in gg.qubits:
                continue

            # No gate touching tq between group end and current gate
            if self._has_interference(group.end_idx, idx, tq):
                continue

            # Extended range must not overlap other groups
            if self._has_time_conflict(groups, group.start_idx, idx, group):
                continue

            # Score: prefer closer groups (fewer idle cycles)
            score = -(idx - group.end_idx)
            if score > best_score:
                best_score = score
                best_group = group

        return best_group

    # ── Interference / conflict checks ────────────────────────────────

    def _has_interference(self, start: int, end: int, tq: int) -> bool:
        """Check whether *tq* appears in any gate between *start* and *end*.

        An rswap gate also counts as interference since it changes qubit
        identity.
        """
        for idx in range(start + 1, end):
            if idx in self._rswap_indices:
                return True
            gate = self._gates[idx]
            if tq in (int(q) for q in gate[1:]):
                return True
        return False

    def _used_later(self, after_idx: int, tq: int) -> bool:
        """Check whether *tq* appears in any gate after *after_idx*.

        An rswap terminates the "used later" check because after an
        rswap the qubit identity has changed.
        """
        for idx in range(after_idx + 1, len(self._gates)):
            if idx in self._rswap_indices:
                return False
            gate = self._gates[idx]
            if tq in (int(q) for q in gate[1:]):
                return True
        return False

    @staticmethod
    def _overlaps(start1: int, end1: int, start2: int, end2: int) -> bool:
        """Return ``True`` if the two intervals overlap."""
        return not (end1 < start2 or end2 < start1)

    @staticmethod
    def _has_time_conflict(
        groups: List[TeleportationGroup],
        new_start: int,
        new_end: int,
        exclude_group: Optional[TeleportationGroup] = None,
    ) -> bool:
        """Check if ``[new_start, new_end]`` overlaps any existing group.

        *exclude_group* (typically the group being extended) is skipped.
        """
        for group in groups:
            if group is exclude_group:
                continue
            if TeleportationGrouper._overlaps(
                new_start, new_end, group.start_idx, group.end_idx
            ):
                return True
        return False

    @staticmethod
    def _has_time_conflict_with_same_tq(
        groups: List[TeleportationGroup],
        tq: int,
        new_start: int,
        new_end: int,
    ) -> bool:
        """Check if ``[new_start, new_end]`` overlaps a group using the
        **same** teleport qubit *tq*."""
        for group in groups:
            if group.teleport_qubit != tq:
                continue
            if TeleportationGrouper._overlaps(
                new_start, new_end, group.start_idx, group.end_idx
            ):
                return True
        return False

    # ── Scoring ───────────────────────────────────────────────────────

    def _score_teleport_qubit(self, tq: int, current_idx: int) -> int:
        """Count how many future global gates can be merged if we pick *tq*.

        A future gate is mergeable if it touches *tq* and there is no
        interference between *current_idx* and that gate.
        """
        count = 0
        for gg in self._global_gates:
            if gg.index <= current_idx:
                continue
            if gg.index in self._rswap_indices:
                continue
            if tq in gg.qubits and not self._has_interference(
                current_idx, gg.index, tq
            ):
                count += 1
        return count

    def _pick_best_teleport_qubit(
        self,
        qubits: List[int],
        idx: int,
        groups: List[TeleportationGroup],
    ) -> Optional[int]:
        """Choose the best qubit to teleport for a new group at index *idx*.

        Matches the original ``calculate_teleportation`` behaviour:
        a candidate qubit is skipped if its single-point group at *idx*
        would overlap any existing group (time-conflict check).
        """
        best_tq: Optional[int] = None
        best_score = float("-inf")

        for tq in qubits:
            mergeability = self._score_teleport_qubit(tq, idx)
            return_penalty = 1 if self._used_later(idx, tq) else 0
            score = self._alpha * mergeability - self._beta * return_penalty

            # Original behaviour: skip tq if [idx, idx] overlaps any group
            if self._has_time_conflict(groups, idx, idx):
                continue

            if score > best_score:
                best_score = score
                best_tq = tq

        return best_tq

    # ── Internal scan ─────────────────────────────────────────────────

    def _find_global_gates(self) -> List[GlobalGate]:
        """Scan the gate list for gates whose qubits span both partitions."""
        result: List[GlobalGate] = []
        for i, gate in enumerate(self._gates):
            if gate[0] == RSWAP_GATE:
                continue
            if len(gate) < 3:
                continue
            qubits = {int(gate[1]), int(gate[2])}
            if (qubits & self._p1) and (qubits & self._p2):
                result.append(GlobalGate(index=i, qubits=qubits))
        return result


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def compute_teleportation_cost(
    gates: List[Gate],
    partition1: List[int],
    partition2: List[int],
    alpha: float = 3.0,
    beta: float = 1.0,
) -> int:
    """Compute the teleportation cost between two partitions.

    This is a convenience wrapper matching the signature of the original
    ``calculate_teleportation`` function.

    Args:
        gates: Full gate list.
        partition1: First partition (list of qubit indices).
        partition2: Second partition (list of qubit indices).
        alpha: Weight for mergeability (default 3).
        beta: Weight for return penalty (default 1).

    Returns:
        Total teleportation cost (number of EPR pairs).
    """
    grouper = TeleportationGrouper(gates, partition1, partition2, alpha, beta)
    if grouper.global_gate_count == 0:
        return 0
    return grouper.compute_cost()
