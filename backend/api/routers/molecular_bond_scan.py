from __future__ import annotations

import re

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.api.schemas.molecule_workflow import (
    MolecularBondScanAcceptedResponse,
    MolecularBondScanCapabilitiesResponse,
    MolecularBondScanErrorResponse,
    MolecularBondScanRequest,
    MolecularBondScanResponse,
)
from backend.database import get_db
from backend.middleware import get_current_user
from backend.models_db import User
from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
from backend.services.molecule_workflow.service import MoleculeWorkflowError

router = APIRouter(prefix="/api/molecular-bond-scans", tags=["molecular-bond-scans"])

ERROR_RESPONSES = {
    401: {"description": "Missing or expired Bearer token."},
    404: {"model": MolecularBondScanErrorResponse, "description": "Scan does not exist or belongs to another user.", "content": {"application/json": {"example": {"detail": {"code": "molecular_bond_scan_not_found", "message": "Bond scan not found or access is not permitted.", "stage": "lookup", "scan_id": "bondscan_missing", "point_index": None, "molecular_problem_id": None}}}}},
    409: {"model": MolecularBondScanErrorResponse, "description": "Idempotency-Key was reused with a different request.", "content": {"application/json": {"example": {"detail": {"code": "idempotency_key_conflict", "message": "Idempotency-Key is already associated with a different request.", "stage": "input_validation", "scan_id": None, "point_index": None, "molecular_problem_id": None}}}}},
    422: {"description": "Request validation uses FastAPI's detail array; business validation uses the typed detail object.", "content": {"application/json": {"schema": {"oneOf": [{"$ref": "#/components/schemas/HTTPValidationError"}, {"$ref": "#/components/schemas/MolecularBondScanErrorResponse"}]}, "examples": {"request_validation": {"value": {"detail": [{"loc": ["body", "scan", "end_distance_angstrom"], "msg": "end_distance_angstrom must be greater than start_distance_angstrom.", "type": "value_error"}]}}, "business_validation": {"value": {"detail": {"code": "invalid_idempotency_key", "message": "Idempotency-Key has an invalid format.", "stage": "input_validation", "scan_id": None, "point_index": None, "molecular_problem_id": None}}}}}}},
    503: {"model": MolecularBondScanErrorResponse, "description": "The request cannot be accepted or the runtime is unavailable. Background point failures are represented by GET 200 point status=failed.", "content": {"application/json": {"example": {"detail": {"code": "bond_scan_persistence_failed", "message": "Could not persist the bond scan request.", "stage": "input_validation", "scan_id": None, "point_index": None, "molecular_problem_id": None}}}}},
}

ACCEPTED_EXAMPLE = {
    "scan_id": "bondscan_2a91c437d7a14e1ca8b1539eb20e27d1",
    "status": "queued",
    "current_stage": "input_validation",
    "created_at": "2026-08-12T08:00:00+00:00",
    "total_point_count": 8,
}

RUNNING_EXAMPLE = {
    "scan_id": "bondscan_running", "molecule_type": "LiH", "status": "running", "current_stage": "point_calculations",
    "execution_mode": "logical_virtual_qpu", "is_real_qpu": False, "created_at": "2026-08-12T08:00:00+00:00",
    "started_at": "2026-08-12T08:00:01+00:00", "completed_at": None, "total_point_count": 8,
    "queued_point_count": 6, "running_point_count": 1, "completed_point_count": 1, "failed_point_count": 0,
    "needs_review_point_count": 0, "current_point_index": 1,
    "result": {"points": [], "hf_discrete_minimum": None, "vqe_discrete_minimum": None, "fci_discrete_minimum": None, "deployment_reference_point_index": None, "deployment_study_id": None, "deployment_result": None, "summary": {"issues": [], "minimum_at_boundary": False}},
    "error": None,
}

FAILED_EXAMPLE = {
    **RUNNING_EXAMPLE, "scan_id": "bondscan_failed", "status": "failed", "current_stage": "failed",
    "completed_at": "2026-08-12T08:05:00+00:00", "queued_point_count": 0, "running_point_count": 0,
    "failed_point_count": 8, "current_point_index": None, "result": None,
    "error": {"code": "all_scan_points_failed", "message": "All LiH scan points failed.", "stage": "point_calculations", "scan_id": "bondscan_failed", "point_index": None, "molecular_problem_id": None},
}


def get_molecular_bond_scan_service(
    db: Session = Depends(get_db), workflow_service=Depends(get_molecule_workflow_service)
) -> MolecularBondScanService:
    return MolecularBondScanService(db, workflow_service)


def _idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 128 or re.fullmatch(r"[A-Za-z0-9._:-]+", value) is None:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_idempotency_key", "message": "Idempotency-Key has an invalid format.", "stage": "input_validation",
            "scan_id": None, "point_index": None, "molecular_problem_id": None,
        })
    return value


@router.get("/capabilities", response_model=MolecularBondScanCapabilitiesResponse, responses=ERROR_RESPONSES)
def bond_scan_capabilities(user: User = Depends(get_current_user)):
    del user
    return {
        "supported_molecule_types": ["LiH"], "distance_range_angstrom": [0.5, 5.0],
        "minimum_point_count": 2, "maximum_point_count": 16, "supported_basis_sets": ["sto-3g"],
        "active_space_orbital_range": [1, 6], "fci_supported": True,
        "deployment_architecture_count_range": [3, 12], "execution_mode": "logical_virtual_qpu", "is_real_qpu": False,
    }


@router.post(
    "", response_model=MolecularBondScanAcceptedResponse, status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an asynchronous LiH bond-length scan",
    description="Requires Bearer authentication and at least three deployment architectures. Poll GET while queued or running. It is always a logical virtual-QPU simulation, never real-QPU execution.",
    responses={202: {"description": "Scan accepted.", "content": {"application/json": {"example": ACCEPTED_EXAMPLE}}}, **ERROR_RESPONSES},
)
def create_molecular_bond_scan(
    body: MolecularBondScanRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: MolecularBondScanService = Depends(get_molecular_bond_scan_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        accepted = service.submit(body.model_dump(mode="json"), user.id, _idempotency_key(idempotency_key))
    except MoleculeWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "code": exc.code, "message": exc.message, "stage": exc.stage,
            "scan_id": None, "point_index": None, "molecular_problem_id": None,
        }) from exc
    if accepted["status"] == "queued":
        background_tasks.add_task(service.execute, accepted["scan_id"], user.id)
    return accepted


@router.get(
    "/{scan_id}", response_model=MolecularBondScanResponse,
    summary="Restore a persisted LiH bond scan",
    description="Returns the same typed partial-result shape throughout execution. Background point failures are represented by GET 200 with point status=failed; terminal scan failure is GET 200 with status=failed.",
    responses={200: {"description": "Typed partial or terminal scan result.", "content": {"application/json": {"examples": {"running": {"value": RUNNING_EXAMPLE}, "completed": {"externalValue": "/docs/fixtures/molecular-bond-scan-lih-success.json", "summary": "Complete LiH scan fixture"}, "failed": {"value": FAILED_EXAMPLE}}}}}, **ERROR_RESPONSES},
)
def get_molecular_bond_scan(
    scan_id: str,
    user: User = Depends(get_current_user),
    service: MolecularBondScanService = Depends(get_molecular_bond_scan_service),
):
    result = service.get(scan_id, user.id)
    if result is None:
        raise HTTPException(status_code=404, detail={
            "code": "molecular_bond_scan_not_found", "message": "Bond scan not found or access is not permitted.",
            "stage": "lookup", "scan_id": scan_id, "point_index": None, "molecular_problem_id": None,
        })
    return result
