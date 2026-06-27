"""
Circuit utility functions: gate filtering, qubit extraction, lifetime
analysis, interaction matrices, and colour-sequence helpers used by
the partitioning algorithms.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import permutations
from typing import Dict, List, Optional, Tuple, Set

from .config import Gate


# ── Gate filtering ────────────────────────────────────────────────────

def remove_single_qubit_gates(gates: List[Gate]) -> List[Gate]:
    """Return a new gate list with all single-qubit gates removed.

    Single-qubit gates have ``len(gate) == 2`` (i.e. ``[name, qubit]``).
    """
    return [g for g in gates if len(g) > 2]


# ── Qubit extraction ──────────────────────────────────────────────────

def extract_qubits(gates: List[Gate]) -> List[int]:
    """Return a sorted list of every qubit index that appears in *gates*."""
    qubits: Set[int] = set()
    for gate in gates:
        for q in gate[1:]:
            qubits.add(int(q))
    return sorted(qubits)


# ── Lifetime analysis ─────────────────────────────────────────────────

def compute_qubit_lifetimes(
    gates: List[Gate], num_qubits: int
) -> List[Tuple[int, int]]:
    """Compute the ``(first_gate_idx, last_gate_idx)`` for each qubit.

    Args:
        gates: Gate list.
        num_qubits: Total number of qubits.

    Returns:
        A list of length *num_qubits* where entry *i* is
        ``(start_time, end_time)``.  A value of ``-1`` means the qubit
        is never touched.
    """
    times: List[Tuple[int, int]] = [(-1, -1) for _ in range(num_qubits)]

    for t, gate in enumerate(gates):
        for q in gate[1:]:
            q = int(q)
            if times[q][0] == -1:
                times[q] = (t, t)
            else:
                times[q] = (times[q][0], t)

    return times


def find_reuse_pairs_from_lifetimes(
    lifetimes: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Find qubit pairs ``(i, j)`` where *i* finishes before *j* starts.

    Such pairs are candidates for physical qubit reuse.
    """
    pairs: List[Tuple[int, int]] = []
    n = len(lifetimes)
    for i in range(n):
        for j in range(i + 1, n):
            if lifetimes[i][1] != -1 and lifetimes[j][0] != -1:
                if lifetimes[i][1] < lifetimes[j][0]:
                    pairs.append((i, j))
    return pairs


def find_possible_reuse_pairs(
    gates: List[Gate], qubits: List[int]
) -> List[Tuple[int, int]]:
    """Find qubit-reuse pairs by scanning gate order.

    A pair ``(a, b)`` is *possible* if *a*'s last appearance precedes
    *b*'s first appearance **and** the pair is not already present as a
    gate (in either order).

    Args:
        gates: Gate list.
        qubits: List of qubit indices to consider.

    Returns:
        List of ``(reused_qubit, reusing_qubit)`` pairs.
    """
    # Build all ordered permutations
    possible_pairs = [tuple(p) for p in permutations(qubits, 2)]

    # Build a set of existing qubit pairs for fast lookup.
    # A qubit pair appears in a gate when len(gate) >= 3 and the last
    # two elements are qubit indices.
    existing_pairs: Set[Tuple[int, int]] = set()
    for g in gates:
        if len(g) >= 3:
            a, b = int(g[1]), int(g[2])
            existing_pairs.add((a, b))
            existing_pairs.add((b, a))

    # Filter: remove pairs that already exist as a gate
    filtered = [p for p in possible_pairs if p not in existing_pairs]

    result: List[Tuple[int, int]] = []
    for a, b in filtered:
        head = 0
        tail = len(gates) - 1

        # Find first gate that touches b
        while head < len(gates):
            gate_qubits = [int(q) for q in gates[head][1:]]
            if b in gate_qubits:
                break
            head += 1

        # Find last gate that touches a
        while tail >= 0:
            gate_qubits = [int(q) for q in gates[tail][1:]]
            if a in gate_qubits:
                break
            tail -= 1

        if head > tail:
            result.append((a, b))

    return result


# ── Gate-index maps ───────────────────────────────────────────────────

def compute_qubit_gate_map(
    gates: List[Gate],
    bit2partition: Optional[Dict[int, str]] = None,
) -> Dict[int, List[int]]:
    """Build a mapping from qubit index → list of gate indices.

    Args:
        gates: Gate list.
        bit2partition: If provided, local (same-partition) two-qubit
            gates are mapped to key ``-1`` instead of their qubit
            indices.  This keeps them out of cross-partition analysis.

    Returns:
        Dict keyed by qubit index (or ``-1`` for local gates).
    """
    mapping: Dict[int, List[int]] = defaultdict(list)

    for idx, gate in enumerate(gates):
        if len(gate) == 2:
            _, q = gate
            mapping[int(q)].append(idx)
        elif len(gate) == 3:
            _, q1, q2 = gate
            q1, q2 = int(q1), int(q2)
            if bit2partition and bit2partition.get(q1) == bit2partition.get(q2):
                mapping[-1].append(idx)
            else:
                mapping[q1].append(idx)
                mapping[q2].append(idx)
        # Single-qubit gates (len == 2) handled above; rswap and others
        # with len != 2,3 are silently excluded.

    return dict(mapping)


def compute_interaction_matrix(
    gates: List[Gate],
) -> Dict[int, Dict[int, int]]:
    """Build a symmetric interaction count matrix between qubits.

    For every two-qubit gate ``[name, q1, q2]``, increment
    ``matrix[q1][q2]`` and ``matrix[q2][q1]`` by 1.

    Returns:
        Nested dict ``{qubit: {other_qubit: count}}``.
    """
    interaction: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for gate in gates:
        if len(gate) >= 3:
            q1, q2 = int(gate[1]), int(gate[2])
            interaction[q1][q2] += 1
            interaction[q2][q1] += 1
    return {k: dict(v) for k, v in interaction.items()}


# ── Colour-sequence helpers ───────────────────────────────────────────

def compute_coloured_sequence(
    qubit_gate_map: Dict[int, List[int]],
    candidate_qubits: List[int],
) -> List[int]:
    """Build a time-ordered "colour" sequence for a set of qubits.

    Each gate index touched by any candidate qubit is tagged with the
    qubit id, then the tags are sorted by gate index.

    Returns:
        List of qubit ids in time order.
    """
    colour_sequence: List[Tuple[int, int]] = []
    for q in candidate_qubits:
        for idx in qubit_gate_map.get(q, []):
            colour_sequence.append((idx, q))
    colour_sequence.sort(key=lambda x: x[0])
    return [q for _, q in colour_sequence]


def count_colour_segments(colour_sequence: List[int]) -> int:
    """Count how many times the colour changes in the sequence.

    Lower counts mean the qubits in the candidate set are more
    temporally clustered — a desirable property for a partition.
    """
    if not colour_sequence:
        return 0
    count = 1
    for i in range(1, len(colour_sequence)):
        if colour_sequence[i] != colour_sequence[i - 1]:
            count += 1
    return count


# ── Global gate evaluation ────────────────────────────────────────────

def evaluate_global_gates_all_partitions(
    partitions: List[List[int]],
    gates: List[Gate],
) -> int:
    """Count the total number of cross-partition two-qubit gates.

    Args:
        partitions: List of partitions, each a list of qubit indices.
        gates: Gate list.

    Returns:
        Total count of gates whose qubits belong to different partitions.
    """
    qubit_to_partition: Dict[int, int] = {}
    for pid, partition in enumerate(partitions):
        for q in partition:
            qubit_to_partition[q] = pid

    total = 0
    for gate in gates:
        if len(gate) < 3:
            continue
        q1, q2 = int(gate[1]), int(gate[2])
        p1 = qubit_to_partition.get(q1, -1)
        p2 = qubit_to_partition.get(q2, -1)
        if p1 != -1 and p2 != -1 and p1 != p2:
            total += 1

    return total
