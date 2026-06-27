"""
Remote-SWAP optimisation for distributed quantum circuits.

After partitions are mapped to physical chips, we can further reduce
the EPR-pair cost by inserting "rswap" (remote-SWAP) gates that
exchange the logical-to-physical qubit assignment across two chips.

The optimisation loop:
    For each edge in the physical chip graph:
        For each pair of partitions mapped to those chips:
            1. Score candidate qubit pairs for swapping.
            2. Find the best insertion point for each rswap.
            3. Simulate the swap and globally re-evaluate EPR cost.
            4. Accept if cost decreases; repeat until convergence.

This module was originally in a large commented-out block in main.py.
It has been cleaned up, with dead code removed and the ``interval``
undefined-variable bug fixed.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from .config import (
    Gate,
    PartitionToChip,
    QubitToPartition,
    RSWAP_GATE,
    DEFAULT_SWAP_MAX_ITERATIONS,
    DEFAULT_SWAP_TOP_K,
)
from .chip_mapping import compute_total_epr_cost


# ---------------------------------------------------------------------------
# Interaction analysis
# ---------------------------------------------------------------------------

def analyze_cross_partition_interactions(
    gates: List[Gate],
    part_a: List[int],
    part_b: List[int],
) -> Tuple[Dict[int, int], Dict[int, int]]:
    """Count remote and local gates for qubits in *part_a* vs *part_b*.

    Args:
        gates: Gate list.
        part_a: First partition.
        part_b: Second partition.

    Returns:
        ``(remote_count, local_count)`` where each is
        ``{qubit: count}`` for qubits in *part_a*.
    """
    set_a = set(part_a)
    set_b = set(part_b)
    remote = defaultdict(int)
    local = defaultdict(int)

    for gate in gates:
        qubits = [int(q) for q in gate[1:]]
        qs = set(qubits)

        if qs & set_a and qs & set_b:
            # Cross-partition gate: count qubits in part_a
            for q in qs & set_a:
                remote[q] += 1
        elif qs <= set_a:
            # Local gate within part_a
            for q in qs:
                local[q] += 1

    return dict(remote), dict(local)


# ---------------------------------------------------------------------------
# Swap candidate selection
# ---------------------------------------------------------------------------

def select_swap_candidates(
    gates: List[Gate],
    part_a: List[int],
    part_b: List[int],
    alpha: float = 1.0,
    beta: float = 1.0,
    top_k: int = DEFAULT_SWAP_TOP_K,
) -> List[Tuple[int, int]]:
    """Rank the top-K ``(qubit_a, qubit_b)`` pairs to consider for rswap.

    Score = ``alpha * (remote_a[q] + remote_b[p])
            - beta  * (local_a[q] + local_b[p])``

    Higher scores mean the pair is a good swap candidate:
    swapping qubits with many remote gates and few local gates
    can reduce global communication.

    Args:
        gates: Gate list.
        part_a: First partition.
        part_b: Second partition.
        alpha: Remote-gate weight.
        beta: Local-gate penalty weight.
        top_k: Number of top candidates to return.

    Returns:
        Sorted list of ``(qubit_a, qubit_b)`` pairs (best first).
    """
    remote_a, local_a = analyze_cross_partition_interactions(gates, part_a, part_b)
    remote_b, local_b = analyze_cross_partition_interactions(gates, part_b, part_a)

    scores: List[Tuple[float, int, int]] = []
    for q in part_a:
        for p in part_b:
            score = (
                alpha * (remote_a.get(q, 0) + remote_b.get(p, 0))
                - beta * (local_a.get(q, 0) + local_b.get(p, 0))
            )
            scores.append((score, q, p))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [(q, p) for _, q, p in scores[:top_k]]


# ---------------------------------------------------------------------------
# Best swap insertion point
# ---------------------------------------------------------------------------

def find_best_swap_insertion(
    gates: List[Gate],
    qa: int,
    qb: int,
    qubit_to_partition: QubitToPartition,
    part_a: Set[int],
    part_b: Set[int],
    cost_remote: float = 1.0,
    cost_swap: float = 1.0,
) -> Tuple[Optional[int], float]:
    """Find the optimal circuit position to insert an rswap between *qa* and *qb*.

    The heuristic computes, for each gate touching *qa* or *qb*, how
    swapping them would change the remote/local gate count, then uses
    a suffix-sum to find the insertion point with maximum net gain.

    Args:
        gates: Gate list.
        qa: Qubit in partition A.
        qb: Qubit in partition B.
        qubit_to_partition: Qubit → partition mapping.
        part_a: Partition A qubit set.
        part_b: Partition B qubit set.
        cost_remote: Reward per converted remote gate.
        cost_swap: Penalty per rswap insertion.

    Returns:
        ``(insert_index, gain)``.  *insert_index* is the position
        in the gate list to insert the rswap.  Returns
        ``(None, 0)`` if no beneficial position exists.
    """
    relevant: List[Tuple[int, float]] = []

    for idx, gate in enumerate(gates):
        qs = {int(q) for q in gate[1:]}
        if qa not in qs and qb not in qs:
            continue

        delta = 0.0

        # Effect of swapping qa
        if qa in qs:
            others = qs - {qa}
            if others:
                other = next(iter(others))
                if other in part_b:
                    delta += 1.0  # gain: remote → local
                elif other in part_a:
                    delta -= 1.0  # loss: local → remote

        # Effect of swapping qb
        if qb in qs:
            others = qs - {qb}
            if others:
                other = next(iter(others))
                if other in part_a:
                    delta += 1.0
                elif other in part_b:
                    delta -= 1.0

        relevant.append((idx, delta))

    if not relevant:
        return None, 0.0

    deltas = [d for _, d in relevant]
    k = len(deltas)

    # Suffix sum
    suffix = [0.0] * (k + 1)
    for i in range(k - 1, -1, -1):
        suffix[i] = suffix[i + 1] + deltas[i]

    best_k = 0
    best_gain = float("-inf")

    for m in range(k):
        gain = suffix[m] * cost_remote - cost_swap
        if gain > best_gain:
            best_gain = gain
            best_k = m

    insert_idx = relevant[best_k][0]
    return insert_idx, best_gain


# ---------------------------------------------------------------------------
# Main optimisation loop
# ---------------------------------------------------------------------------

def optimize_remote_swaps(
    gates: List[Gate],
    partitions: List[List[int]],
    qubit_to_partition: QubitToPartition,
    partition_to_chip: PartitionToChip,
    chip_graph: nx.Graph,
    max_iterations: int = DEFAULT_SWAP_MAX_ITERATIONS,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> List[dict]:
    """Iteratively insert rswap gates to reduce total EPR cost.

    For each edge in the chip graph, candidate qubit swaps between the
    mapped partitions are evaluated.  A swap is accepted if the
    simulated total EPR cost decreases.

    **Fixes from the original commented-out code:**
    - Removed unreachable dead code after ``break``.
    - Removed references to undefined ``interval`` variable.
    - Uses explicit parameter passing (no global state).

    Args:
        gates: Gate list.
        partitions: All partitions.
        qubit_to_partition: Qubit → partition id mapping.
        partition_to_chip: Partition → chip id mapping.
        chip_graph: Physical chip topology.
        max_iterations: Max optimisation iterations.
        alpha: Remote-gate weight for candidate selection.
        beta: Local-gate penalty for candidate selection.

    Returns:
        List of swap events, each ``{"idx": int, "q1": int, "q2": int}``.
    """
    swap_events: List[dict] = []
    current_map = dict(qubit_to_partition)
    current_gates = list(gates)

    current_cost = compute_total_epr_cost(
        current_gates,
        partitions,
        current_map,
        partition_to_chip,
        chip_graph,
    )

    improved = True
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        for chip_a, chip_b in chip_graph.edges():
            # Find partitions mapped to these chips
            parts_a = [p for p, c in partition_to_chip.items() if c == chip_a]
            parts_b = [p for p, c in partition_to_chip.items() if c == chip_b]

            for part_name_a in parts_a:
                for part_name_b in parts_b:
                    # Resolve partition name → qubit list
                    idx_a = int(part_name_a[1:]) - 1  # "P1" → 0
                    idx_b = int(part_name_b[1:]) - 1
                    part_a = partitions[idx_a]
                    part_b = partitions[idx_b]

                    candidates = select_swap_candidates(
                        current_gates, part_a, part_b, alpha=alpha, beta=beta
                    )

                    for q, p in candidates:
                        insert_idx, gain = find_best_swap_insertion(
                            current_gates,
                            q,
                            p,
                            current_map,
                            set(part_a),
                            set(part_b),
                        )

                        if insert_idx is None or gain <= 0:
                            continue

                        # Simulate swap
                        test_map = dict(current_map)
                        test_map[q], test_map[p] = test_map[p], test_map[q]

                        test_gates = list(current_gates)
                        test_gates.insert(insert_idx, [RSWAP_GATE, q, p])

                        new_cost = compute_total_epr_cost(
                            test_gates,
                            partitions,
                            test_map,
                            partition_to_chip,
                            chip_graph,
                        )

                        if new_cost < current_cost:
                            swap_events.append({
                                "idx": insert_idx,
                                "q1": q,
                                "q2": p,
                            })
                            current_map = test_map
                            current_gates = test_gates
                            current_cost = new_cost
                            improved = True
                            break

                    if improved:
                        break
                if improved:
                    break
            if improved:
                break

    return swap_events


# ---------------------------------------------------------------------------
# Apply swap events to gate list
# ---------------------------------------------------------------------------

def apply_swap_events_to_gates(
    gates: List[Gate], swap_events: List[dict]
) -> List[Gate]:
    """Insert rswap gates into a gate list according to *swap_events*.

    Events are processed in reverse index order so that earlier
    insertions do not shift later indices.

    Args:
        gates: Original gate list.
        swap_events: List of ``{"idx": int, "q1": int, "q2": int}``.

    Returns:
        New gate list with rswap gates inserted.
    """
    result = list(gates)
    for ev in sorted(swap_events, key=lambda x: x["idx"], reverse=True):
        result.insert(ev["idx"], [RSWAP_GATE, ev["q1"], ev["q2"]])
    return result


def apply_rswap_semantics(gates: List[Gate]) -> List[Gate]:
    """Apply rswap renaming semantics to the gate list.

    Each rswap gate swaps the logical identities of its two qubits.
    All subsequent gates see the swapped identities.

    Args:
        gates: Gate list that may contain rswap gates.

    Returns:
        Gate list with qubit indices resolved through the rename map.
    """
    rename: Dict[int, int] = {}
    result: List[Gate] = []

    def resolve(q: int) -> int:
        return rename.get(q, q)

    for gate in gates:
        if gate[0] == RSWAP_GATE:
            q1, q2 = int(gate[1]), int(gate[2])
            r1, r2 = resolve(q1), resolve(q2)
            # Swap the mapping
            rename[r1], rename[r2] = r2, r1
            result.append([RSWAP_GATE, r1, r2])
        else:
            new_gate = [gate[0]] + [resolve(int(q)) for q in gate[1:]]
            result.append(new_gate)

    return result
