"""
历史记录路由 —— 查看当前用户的所有过往分区任务和映射结果。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models_db import Task, Circuit, Mapping, User
from ..middleware import get_current_user

router = APIRouter(prefix="/api/user", tags=["历史记录"])


@router.get("/history")
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有历史任务（按时间倒序）。"""
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .order_by(Task.created_at.desc())
        .limit(50)
        .all()
    )

    results = []
    for t in tasks:
        circuit = db.query(Circuit).filter(Circuit.id == t.circuit_id).first()
        mappings = (
            db.query(Mapping)
            .filter(Mapping.task_id == t.id)
            .order_by(Mapping.created_at.desc())
            .all()
        )

        results.append({
            "task_id": t.task_id,
            "status": t.status,
            "circuit_name": circuit.name if circuit else "未知电路",
            "num_qubits": circuit.num_qubits if circuit else 0,
            "total_gates": circuit.total_gates if circuit else 0,
            "params": t.params_json or {},
            "result": t.result_json,
            "elapsed_seconds": t.elapsed_seconds,
            "mappings": [
                {
                    "topology_name": m.topology_name,
                    "epr_cost": m.epr_cost,
                    "subgraph_cost": m.subgraph_cost,
                    "mapping": m.mapping_json,
                }
                for m in mappings
            ],
            "created_at": t.created_at.isoformat() if t.created_at else "",
        })

    return {"history": results, "total": len(results)}
