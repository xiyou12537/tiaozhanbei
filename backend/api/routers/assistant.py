from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.routers.molecular_bond_scan import get_molecular_bond_scan_service
from backend.api.routers.molecular_study import get_molecular_study_service
from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.api.schemas.assistant import (
    AssistantConfirmToolRequest,
    AssistantErrorResponse,
    AssistantSessionCreateRequest,
    AssistantSessionResponse,
    AssistantStreamMessageRequest,
    AssistantToolExecutionResponse,
)
from backend.database import get_db
from backend.middleware import get_current_user
from backend.models_db import User
from backend.services.assistant import AssistantError, MolecularAssistantService
from backend.services.assistant.model_adapter import assistant_runtime_limits, build_assistant_model_adapter
from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
from backend.services.molecule_workflow.study_service import MolecularStudyService

router = APIRouter(prefix="/api/assistant", tags=["molecular-assistant"])

ERROR_RESPONSES = {
    401: {"description": "Missing or invalid Bearer token."},
    404: {"model": AssistantErrorResponse, "description": "Session, confirmation, or user-owned task was not found."},
    409: {"model": AssistantErrorResponse, "description": "Confirmation is expired, mismatched, or no longer pending."},
    422: {"model": AssistantErrorResponse, "description": "Tool name or tool parameters are not allowed."},
    429: {"model": AssistantErrorResponse, "description": "Configured model provider rate limited the request."},
    502: {"model": AssistantErrorResponse, "description": "Configured model provider is unavailable or invalid."},
    503: {"model": AssistantErrorResponse, "description": "Model is unconfigured or confirmed task creation is unavailable."},
    504: {"model": AssistantErrorResponse, "description": "Configured model provider timed out."},
}


def get_assistant_service(
    db: Session = Depends(get_db),
    workflow_service=Depends(get_molecule_workflow_service),
    study_service: MolecularStudyService = Depends(get_molecular_study_service),
    bond_scan_service: MolecularBondScanService = Depends(get_molecular_bond_scan_service),
) -> MolecularAssistantService:
    return MolecularAssistantService(
        db,
        build_assistant_model_adapter(),
        workflow_service,
        study_service,
        bond_scan_service,
        assistant_runtime_limits(),
    )


def _raise_assistant_error(exc: AssistantError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.as_dict()) from exc


@router.post("/sessions", response_model=AssistantSessionResponse, status_code=201, responses=ERROR_RESPONSES)
def create_assistant_session(
    body: AssistantSessionCreateRequest,
    user: User = Depends(get_current_user),
    service: MolecularAssistantService = Depends(get_assistant_service),
):
    try:
        return service.create_session(user.id, body.title)
    except AssistantError as exc:
        _raise_assistant_error(exc)


@router.get("/sessions/{session_id}", response_model=AssistantSessionResponse, responses=ERROR_RESPONSES)
def get_assistant_session(
    session_id: str,
    user: User = Depends(get_current_user),
    service: MolecularAssistantService = Depends(get_assistant_service),
):
    try:
        return service.get_session(session_id, user.id)
    except AssistantError as exc:
        _raise_assistant_error(exc)


@router.post("/sessions/{session_id}/messages/stream", responses=ERROR_RESPONSES)
def stream_assistant_message(
    session_id: str,
    body: AssistantStreamMessageRequest,
    user: User = Depends(get_current_user),
    service: MolecularAssistantService = Depends(get_assistant_service),
):
    try:
        service.validate_stream_request(session_id, user.id, body.ui_tool_name, body.ui_tool_arguments)
    except AssistantError as exc:
        _raise_assistant_error(exc)

    def event_stream():
        for event in service.stream_message(
            session_id,
            user.id,
            body.message,
            body.ui_tool_name,
            body.ui_tool_arguments,
        ):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/sessions/{session_id}/tool-confirmations",
    response_model=AssistantToolExecutionResponse,
    responses=ERROR_RESPONSES,
)
def confirm_assistant_tool(
    session_id: str,
    body: AssistantConfirmToolRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    service: MolecularAssistantService = Depends(get_assistant_service),
):
    try:
        response = service.confirm_tool(session_id, user.id, body.confirmation_id, body.tool_name, body.parameter_summary)
    except AssistantError as exc:
        _raise_assistant_error(exc)

    result = response.get("result") or {}
    if not response.get("already_confirmed") and result.get("status") == "queued":
        task_type = result.get("task_type")
        task_id = result.get("task_id")
        if task_type == "molecular_study":
            background_tasks.add_task(service.study_service.execute, task_id, user.id)
        elif task_type == "molecular_bond_scan":
            background_tasks.add_task(service.bond_scan_service.execute, task_id, user.id)
    return response
