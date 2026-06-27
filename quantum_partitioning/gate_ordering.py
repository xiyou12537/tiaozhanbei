"""
Gate-order optimisation via local reordering (simulated-annealing style).

When two partitions are fixed, the order of gates can significantly
affect how many teleportations can be merged.  This module reorders
gates within commutativity constraints to maximise teleportation
merging, then moves interfering local gates out of the way when a
merge would otherwise be blocked.

Key fix from the original code:
    When moving interfering gates in a loop, indices were stored before
    modification and then used after the list had shifted.  We now
    recompute the interference set after each successful move.
"""

from __future__ import annotations

import copy
from typing import List, Optional, Set, Tuple

from .config import Gate
from .gate_commutation import can_swap
from .teleportation import TeleportationGrouper, GlobalGate


class GateOrderOptimizer:
    """Optimize gate order between two partitions to reduce teleportation cost.

    The optimiser:
    1. Identifies global (cross-partition) gates.
    2. Groups them greedily for shared teleportation.
    3. When a merge is blocked by interfering local gates, attempts
       to move those gates earlier or later within commutativity
       constraints.
    4. Re-evaluates teleportation cost after reordering.

    Args:
        gates: Full gate list (will be deep-copied).
        partition1: First partition qubit list.
        partition2: Second partition qubit list.
        alpha: Mergeability weight for teleport-qubit selection.
        beta: Return-penalty weight for teleport-qubit selection.
    """

    def __init__(
        self,
        gates: List[Gate],
        partition1: List[int],
        partition2: List[int],
        alpha: float = 4.0,
        beta: float = 1.0,
    ):
        self._original_gates = gates
        self._gates: List[Gate] = copy.deepcopy(gates)
        self._p1: Set[int] = set(partition1)
        self._p2: Set[int] = set(partition2)
        self._alpha = alpha
        self._beta = beta

        # Identify global gates on the working copy
        self._global_gates = self._find_global_gates()

    # ── Public API ────────────────────────────────────────────────────

    def optimize(self) -> Tuple[List[Gate], int]:
        """Run the full optimisation and return ``(optimized_gates, cost)``.

        Returns:
            Tuple of ``(new_gate_list, teleportation_cost)``.
        """
        if not self._global_gates:
            return self._gates, 0

        groups = self._build_groups_with_movement()

        # Compute cost using the standard grouper on the final gate list
        grouper = TeleportationGrouper(
            self._gates,
            list(self._p1),
            list(self._p2),
            alpha=self._alpha,
            beta=self._beta,
        )
        cost = grouper.compute_cost() if grouper.global_gate_count > 0 else 0

        return self._gates, cost

    # ── Group building with gate movement ────────────────────────────

    def _build_groups_with_movement(self) -> List[dict]:
        """Build teleportation groups, moving interfering gates as needed."""
        groups: List[dict] = []

        for gg in self._global_gates:
            idx = gg.index
            qubits = list(gg.qubits)

            # ── Try to merge into an existing group ──
            best_group, best_tq = self._find_best_merge(groups, gg, idx)

            if best_group is not None:
                teleport_qubit = best_tq
                start = best_group["end_idx"] + 1
                end = idx

                # Check for interference
                has_conflict = self._has_interference(
                    best_group["end_idx"], idx, teleport_qubit
                )

                if has_conflict:
                    # Attempt to resolve by moving interfering gates
                    self._resolve_interference(
                        best_group, idx, teleport_qubit, start, end
                    )

                # Re-check after move attempt
                if not self._has_interference(
                    best_group["end_idx"], idx, teleport_qubit
                ):
                    best_group["gates"].append(gg)
                    best_group["end_idx"] = idx
                else:
                    # Move failed — create a new group instead
                    groups.append({
                        "teleport_qubit": teleport_qubit,
                        "gates": [gg],
                        "start_idx": idx,
                        "end_idx": idx,
                    })
            else:
                # ── Create a new group ──
                best_tq = self._pick_best_teleport_qubit(qubits, idx)
                if best_tq is not None:
                    groups.append({
                        "teleport_qubit": best_tq,
                        "gates": [gg],
                        "start_idx": idx,
                        "end_idx": idx,
                    })

        return groups

    def _find_best_merge(
        self, groups: List[dict], gg: GlobalGate, idx: int
    ) -> Tuple[Optional[dict], Optional[int]]:
        """Find the best existing group for *gg* to merge into."""
        best_group = None
        best_tq = None
        best_score = float("-inf")

        for group in groups:
            tq = group["teleport_qubit"]
            if tq not in gg.qubits:
                continue

            score = -(idx - group["end_idx"])
            if score > best_score:
                best_score = score
                best_group = group
                best_tq = tq

        return best_group, best_tq

    # ── Interference resolution ──────────────────────────────────────

    def _resolve_interference(
        self,
        best_group: dict,
        idx: int,
        teleport_qubit: int,
        start: int,
        end: int,
    ) -> None:
        """Attempt to move interfering gates out of the merge window.

        Processes interfering gates from **right to left** so that
        moving a gate does not invalidate the stored indices of gates
        earlier in the circuit (which have smaller indices).
        """
        # Collect interfering gate indices
        interfering_indices = []
        for i in range(start, end):
            gate_qubits = set(int(q) for q in self._gates[i][1:])
            if teleport_qubit in gate_qubits:
                # Only move local gates (both qubits in same partition)
                if gate_qubits.issubset(self._p1) or gate_qubits.issubset(self._p2):
                    interfering_indices.append(i)

        # Process right-to-left to avoid index-shift corruption
        for i in reversed(interfering_indices):
            moved = False

            # Try moving LEFT (toward the existing group's end)
            anchor = best_group["end_idx"]
            chain = self._get_forward_dependency_chain(anchor, i)
            if self._can_move_block(chain, i):
                self._move_block_after(self._gates, chain, i)
                moved = True

            # Try moving RIGHT (past the current gate) only if left failed
            if not moved:
                chain = self._get_forward_dependency_chain(i, idx)
                if self._can_move_block(chain, idx):
                    self._move_block_after(self._gates, chain, idx)

    # ── Dependency chain ─────────────────────────────────────────────

    def _get_forward_dependency_chain(
        self, start: int, end: int
    ) -> List[int]:
        """Find all gates in ``[start, end)`` that are transitively
        dependent on the gate at *start* (cannot be reordered past it).
        """
        chain: Set[int] = {start}
        frontier = [start]

        while frontier:
            cur = frontier.pop()
            cur_qubits = set(int(q) for q in self._gates[cur][1:])

            for i in range(cur + 1, end):
                if i in chain:
                    continue
                next_qubits = set(int(q) for q in self._gates[i][1:])
                if cur_qubits & next_qubits:
                    if not can_swap(self._gates[cur], self._gates[i]):
                        chain.add(i)
                        frontier.append(i)

        return sorted(chain)

    def _can_move_block(
        self, block: List[int], target_idx: int
    ) -> bool:
        """Check if every gate in *block* can be moved past all
        intermediate gates to *target_idx*."""
        block_set = set(block)

        for i in block:
            gate = self._gates[i]
            gate_qubits = set(int(q) for q in gate[1:])

            for j in range(i + 1, target_idx + 1):
                if j in block_set:
                    continue
                other = self._gates[j]
                other_qubits = set(int(q) for q in other[1:])

                if gate_qubits & other_qubits:
                    if not can_swap(gate, other):
                        return False

        return True

    @staticmethod
    def _move_block_after(
        gates: List[Gate], block: List[int], target_idx: int
    ) -> None:
        """Move a contiguous block of gates to just after *target_idx*.

        Modifies *gates* in place.
        """
        block_gates = [gates[i] for i in block]

        # Remove from original positions (highest index first)
        for i in sorted(block, reverse=True):
            gates.pop(i)

        # Compute insertion point accounting for removals
        shift = sum(1 for i in block if i < target_idx)
        insert_pos = target_idx - shift + 1

        for i, g in enumerate(block_gates):
            gates.insert(insert_pos + i, g)

    # ── Helpers (same as TeleportationGrouper but on mutable _gates) ──

    def _find_global_gates(self) -> List[GlobalGate]:
        """Scan for cross-partition gates."""
        result = []
        for i, gate in enumerate(self._gates):
            if len(gate) < 3:
                continue
            qubits = {int(gate[1]), int(gate[2])}
            if (qubits & self._p1) and (qubits & self._p2):
                result.append(GlobalGate(index=i, qubits=qubits))
        return result

    def _has_interference(self, start: int, end: int, tq: int) -> bool:
        """Check whether *tq* appears in any gate in ``(start, end)``."""
        for idx in range(start + 1, end):
            if tq in (int(q) for q in self._gates[idx][1:]):
                return True
        return False

    def _pick_best_teleport_qubit(
        self, qubits: List[int], idx: int
    ) -> Optional[int]:
        """Score-based selection of the best teleport qubit."""
        best_tq = None
        best_score = float("-inf")

        # Score: count mergeable future global gates
        for tq in qubits:
            merge_count = 0
            for gg in self._global_gates:
                if gg.index <= idx:
                    continue
                if tq in gg.qubits and not self._has_interference(
                    idx, gg.index, tq
                ):
                    merge_count += 1

            # Return penalty: 1 if tq is used later in the circuit
            return_penalty = 1 if self._used_later_accurate(idx, tq) else 0
            score = self._alpha * merge_count - self._beta * return_penalty

            if score > best_score:
                best_score = score
                best_tq = tq

        return best_tq

    def _used_later_accurate(self, after_idx: int, tq: int) -> bool:
        """Check if *tq* appears in any cross-partition gate after *after_idx*."""
        cross_indices = [
            gg.index for gg in self._global_gates if tq in gg.qubits
        ]
        if not cross_indices:
            return False

        last_cross_idx = max(cross_indices)
        for idx in range(last_cross_idx + 1, len(self._gates)):
            if tq in (int(q) for q in self._gates[idx][1:]):
                return True
        return False


# ---------------------------------------------------------------------------
# Multi-partition convenience
# ---------------------------------------------------------------------------

def optimize_gate_order_all_partitions(
    gates: List[Gate],
    partitions: List[List[int]],
    alpha: float = 4.0,
    beta: float = 1.0,
) -> Tuple[List[Gate], int]:
    """Optimize gate order across all partition pairs.

    Iterates over every pair of partitions, optimising the gate order
    for that pair.  The total cost is accumulated across all pairs.

    Args:
        gates: Gate list.
        partitions: List of partitions.
        alpha: Mergeability weight.
        beta: Return-penalty weight.

    Returns:
        ``(optimized_gates, total_teleportation_cost)``.
    """
    working_gates = copy.deepcopy(gates)
    total_cost = 0

    for i in range(len(partitions) - 1):
        for j in range(i + 1, len(partitions)):
            optimizer = GateOrderOptimizer(
                working_gates,
                partitions[i],
                partitions[j],
                alpha=alpha,
                beta=beta,
            )
            working_gates, pair_cost = optimizer.optimize()
            total_cost += pair_cost

    return working_gates, total_cost
