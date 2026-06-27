"""
Chip-topology mapping via subgraph isomorphism.

After partitioning, each logical partition must be assigned to a
physical chip.  The chips are connected by a target topology graph
(ring, grid, star, etc.).  The mapping problem is:

    Find a subgraph monomorphism from the target chip graph into
    the complete partition-interaction graph that minimises the
    total EPR-pair cost.

The EPR cost accounts for:
- Directly-connected partitions: cost = weight (number of global gates).
- Multi-hop partitions: cost = weight × (2 × distance − 1).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
from networkx.algorithms import isomorphism

from .config import Gate, PartitionToChip, QubitToPartition, RSWAP_GATE
from .teleportation import TeleportationGrouper


# ---------------------------------------------------------------------------
# Partition interaction graph
# ---------------------------------------------------------------------------

def build_partition_interaction_graph(
    partitions: List[List[int]],
    gates: List[Gate],
) -> Tuple[nx.Graph, Dict[Tuple[str, str], int]]:
    """Build a complete weighted graph where nodes are partitions and
    edge weights are the number of cross-partition gates.

    Args:
        partitions: List of partitions.
        gates: Gate list.

    Returns:
        ``(graph, edge_costs)``.  *graph* is a ``networkx.Graph``
        with edge attribute ``weight``.  *edge_costs* is a dict
        ``{(pid_i, pid_j): count}``.
    """
    # qubit → partition id
    qubit_to_pid: Dict[int, int] = {}
    for pid, part in enumerate(partitions):
        for q in part:
            qubit_to_pid[q] = pid

    # Count cross-partition gates
    edge_costs: Dict[Tuple[int, int], int] = defaultdict(int)

    for gate in gates:
        if len(gate) < 3:
            continue
        q1, q2 = int(gate[1]), int(gate[2])
        p1 = qubit_to_pid.get(q1, -1)
        p2 = qubit_to_pid.get(q2, -1)
        if p1 != -1 and p2 != -1 and p1 != p2:
            i, j = (p1, p2) if p1 < p2 else (p2, p1)
            edge_costs[(i, j)] += 1

    # Build graph
    graph = nx.Graph()
    n = len(partitions)
    for i in range(n):
        graph.add_node(f"P{i + 1}")

    # Ensure complete graph (add zero-weight edges for missing pairs)
    str_costs: Dict[Tuple[str, str], int] = {}
    for i, j in combinations(range(n), 2):
        w = edge_costs.get((i, j), 0)
        graph.add_edge(f"P{i + 1}", f"P{j + 1}", weight=w)
        str_costs[(f"P{i + 1}", f"P{j + 1}")] = w

    return graph, str_costs


# ---------------------------------------------------------------------------
# Target graph parsing (safe — no eval)
# ---------------------------------------------------------------------------

def parse_target_topology(edges: List[Tuple[int, int]]) -> nx.Graph:
    """Create a target chip graph from an edge list.

    Args:
        edges: List of ``(chip_i, chip_j)`` tuples (1-indexed).

    Returns:
        A ``networkx.Graph`` with nodes labelled ``"T1"``, ``"T2"``, ...

    Example:
        >>> g = parse_target_topology([(0,1), (1,2), (2,0)])  # 3-node ring
    """
    graph = nx.Graph()
    for u, v in edges:
        graph.add_edge(f"T{u + 1}", f"T{v + 1}")
    return graph


def parse_target_topology_from_string(edge_str: str) -> Optional[nx.Graph]:
    """Parse a target topology from a user-provided string.

    Uses ``ast.literal_eval`` for safe parsing (no ``eval()``).

    Args:
        edge_str: String like ``"[(0,1),(1,2),(2,0)]"``.

    Returns:
        A ``networkx.Graph``, or ``None`` on parse error.
    """
    try:
        edges = ast.literal_eval(edge_str)
        if not isinstance(edges, list):
            return None
        return parse_target_topology(edges)
    except (ValueError, SyntaxError):
        return None


# ---------------------------------------------------------------------------
# Subgraph-monomorphism search
# ---------------------------------------------------------------------------

def find_chip_mapping(
    complete_graph: nx.Graph,
    target_graph: nx.Graph,
) -> Tuple[Optional[PartitionToChip], float]:
    """Find the optimal mapping of partitions to physical chips.

    Searches all subgraph monomorphisms from *target_graph* into
    *complete_graph*, evaluating each by total EPR cost.

    Args:
        complete_graph: Complete weighted partition-interaction graph.
        target_graph: Target chip-topology graph.

    Returns:
        ``(mapping, min_cost)`` where *mapping* is
        ``{chip_id: partition_id}`` and *min_cost* is the total
        cost.  Returns ``(None, inf)`` if no valid mapping exists.
    """
    gm = isomorphism.GraphMatcher(complete_graph, target_graph)

    matches: List[Tuple[PartitionToChip, float]] = []

    for sub_mapping in gm.subgraph_monomorphisms_iter():
        # Determine mapping direction:
        # sub_mapping will be {complete_node: target_node} or vice versa
        first_key = next(iter(sub_mapping))
        if first_key in complete_graph.nodes():
            mapping = {v: k for k, v in sub_mapping.items()}
        else:
            mapping = sub_mapping

        # Build the physical subgraph induced by this mapping
        sub_nodes = list(mapping.values())
        subgraph = nx.Graph()
        subgraph.add_nodes_from(sub_nodes)
        for u, v in target_graph.edges():
            if u in mapping and v in mapping:
                pu, pv = mapping[u], mapping[v]
                subgraph.add_edge(pu, pv)

        # Evaluate cost
        total_cost = 0.0
        valid = True

        for (i, j), data in complete_graph.edges.items():
            w = data.get("weight", 0)
            if w == 0:
                continue

            # Skip edges involving partitions not in this mapping
            if i not in subgraph or j not in subgraph:
                continue

            if subgraph.has_edge(i, j):
                total_cost += w
            else:
                try:
                    d = nx.shortest_path_length(subgraph, i, j)
                    total_cost += w * (2 * d - 1)
                except nx.NetworkXNoPath:
                    valid = False
                    break

        if valid:
            matches.append((mapping, total_cost))

    if not matches:
        return None, float("inf")

    best_mapping, min_cost = min(matches, key=lambda x: x[1])
    return best_mapping, min_cost


# ---------------------------------------------------------------------------
# EPR cost with physical distance
# ---------------------------------------------------------------------------

def compute_epr_cost(
    gates: List[Gate],
    partition1: List[int],
    partition2: List[int],
    qubit_to_partition: QubitToPartition,
    partition_to_chip: PartitionToChip,
    chip_graph: nx.Graph,
    alpha: float = 3.0,
    beta: float = 1.0,
) -> int:
    """Compute the EPR-pair cost between two partitions accounting for
    physical chip distance.

    Args:
        gates: Gate list.
        partition1: First partition qubits.
        partition2: Second partition qubits.
        qubit_to_partition: Maps qubit → partition id (e.g. ``"P1"``).
        partition_to_chip: Maps partition id → chip id (e.g. ``"T1"``).
        chip_graph: Physical chip topology.
        alpha: Mergeability weight.
        beta: Return-penalty weight.

    Returns:
        Total EPR-pair cost for this partition pair.
    """
    p1_set = set(partition1)
    p2_set = set(partition2)

    # ── 0. rswap cost accumulation ──
    rswap_cost = 0
    rswap_indices: Set[int] = set()

    for i, gate in enumerate(gates):
        if gate[0] != RSWAP_GATE:
            continue
        q1, q2 = int(gate[1]), int(gate[2])
        crossed = (q1 in p1_set and q2 in p2_set) or (
            q1 in p2_set and q2 in p1_set
        )
        if crossed:
            rswap_cost += 3
            rswap_indices.add(i)

    # ── 1. Find cross-partition gates (excluding rswap) ──
    global_gates = []
    for i, gate in enumerate(gates):
        if gate[0] == RSWAP_GATE:
            continue
        if len(gate) < 3:
            continue
        qubits = {int(gate[1]), int(gate[2])}
        if (qubits & p1_set) and (qubits & p2_set):
            global_gates.append({"index": i, "qubits": qubits})

    if not global_gates:
        return rswap_cost

    # ── 2. Helper functions (using local gate list) ──

    def has_interference(start: int, end: int, tq: int) -> bool:
        for idx in range(start + 1, end):
            if idx in rswap_indices:
                return True
            if tq in (int(q) for q in gates[idx][1:]):
                return True
        return False

    def used_later(after_idx: int, tq: int) -> bool:
        for idx in range(after_idx + 1, len(gates)):
            if idx in rswap_indices:
                return False
            if tq in (int(q) for q in gates[idx][1:]):
                return True
        return False

    def score_teleport_qubit(tq: int, current_idx: int) -> int:
        count = 0
        for g in global_gates:
            if g["index"] <= current_idx:
                continue
            if g["index"] in rswap_indices:
                continue
            if tq in g["qubits"] and not has_interference(
                current_idx, g["index"], tq
            ):
                count += 1
        return count

    def _overlaps(s1: int, e1: int, s2: int, e2: int) -> bool:
        return not (e1 < s2 or e2 < s1)

    def has_time_conflict(
        new_start: int, new_end: int, exclude_group: Optional[dict] = None
    ) -> bool:
        for group in groups:
            if group is exclude_group:
                continue
            if _overlaps(
                new_start, new_end,
                group["start_idx"], group["end_idx"],
            ):
                return True
        return False

    # ── 3. Build teleportation groups ──
    groups: List[dict] = []

    for g in global_gates:
        idx = g["index"]
        qubits = list(g["qubits"])

        # Try to merge
        best_group = None
        best_score = float("-inf")

        for group in groups:
            tq = group["teleport_qubit"]
            if any(r in rswap_indices for r in range(group["end_idx"] + 1, idx)):
                continue
            if tq not in g["qubits"]:
                continue
            if has_interference(group["end_idx"], idx, tq):
                continue
            if has_time_conflict(group["start_idx"], idx, exclude_group=group):
                continue

            score = -(idx - group["end_idx"])
            if score > best_score:
                best_score = score
                best_group = group

        if best_group is not None:
            best_group["gates"].append(g)
            best_group["end_idx"] = idx
        else:
            best_tq = None
            best_score = float("-inf")

            for tq in qubits:
                mergeability = score_teleport_qubit(tq, idx)
                return_penalty = 1 if used_later(idx, tq) else 0
                score = alpha * mergeability - beta * return_penalty
                if score > best_score:
                    best_score = score
                    best_tq = tq

            if best_tq is not None:
                groups.append({
                    "teleport_qubit": best_tq,
                    "gates": [g],
                    "start_idx": idx,
                    "end_idx": idx,
                })

    # ── 4. Compute EPR cost with distance ──
    total_epr = rswap_cost

    for group in groups:
        k = len(group["gates"])
        tq = group["teleport_qubit"]

        # qubit → partition → chip
        src_pid = qubit_to_partition[tq]

        # Determine destination partition
        ref_q = next(iter(p1_set))
        if src_pid == qubit_to_partition[ref_q]:
            # Source is partition1 → destination is partition2
            dst_ref = next(iter(p2_set))
        else:
            dst_ref = next(iter(p1_set))

        dst_pid = qubit_to_partition[dst_ref]

        c1 = partition_to_chip.get(src_pid)
        c2 = partition_to_chip.get(dst_pid)

        if c1 is None or c2 is None or c1 == c2:
            continue

        try:
            d = nx.shortest_path_length(chip_graph, c1, c2)
        except nx.NetworkXNoPath:
            continue

        if k == 1:
            total_epr += (2 * d - 1)
        else:
            if used_later(group["end_idx"], tq):
                total_epr += 2 * d
            else:
                total_epr += d

    return total_epr


def compute_total_epr_cost(
    gates: List[Gate],
    partitions: List[List[int]],
    qubit_to_partition: QubitToPartition,
    partition_to_chip: PartitionToChip,
    chip_graph: nx.Graph,
    alpha: float = 3.0,
    beta: float = 1.0,
) -> int:
    """Sum ``compute_epr_cost`` over all partition pairs.

    Args:
        gates: Gate list.
        partitions: All partitions.
        qubit_to_partition: Qubit → partition mapping.
        partition_to_chip: Partition → chip mapping.
        chip_graph: Physical chip topology graph.
        alpha: Mergeability weight.
        beta: Return-penalty weight.

    Returns:
        Total EPR-pair cost across the whole system.
    """
    total = 0
    n = len(partitions)
    for i in range(n):
        for j in range(i + 1, n):
            total += compute_epr_cost(
                gates=gates,
                partition1=partitions[i],
                partition2=partitions[j],
                qubit_to_partition=qubit_to_partition,
                partition_to_chip=partition_to_chip,
                chip_graph=chip_graph,
                alpha=alpha,
                beta=beta,
            )
    return total
