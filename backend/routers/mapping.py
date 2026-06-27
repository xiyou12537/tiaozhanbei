"""
Chip-topology mapping endpoints.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException

from ..models import (
    MappingRequest,
    MappingResultResponse,
    TopologyCompareRequest,
    TopologyCompareResponse,
    TopologyEdge,
    TopologyPreset,
)
from ..services.cache import cache
from ..services.task_manager import task_manager
from quantum_partitioning.chip_mapping import (
    build_partition_interaction_graph,
    compute_total_epr_cost,
    find_chip_mapping,
    parse_target_topology,
)

router = APIRouter(prefix="/api/mapping", tags=["mapping"])


# ── Preset topologies ──────────────────────────────────────────────

PRESETS: Dict[str, TopologyPreset] = {
    "ring-3": TopologyPreset(
        name="ring-3",
        label="Ring (3 chips)",
        description="3-node cycle",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=1, target=2),
               TopologyEdge(source=2, target=0)],
    ),
    "ring-4": TopologyPreset(
        name="ring-4",
        label="Ring (4 chips)",
        description="4-node cycle",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=1, target=2),
               TopologyEdge(source=2, target=3),
               TopologyEdge(source=3, target=0)],
    ),
    "star-4": TopologyPreset(
        name="star-4",
        label="Star (4 chips)",
        description="Central chip with 3 leaves",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=0, target=2),
               TopologyEdge(source=0, target=3)],
    ),
    "linear-3": TopologyPreset(
        name="linear-3",
        label="Linear (3 chips)",
        description="3-node path",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=1, target=2)],
    ),
    "linear-4": TopologyPreset(
        name="linear-4",
        label="Linear (4 chips)",
        description="4-node path",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=1, target=2),
               TopologyEdge(source=2, target=3)],
    ),
    "fully-4": TopologyPreset(
        name="fully-4",
        label="Fully connected (4 chips)",
        description="All-to-all connectivity",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=0, target=2),
               TopologyEdge(source=0, target=3),
               TopologyEdge(source=1, target=2),
               TopologyEdge(source=1, target=3),
               TopologyEdge(source=2, target=3)],
    ),
    "grid-2x2": TopologyPreset(
        name="grid-2x2",
        label="Grid 2x2 (4 chips)",
        description="2x2 mesh",
        edges=[TopologyEdge(source=0, target=1),
               TopologyEdge(source=0, target=2),
               TopologyEdge(source=1, target=3),
               TopologyEdge(source=2, target=3)],
    ),
}


@router.get("/topology-presets", response_model=Dict[str, TopologyPreset])
def get_presets():
    """Return all built-in topology presets."""
    return PRESETS


# ── Mapping ────────────────────────────────────────────────────────

def _compute_mapping(
    raw_partitions: List[List[int]],
    optimized_gates: list,
    edges: List[TopologyEdge],
) -> dict:
    """Core mapping computation (reusable for single + compare)."""
    complete_g, _ = build_partition_interaction_graph(raw_partitions, optimized_gates)
    target_g = parse_target_topology([(e.source, e.target) for e in edges])

    mapping, min_cost = find_chip_mapping(complete_g, target_g)

    if mapping is None:
        return {
            "mapping": {},
            "subgraph_cost": float("inf"),
            "total_epr_cost": 0,
            "valid": False,
        }

    # qubit -> partition
    qubit_to_partition: Dict[int, str] = {}
    for idx, part in enumerate(raw_partitions):
        pid = f"P{idx + 1}"
        for q in part:
            qubit_to_partition[q] = pid

    # partition -> chip
    p2c = {v: k for k, v in mapping.items()}

    epr_cost = compute_total_epr_cost(
        optimized_gates, raw_partitions, qubit_to_partition, p2c, target_g
    )

    return {
        "mapping": mapping,
        "subgraph_cost": min_cost,
        "total_epr_cost": epr_cost,
        "valid": True,
    }


@router.post("/find", response_model=MappingResultResponse)
def find_mapping(body: MappingRequest):
    """Find optimal partition-to-chip mapping for a target topology."""
    # Get partition result
    result = task_manager.get_result(body.task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Partition result not found.")

    out = _compute_mapping(
        result["raw_partitions"],
        result["optimized_gates"],
        body.topology_edges,
    )

    if not out["valid"]:
        return MappingResultResponse(
            mapping={},
            subgraph_cost=float("inf"),
            total_epr_cost=0,
            topology_edges=body.topology_edges,
            valid=False,
        )

    return MappingResultResponse(
        mapping=out["mapping"],
        subgraph_cost=out["subgraph_cost"],
        total_epr_cost=out["total_epr_cost"],
        topology_edges=body.topology_edges,
        valid=True,
    )


@router.post("/compare", response_model=TopologyCompareResponse)
def compare_topologies(body: TopologyCompareRequest):
    """Compare EPR costs across multiple target topologies."""
    result = task_manager.get_result(body.task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Partition result not found.")

    comparisons: List[MappingResultResponse] = []
    for name, edges in body.topologies.items():
        out = _compute_mapping(
            result["raw_partitions"],
            result["optimized_gates"],
            edges,
        )
        comparisons.append(MappingResultResponse(
            mapping=out.get("mapping", {}),
            subgraph_cost=out.get("subgraph_cost", float("inf")),
            total_epr_cost=out.get("total_epr_cost", 0),
            topology_edges=edges,
            valid=out["valid"],
        ))

    return TopologyCompareResponse(
        task_id=body.task_id,
        comparisons=comparisons,
    )
