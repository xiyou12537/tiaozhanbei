from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..database import SessionLocal
from ..middleware import get_current_user
from ..models import (
    GridSearchRequest,
    PartitionInfo,
    PartitionRequest,
    PartitionResultResponse,
    TaskStatusResponse,
)
from ..models_db import Circuit as DBCircuit
from ..models_db import Task as DBTask
from ..models_db import User as DBUser
from ..services.cache import cache
from ..services.runtime_status import load_partition_pipeline
from ..services.task_manager import task_manager

router = APIRouter(prefix="/api/partition", tags=["分区"])


def _get_partition_pipeline():
    try:
        return load_partition_pipeline()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _run_partition(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the synchronous partitioning task inside the worker thread."""
    run_partitioning_pipeline = _get_partition_pipeline()
    multi_gates = payload["multi_gates"]
    qubits = payload["qubits"]

    started_at = time.time()
    scheme, b1_used, b2_used = run_partitioning_pipeline(
        gates=multi_gates,
        qubits=qubits,
        num_partitions=payload["num_partitions"],
        max_imbalance=payload.get("max_imbalance", 1),
        search=payload.get("search", False),
        b1_list=payload.get("b1_list"),
        b2_list=payload.get("b2_list"),
        b1=payload.get("b1", 10.0),
        b2=payload.get("b2", 2.0),
        alpha=payload.get("alpha", 3.0),
        beta=payload.get("beta", 1.0),
    )
    elapsed_seconds = time.time() - started_at

    if scheme is None:
        return {"error": "未找到有效的分区方案。", "elapsed_seconds": round(elapsed_seconds, 3)}

    result = {
        "partitions": [
            {"index": index, "qubits": partition, "size": len(partition)}
            for index, partition in enumerate(scheme.partitions)
        ],
        "teleportations": scheme.teleportations,
        "global_gates": scheme.global_gates,
        "optimized_gate_count": len(scheme.optimized_gates),
        "params_used": {"b1": b1_used, "b2": b2_used},
        "elapsed_seconds": round(elapsed_seconds, 3),
        "optimized_gates": scheme.optimized_gates,
        "raw_partitions": scheme.partitions,
        "error": None,
    }

    db = SessionLocal()
    try:
        circuit_data = payload.get("circuit_data", {})
        if circuit_data:
            db_circuit = DBCircuit(
                user_id=payload["user_id"],
                name=circuit_data.get("name", "未命名电路"),
                qasm_content=circuit_data.get("qasm", ""),
                num_qubits=circuit_data.get("num_qubits", 0),
                total_gates=circuit_data.get("total_gates", 0),
                multi_qubit_gates=circuit_data.get("multi_gates", 0),
                qubit_list=circuit_data.get("qubit_list", []),
            )
            db.add(db_circuit)
            db.flush()
            circuit_id = db_circuit.id
        else:
            circuit_id = 0

        db_task = DBTask(
            user_id=payload["user_id"],
            circuit_id=circuit_id,
            task_id=payload.get("task_id", ""),
            status="completed",
            params_json={
                "num_partitions": payload.get("num_partitions"),
                "b1": payload.get("b1"),
                "b2": payload.get("b2"),
                "alpha": payload.get("alpha"),
                "beta": payload.get("beta"),
                "search": payload.get("search"),
            },
            result_json={
                "teleportations": scheme.teleportations,
                "global_gates": scheme.global_gates,
                "partitions": result["partitions"],
                "elapsed_seconds": result["elapsed_seconds"],
            },
            elapsed_seconds=elapsed_seconds,
        )
        db.add(db_task)
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

    return result


@router.post("/run", response_model=TaskStatusResponse)
def run_partition(
    body: PartitionRequest,
    user: DBUser = Depends(get_current_user),
):
    """Submit an asynchronous partitioning task."""
    _get_partition_pipeline()

    data = cache.get(body.circuit_id)
    if data is None:
        raise HTTPException(status_code=404, detail="电路未找到，请先上传。")

    payload = {
        "multi_gates": data["multi_gates"],
        "qubits": data["qubits"],
        "num_partitions": body.num_partitions,
        "max_imbalance": body.max_imbalance,
        "b1": body.b1,
        "b2": body.b2,
        "alpha": body.alpha,
        "beta": body.beta,
        "search": body.search,
        "user_id": user.id,
        "circuit_data": {
            "name": f"电路 ({data['num_qubits']} 量子比特)",
            "qasm": data.get("qasm", ""),
            "num_qubits": data["num_qubits"],
            "total_gates": len(data["gates"]),
            "multi_gates": len(data["multi_gates"]),
            "qubit_list": data["qubits"],
        },
    }

    task_id = task_manager.submit(_run_partition, payload)
    payload["task_id"] = task_id
    return TaskStatusResponse(task_id=task_id, status="queued", message="任务已提交。")


@router.post("/grid-search", response_model=TaskStatusResponse)
def run_grid_search(
    body: GridSearchRequest,
    user: DBUser = Depends(get_current_user),
):
    """Submit an asynchronous partitioning grid-search task."""
    _get_partition_pipeline()

    data = cache.get(body.circuit_id)
    if data is None:
        raise HTTPException(status_code=404, detail="电路未找到，请先上传。")

    payload = {
        "multi_gates": data["multi_gates"],
        "qubits": data["qubits"],
        "num_partitions": body.num_partitions,
        "max_imbalance": body.max_imbalance,
        "alpha": body.alpha,
        "beta": body.beta,
        "search": True,
        "b1_list": body.b1_list,
        "b2_list": body.b2_list,
        "user_id": user.id,
        "circuit_data": {
            "name": f"电路 ({data['num_qubits']} 量子比特)",
            "qasm": data.get("qasm", ""),
            "num_qubits": data["num_qubits"],
            "total_gates": len(data["gates"]),
            "multi_gates": len(data["multi_gates"]),
            "qubit_list": data["qubits"],
        },
    }

    task_id = task_manager.submit(_run_partition, payload)
    payload["task_id"] = task_id
    return TaskStatusResponse(task_id=task_id, status="queued", message="网格搜索任务已提交。")


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """Return the current status of a submitted task."""
    status_payload = task_manager.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="任务不存在。")

    return TaskStatusResponse(
        task_id=task_id,
        status=status_payload["status"],
        progress=status_payload["progress"],
        message=status_payload["message"],
    )


@router.get("/result/{task_id}", response_model=PartitionResultResponse)
def get_partition_result(task_id: str):
    """Return the result of a completed partitioning task."""
    result = task_manager.get_result(task_id)
    if result is None:
        status_payload = task_manager.get_status(task_id)
        if status_payload is None:
            raise HTTPException(status_code=404, detail="任务不存在。")
        raise HTTPException(
            status_code=409,
            detail=f"任务尚未完成，当前状态：{status_payload['status']}",
        )

    if result.get("error"):
        return PartitionResultResponse(
            task_id=task_id,
            num_partitions=0,
            partitions=[],
            teleportations=0,
            global_gates=0,
            optimized_gate_count=0,
            params_used={},
            elapsed_seconds=result.get("elapsed_seconds", 0),
            error=result["error"],
        )

    return PartitionResultResponse(
        task_id=task_id,
        num_partitions=len(result["partitions"]),
        partitions=[PartitionInfo(**item) for item in result["partitions"]],
        teleportations=result["teleportations"],
        global_gates=result["global_gates"],
        optimized_gate_count=result["optimized_gate_count"],
        params_used=result["params_used"],
        elapsed_seconds=result["elapsed_seconds"],
        error=None,
    )
