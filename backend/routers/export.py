"""
Export endpoints for downloading results as JSON reports or PNG images.
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from ..models import ExportRequest, ExportResponse
from ..services.cache import cache
from ..services.task_manager import task_manager
from quantum_partitioning.visualization import (
    build_partition_graph_data,
    render_partition_graph,
    render_mapping_visualization,
)
from quantum_partitioning.chip_mapping import (
    build_partition_interaction_graph,
    parse_target_topology,
    find_chip_mapping,
    compute_total_epr_cost,
)

router = APIRouter(prefix="/api/export", tags=["export"])


def _build_report(task_id: str) -> Dict[str, Any]:
    """Build a complete JSON-serialisable report."""
    result = task_manager.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task result not found.")

    return {
        "task_id": task_id,
        "partitions": result["partitions"],
        "teleportations": result["teleportations"],
        "global_gates": result["global_gates"],
        "optimized_gate_count": result["optimized_gate_count"],
        "params_used": result["params_used"],
        "elapsed_seconds": result["elapsed_seconds"],
    }


@router.post("/report", response_model=ExportResponse)
def export_report(body: ExportRequest):
    """Generate a JSON report for a completed task."""
    report = _build_report(body.task_id)

    # Store report in cache so the download endpoint can serve it
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    cache.set(f"export:{body.task_id}", report_json, ttl=600)

    return ExportResponse(
        task_id=body.task_id,
        download_url=f"/api/export/report/{body.task_id}/download",
        filename=f"partition_report_{body.task_id}.json",
    )


@router.get("/report/{task_id}/download")
def download_report(task_id: str):
    """Download a previously generated report."""
    report_json = cache.get(f"export:{task_id}")
    if report_json is None:
        raise HTTPException(status_code=404, detail="Report not found. Generate it first via POST /api/export/report.")

    return Response(
        content=report_json,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=partition_report_{task_id}.json"
        },
    )


@router.get("/graph-data/{task_id}")
def get_partition_graph_data(task_id: str):
    """返回分区交互图的节点和边数据（含权重），供前端可视化。"""
    result = task_manager.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务结果不存在")
    data = build_partition_graph_data(
        result["raw_partitions"], result["optimized_gates"]
    )
    return data


@router.get("/graph/{task_id}/png")
def export_partition_graph_png(task_id: str):
    """Generate and download the partition interaction graph as PNG."""
    result = task_manager.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task result not found.")

    png_bytes = render_partition_graph(
        result["raw_partitions"],
        result["optimized_gates"],
        title=f"Partition Interaction Graph (task {task_id})",
    )

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename=partition_graph_{task_id}.png"
        },
    )
