from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.api.schemas.molecule_workflow import (
    MolecularStudyAcceptedResponse,
    MolecularStudyErrorResponse,
    MolecularStudyRequest,
    MolecularStudyResponse,
)
from backend.database import get_db
from backend.middleware import get_current_user
from backend.models_db import User
from backend.services.molecule_workflow.study_service import MolecularStudyService

router = APIRouter(prefix="/api/molecular-studies", tags=["molecular-studies"])

STUDY_ERROR_RESPONSES = {
    401: {
        "description": "Missing or expired Bearer token.",
        "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
    },
    404: {
        "model": MolecularStudyErrorResponse,
        "description": "The study does not exist or does not belong to the current user.",
        "content": {"application/json": {"example": {"detail": {
            "code": "molecular_study_not_found", "message": "Study not found or access is not permitted.",
            "stage": "lookup", "study_id": "study_missing", "molecular_problem_id": None, "architecture_id": None,
        }}}},
    },
    409: {
        "model": MolecularStudyErrorResponse,
        "description": "The requested study state conflicts with an in-progress operation.",
        "content": {"application/json": {"example": {"detail": {
            "code": "molecular_study_in_progress", "message": "The molecular study is still in progress.",
            "stage": "scheduling", "study_id": "study_running", "molecular_problem_id": None, "architecture_id": None,
        }}}},
    },
    422: {
        "description": "Request validation errors use FastAPI's detail array; business validation uses the stable detail object.",
        "content": {"application/json": {"schema": {"oneOf": [
            {"$ref": "#/components/schemas/HTTPValidationError"},
            {"$ref": "#/components/schemas/MolecularStudyErrorResponse"},
        ]}, "examples": {
            "request_validation": {"value": {"detail": [{"loc": ["body", "architectures"], "msg": "List should have at least 3 items", "type": "too_short"}]}},
            "business_validation": {"value": {"detail": {
                "code": "duplicate_architecture_id", "message": "architecture_id must be unique within a study.",
                "stage": "input_validation", "study_id": None, "molecular_problem_id": None, "architecture_id": "linear-a",
            }}},
        }}},
    },
    503: {
        "model": MolecularStudyErrorResponse,
        "description": "The request cannot be scheduled or the query service is unavailable. Background PySCF/VQE failures are returned by GET 200 with status=failed.",
        "content": {"application/json": {"example": {"detail": {
            "code": "molecular_study_scheduler_unavailable", "message": "The molecular-study scheduler is unavailable.",
            "stage": "scheduling", "study_id": None, "molecular_problem_id": None, "architecture_id": None,
        }}}},
    },
}

STUDY_ACCEPTED_EXAMPLE = {
    "study_id": "study_b98937370e114449827c06e176beae59",
    "molecular_problem_id": "mprob_c256ca582bc644f5b84dfcff1ead50fa",
    "problem_id": "mprob_c256ca582bc644f5b84dfcff1ead50fa",
    "status": "queued", "current_stage": "queued", "created_at": "2026-08-11T01:42:00+00:00",
    "started_at": None, "completed_at": None, "completed_evaluation_count": 0, "total_evaluation_count": 3, "error": None,
}

STUDY_RUNNING_EXAMPLE = {
    "study_id": "study_running", "molecular_problem_id": "mprob_running", "problem_id": "mprob_running",
    "status": "running", "current_stage": "deployment_evaluation", "created_at": "2026-08-11T01:42:00+00:00",
    "started_at": "2026-08-11T01:42:01+00:00", "completed_at": None,
    "completed_evaluation_count": 1, "total_evaluation_count": 3, "error": None,
    "result": {"molecular_problem": {"molecular_problem_id": "mprob_running", "status": "completed", "stages": [], "molecule": None, "hf_energy_hartree": None, "active_space": None, "hamiltonian": None, "vqe": None, "fci_reference": {"status": "not_configured", "method": None, "energy_hartree": None, "message": "No constrained-active-space FCI runtime is configured."}, "vqe_fci_scientific_error_hartree": None}, "deployment_evaluations": [], "summary": {"total_evaluation_count": 3, "completed_evaluation_count": 1, "deployable_evaluation_count": 1, "non_deployable_evaluation_count": 0, "failed_evaluation_count": 0}},
}

STUDY_FAILED_EXAMPLE = {
    "study_id": "study_failed", "molecular_problem_id": "mprob_failed", "problem_id": "mprob_failed",
    "status": "failed", "current_stage": "molecular_problem", "created_at": "2026-08-11T01:42:00+00:00",
    "started_at": "2026-08-11T01:42:01+00:00", "completed_at": "2026-08-11T01:42:02+00:00",
    "completed_evaluation_count": 0, "total_evaluation_count": 3, "result": None,
    "error": {"code": "molecular_study_failed", "message": "PySCF runtime became unavailable.", "stage": "molecular_problem", "study_id": "study_failed", "molecular_problem_id": "mprob_failed", "architecture_id": None},
}


def get_molecular_study_service(
    db: Session = Depends(get_db), workflow_service=Depends(get_molecule_workflow_service)
) -> MolecularStudyService:
    return MolecularStudyService(db, workflow_service)


@router.post(
    "",
    response_model=MolecularStudyAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an asynchronous molecular deployment study",
    description=(
        "Requires Bearer authentication and at least three architecture proposals. "
        "Poll while `status` is `queued` or `running`; stop at `completed` or `failed`. "
        "A non-deployable architecture is a completed evaluation and does not fail the study."
    ),
    responses={
        202: {"description": "Study accepted for asynchronous execution.", "content": {"application/json": {"example": STUDY_ACCEPTED_EXAMPLE}}},
        **STUDY_ERROR_RESPONSES,
    },
)
def create_molecular_study(
    body: MolecularStudyRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: MolecularStudyService = Depends(get_molecular_study_service),
):
    accepted = service.submit(body.model_dump(mode="json"), user.id)
    background_tasks.add_task(service.execute, accepted["study_id"], user.id)
    return accepted


@router.get(
    "/{study_id}",
    response_model=MolecularStudyResponse,
    summary="Restore a molecular deployment study",
    description=(
        "Running studies return a stable partial result skeleton. PySCF/VQE failures after acceptance are represented "
        "as `200` with `status=failed`; `503` is reserved for an unavailable scheduling/query service."
    ),
    responses={
        200: {"description": "A typed partial or terminal Study result.", "content": {"application/json": {"examples": {
            "running": {"value": STUDY_RUNNING_EXAMPLE},
            "completed": {"externalValue": "/docs/fixtures/molecular-study-h2-three-architecture-success.json", "summary": "Complete three-architecture H2 fixture"},
            "failed": {"value": STUDY_FAILED_EXAMPLE},
        }}}},
        **STUDY_ERROR_RESPONSES,
    },
)
def get_molecular_study(
    study_id: str,
    user: User = Depends(get_current_user),
    service: MolecularStudyService = Depends(get_molecular_study_service),
):
    result = service.get(study_id, user.id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "molecular_study_not_found",
                "message": "Study not found or access is not permitted.",
                "stage": "lookup",
                "study_id": study_id,
                "molecular_problem_id": None,
                "architecture_id": None,
            },
        )
    return result
