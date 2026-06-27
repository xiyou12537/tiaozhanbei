"""
Visualization utilities for quantum circuit partitioning.

All functions provide **data-only** outputs (dicts) suitable for
web-based rendering.  Optional matplotlib-based renderers are
provided but use the ``Agg`` backend so they never block or open
GUI windows.
"""

from __future__ import annotations

import io
from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — no GUI required

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from .config import Gate


# ---------------------------------------------------------------------------
# Data builders (web-friendly, no matplotlib)
# ---------------------------------------------------------------------------

def build_partition_graph_data(
    partitions: List[List[int]],
    gates: List[Gate],
) -> Dict[str, Any]:
    """Build a JSON-serialisable representation of the partition
    interaction graph.

    Args:
        partitions: List of partitions.
        gates: Gate list.

    Returns:
        Dict with keys ``nodes``, ``edges``, and ``edge_costs``.
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

    n = len(partitions)

    nodes = [
        {"id": f"P{i + 1}", "label": f"Partition {i + 1}",
         "size": len(partitions[i])}
        for i in range(n)
    ]

    edges = []
    cost_dict = {}
    for i, j in combinations(range(n), 2):
        w = edge_costs.get((i, j), 0)
        edges.append({
            "source": f"P{i + 1}",
            "target": f"P{j + 1}",
            "weight": w,
        })
        cost_dict[f"P{i + 1}-P{j + 1}"] = w

    return {"nodes": nodes, "edges": edges, "edge_costs": cost_dict}


def build_mapping_data(
    complete_graph: nx.Graph,
    target_graph: nx.Graph,
    mapping: Dict[str, str],
    cost: float,
) -> Dict[str, Any]:
    """Build a JSON-serialisable representation of a chip-mapping result.

    Args:
        complete_graph: Weighted partition-interaction graph.
        target_graph: Physical chip topology graph.
        mapping: ``{chip_id: partition_id}``.
        cost: Total EPR cost of this mapping.

    Returns:
        Dict with ``mapping``, ``cost``, ``subgraph_nodes``,
        ``subgraph_edges``, ``all_nodes``, and ``all_edges``.
    """
    return {
        "mapping": mapping,
        "cost": cost,
        "subgraph_nodes": list(mapping.values()),
        "subgraph_edges": [
            (mapping[u], mapping[v])
            for u, v in target_graph.edges()
        ],
        "all_nodes": list(complete_graph.nodes()),
        "all_edges": [
            {"source": u, "target": v, "weight": d.get("weight", 0)}
            for u, v, d in complete_graph.edges(data=True)
        ],
    }


# ---------------------------------------------------------------------------
# Matplotlib renderers (return PNG bytes)
# ---------------------------------------------------------------------------

def render_partition_graph(
    partitions: List[List[int]],
    gates: List[Gate],
    title: str = "Partition Interaction Graph",
) -> bytes:
    """Render the partition interaction graph as a PNG image.

    Args:
        partitions: List of partitions.
        gates: Gate list.
        title: Plot title.

    Returns:
        PNG image bytes.
    """
    data = build_partition_graph_data(partitions, gates)

    graph = nx.Graph()
    for node in data["nodes"]:
        graph.add_node(node["id"])
    for edge in data["edges"]:
        graph.add_edge(edge["source"], edge["target"], weight=edge["weight"])

    pos = nx.circular_layout(graph)
    fig, ax = plt.subplots(figsize=(8, 6))
    nx.draw(graph, pos, with_labels=True, node_size=800,
            node_color="lightblue", font_size=12, ax=ax)

    edge_labels = nx.get_edge_attributes(graph, "weight")
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, ax=ax)

    ax.set_title(title)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_mapping_visualization(
    complete_graph: nx.Graph,
    target_graph: nx.Graph,
    mapping: Dict[str, str],
    cost: float,
    title: str = "Best Subgraph Match",
) -> bytes:
    """Render the chip-mapping result as a PNG image.

    Args:
        complete_graph: Weighted partition-interaction graph.
        target_graph: Physical chip topology.
        mapping: ``{chip_id: partition_id}``.
        cost: Total cost.
        title: Plot title.

    Returns:
        PNG image bytes.
    """
    pos = nx.circular_layout(complete_graph)
    fig, ax = plt.subplots(figsize=(12, 8))

    # Draw complete graph (background)
    nx.draw(complete_graph, pos, node_color="lightgrey",
            edge_color="lightgrey", with_labels=True, alpha=0.5,
            node_size=500, ax=ax)

    # Highlight mapped nodes and edges
    sub_nodes = list(mapping.values())
    nx.draw_networkx_nodes(complete_graph, pos, nodelist=sub_nodes,
                           node_color="lightgreen", node_size=800, ax=ax)

    sub_edges = [
        (mapping[u], mapping[v])
        for u, v in target_graph.edges()
        if u in mapping and v in mapping
    ]
    if sub_edges:
        nx.draw_networkx_edges(complete_graph, pos, edgelist=sub_edges,
                               width=3, edge_color="green", alpha=0.8, ax=ax)

    edge_labels = nx.get_edge_attributes(complete_graph, "weight")
    nx.draw_networkx_edge_labels(complete_graph, pos,
                                 edge_labels=edge_labels, ax=ax)

    ax.set_title(f"{title} (Cost: {cost})")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_parameter_landscape(
    b1_list: List[float],
    b2_list: List[float],
    teleport_grid: Dict[Tuple[float, float], int],
    title: str = "Parameter Landscape",
) -> bytes:
    """Render a 3D wireframe of teleportation counts over (b1, b2).

    Args:
        b1_list: b1 values tried.
        b2_list: b2 values tried.
        teleport_grid: ``{(b1, b2): teleport_count}``.
        title: Plot title.

    Returns:
        PNG image bytes.
    """
    x_vals, y_vals = np.meshgrid(b2_list, b1_list)
    z_vals = np.zeros_like(x_vals, dtype=float)

    for i, b1 in enumerate(b1_list):
        for j, b2 in enumerate(b2_list):
            z_vals[i, j] = teleport_grid.get((b1, b2), np.nan)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_wireframe(x_vals, y_vals, z_vals, rstride=1, cstride=1)

    ax.set_xlabel("b2")
    ax.set_ylabel("b1")
    ax.set_zlabel("Teleportations")
    ax.set_title(title)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
