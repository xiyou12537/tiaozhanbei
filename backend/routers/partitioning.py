"""
分区计算接口 —— 启动异步分区任务、轮询状态、获取结果。
任务完成后自动保存到数据库供历史记录查询。
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models_db import Circuit as DBCircuit, Task as DBTask
from ..models import (
    GridSearchRequest,
    PartitionInfo,
    PartitionRequest,
    PartitionResultResponse,
    TaskStatusResponse,
)
from ..services.cache import cache
from ..services.task_manager import task_manager
from ..middleware import get_current_user
from ..models_db import User as DBUser
from quantum_partitioning.partitioning import (
    PartitionScheme,
    run_partitioning_pipeline,
)

router = APIRouter(prefix="/api/partition", tags=["partition"])


def _run_partition(payload: Dict[str, Any]) -> Dict[str, Any]:
    """同步分区计算（在后台线程中调用），完成后自动保存到数据库。"""
    multi_gates = payload["multi_gates"]
    qubits = payload["qubits"]

    t0 = time.time()
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
    elapsed = time.time() - t0

    if scheme is None:
        return {"error": "未找到有效分区方案", "elapsed": elapsed}

    result = {
        "partitions": [
            {"index": i, "qubits": p, "size": len(p)}
            for i, p in enumerate(scheme.partitions)
        ],
        "teleportations": scheme.teleportations,
        "global_gates": scheme.global_gates,
        "optimized_gate_count": len(scheme.optimized_gates),
        "params_used": {"b1": b1_used, "b2": b2_used},
        "elapsed_seconds": round(elapsed, 3),
        "optimized_gates": scheme.optimized_gates,
        "raw_partitions": scheme.partitions,
        "error": None,
    }

    # 保存到数据库供历史记录
    try:
        db = SessionLocal()
        # 保存电路（如果还没保存过）
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

        # 保存任务
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
            elapsed_seconds=elapsed,
        )
        db.add(db_task)
        db.commit()
    except Exception:
        pass  # 保存失败不影响主流程
    finally:
        db.close()

    return result


@router.post("/run", response_model=TaskStatusResponse)
def run_partition(
    body: PartitionRequest,
    user: DBUser = Depends(get_current_user),
):
    """启动分区计算任务（异步）。返回 task_id 用于轮询。"""
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
            "name": f"电路 ({data['num_qubits']}量子比特)",
            "qasm": data.get("qasm", ""),
            "num_qubits": data["num_qubits"],
            "total_gates": len(data["gates"]),
            "multi_gates": len(data["multi_gates"]),
            "qubit_list": data["qubits"],
        },
    }

    task_id = task_manager.submit(_run_partition, payload)
    # Store task_id in payload for later DB save
    payload["task_id"] = task_id
    return TaskStatusResponse(task_id=task_id, status="queued", message="任务已提交")


@router.post("/grid-search", response_model=TaskStatusResponse)
def run_grid_search(
    body: GridSearchRequest,
    user: DBUser = Depends(get_current_user),
):
    """启动网格搜索分区任务（异步，可能较慢）。"""
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
            "name": f"电路 ({data['num_qubits']}量子比特)",
            "qasm": data.get("qasm", ""),
            "num_qubits": data["num_qubits"],
            "total_gates": len(data["gates"]),
            "multi_gates": len(data["multi_gates"]),
            "qubit_list": data["qubits"],
        },
    }

    task_id = task_manager.submit(_run_partition, payload)
    payload["task_id"] = task_id
    return TaskStatusResponse(task_id=task_id, status="queued", message="网格搜索已提交")


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """Poll task progress."""
    status = task_manager.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    return TaskStatusResponse(
        task_id=task_id,
        status=status["status"],
        progress=status["progress"],
        message=status["message"],
    )


@router.get("/result/{task_id}", response_model=PartitionResultResponse)
def get_partition_result(task_id: str):
    """Get completed partition result."""
    result = task_manager.get_result(task_id)
    if result is None:
        # Maybe the task hasn't completed yet
        status = task_manager.get_status(task_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        raise HTTPException(
            status_code=409,
            detail=f"Task not complete. Current status: {status['status']}",
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
        partitions=[PartitionInfo(**p) for p in result["partitions"]],
        teleportations=result["teleportations"],
        global_gates=result["global_gates"],
        optimized_gate_count=result["optimized_gate_count"],
        params_used=result["params_used"],
        elapsed_seconds=result["elapsed_seconds"],
        error=None,
    )
