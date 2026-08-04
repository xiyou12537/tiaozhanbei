"""历史记录路由：查看当前用户的分区任务和映射结果。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import get_current_user
from ..models_db import Circuit, Mapping, Task, User

router = APIRouter(prefix="/api/user", tags=["历史记录"])


@router.get("/history")
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的历史任务列表，按时间倒序返回。"""
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .order_by(Task.created_at.desc())
        .limit(50)
        .all()
    )

    results = []
    for task in tasks:
        circuit = db.query(Circuit).filter(Circuit.id == task.circuit_id).first()
        mappings = (
            db.query(Mapping)
            .filter(Mapping.task_id == task.id)
            .order_by(Mapping.created_at.desc())
            .all()
        )

        results.append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "circuit_name": circuit.name if circuit else "未知电路",
                "num_qubits": circuit.num_qubits if circuit else 0,
                "total_gates": circuit.total_gates if circuit else 0,
                "params": task.params_json or {},
                "result": task.result_json,
                "elapsed_seconds": task.elapsed_seconds,
                "mappings": [
                    {
                        "topology_name": item.topology_name,
                        "epr_cost": item.epr_cost,
                        "subgraph_cost": item.subgraph_cost,
                        "mapping": item.mapping_json,
                    }
                    for item in mappings
                ],
                "created_at": task.created_at.isoformat() if task.created_at else "",
            }
        )

    return {"history": results, "total": len(results)}
