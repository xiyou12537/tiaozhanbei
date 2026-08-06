from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.schemas.molecule_workflow import (
    MoleculeWorkflowErrorResponse,
    MoleculeWorkflowHistoryResponse,
    MoleculeWorkflowRequest,
    MoleculeWorkflowResponse,
    SUCCESS_RESPONSE_EXAMPLE,
)
from backend.database import get_db
from backend.middleware import get_current_user
from backend.models_db import User
from backend.services.molecule_workflow import MoleculeWorkflowError, MoleculeWorkflowService
from backend.services.molecule_workflow.repository import MoleculeWorkflowRepository

router = APIRouter(prefix="/api/molecule-workflows", tags=["molecule-workflows"])

ERROR_RESPONSES = {
    401: {
        "description": "缺少或无效的认证令牌。",
        "content": {"application/json": {"example": {"detail": "未提供认证令牌。"}}},
    },
    404: {
        "model": MoleculeWorkflowErrorResponse,
        "description": "工作流不存在或不属于当前用户。",
        "content": {
            "application/json": {
                "example": {
                    "detail": {
                        "code": "molecule_workflow_not_found",
                        "message": "未找到分子计算工作流或无权访问。",
                        "stage": "lookup",
                        "workflow_id": "molwf_missing",
                    }
                }
            }
        },
    },
    409: {
        "model": MoleculeWorkflowErrorResponse,
        "description": "同一幂等键的工作流仍在运行或已失败。",
        "content": {
            "application/json": {
                "example": {
                    "detail": {
                        "code": "molecule_workflow_in_progress",
                        "message": "相同幂等键的分子计算工作流仍在执行。",
                        "stage": "vqe_optimization",
                        "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7",
                    }
                }
            }
        },
    },
    422: {
        "model": MoleculeWorkflowErrorResponse,
        "description": "输入、活性空间、量子比特限制、分区或映射不可执行。",
        "content": {
            "application/json": {
                "example": {
                    "detail": {
                        "code": "mapped_qubit_limit_exceeded",
                        "message": "映射后得到 14 个量子比特，超过第一版上限 12。",
                        "stage": "qubit_mapping",
                        "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7",
                    }
                }
            }
        },
    },
    503: {
        "model": MoleculeWorkflowErrorResponse,
        "description": "真实 PySCF/OpenFermion 计算运行时不可用。",
        "content": {
            "application/json": {
                "example": {
                    "detail": {
                        "code": "electronic_structure_runtime_unavailable",
                        "message": "PySCF/OpenFermion 计算运行时不可用：PySCF Docker runtime is unavailable or timed out.",
                        "stage": "electronic_structure",
                        "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7",
                    }
                }
            }
        },
    },
}


def get_molecule_workflow_service(db: Session = Depends(get_db)) -> MoleculeWorkflowService:
    return MoleculeWorkflowService(MoleculeWorkflowRepository(db))


def _raise_workflow_error(exc: MoleculeWorkflowError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.as_dict()) from exc


def _validate_idempotency_key(idempotency_key: str | None) -> str | None:
    if idempotency_key is None:
        return None
    if len(idempotency_key) > 128 or re.fullmatch(r"[A-Za-z0-9._:-]+", idempotency_key) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_idempotency_key",
                "message": "Idempotency-Key 只能包含字母、数字、点、下划线、冒号和连字符，且不超过 128 字符。",
                "stage": "input_validation",
                "workflow_id": None,
            },
        )
    return idempotency_key


@router.post(
    "",
    response_model=MoleculeWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="执行并持久化通用小分子量子计算闭环",
    description=(
        "对固定输入几何依次执行 PySCF HF、活性空间选择、费米子 Hamiltonian、量子比特映射、"
        "VQE、线路分区、虚拟节点映射和 logical_virtual_qpu 分布式逻辑模拟。"
        "该模式是模拟器能力，不代表真实 QPU 执行。"
    ),
    responses={
        201: {
            "description": "闭环计算完成，结果已持久化。",
            "content": {"application/json": {"example": SUCCESS_RESPONSE_EXAMPLE}},
        },
        **ERROR_RESPONSES,
    },
)
def create_molecule_workflow(
    body: MoleculeWorkflowRequest,
    user: User = Depends(get_current_user),
    service: MoleculeWorkflowService = Depends(get_molecule_workflow_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        return service.execute(
            body.model_dump(mode="json"),
            user.id,
            _validate_idempotency_key(idempotency_key),
        )
    except MoleculeWorkflowError as exc:
        _raise_workflow_error(exc)


@router.get(
    "",
    response_model=MoleculeWorkflowHistoryResponse,
    summary="查询当前用户的分子 Workflow 历史",
    responses={401: ERROR_RESPONSES[401]},
)
def list_molecule_workflows(
    user: User = Depends(get_current_user),
    service: MoleculeWorkflowService = Depends(get_molecule_workflow_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    molecule_name: str | None = Query(default=None, min_length=1, max_length=120),
    status: str | None = Query(default=None, pattern="^(running|completed|failed)$"),
    validation_status: str | None = Query(default=None, pattern="^(passed|needs_review)$"),
):
    return service.list_workflows(
        user.id,
        page=page,
        page_size=page_size,
        molecule_name=molecule_name,
        status=status,
        validation_status=validation_status,
    )


@router.get(
    "/{workflow_id}",
    response_model=MoleculeWorkflowResponse,
    summary="查询已持久化的分子计算闭环结果",
    responses=ERROR_RESPONSES,
)
def get_molecule_workflow(
    workflow_id: str,
    user: User = Depends(get_current_user),
    service: MoleculeWorkflowService = Depends(get_molecule_workflow_service),
):
    try:
        return service.get(workflow_id, user.id)
    except MoleculeWorkflowError as exc:
        _raise_workflow_error(exc)
