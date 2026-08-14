from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.api.schemas.molecule_workflow import MolecularBondScanRequest, MolecularStudyRequest, MoleculeWorkflowRequest
from backend.database import assistant_schema_ready
from backend.models_db import AssistantMessageRecord, AssistantSessionRecord, AssistantToolExecutionRecord
from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
from backend.services.molecule_workflow.service import MoleculeWorkflowError, MoleculeWorkflowService
from backend.services.molecule_workflow.study_service import MolecularStudyService

from .knowledge import SYSTEM_KNOWLEDGE
from .model_adapter import AssistantModelAdapter, AssistantModelError, AssistantRuntimeLimits, assistant_runtime_limits


class AssistantError(RuntimeError):
    def __init__(self, code: str, message: str, stage: str, status_code: int = 422, *, session_id: str | None = None, tool_name: str | None = None):
        super().__init__(message)
        self.code, self.message, self.stage, self.status_code = code, message, stage, status_code
        self.session_id, self.tool_name = session_id, tool_name

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "stage": self.stage, "session_id": self.session_id, "tool_name": self.tool_name}


READ_TOOLS = {"platform_capabilities", "select_task", "get_current_user_result"}
DRAFT_TOOLS = {"draft_molecule_workflow", "draft_molecular_study", "draft_molecular_bond_scan"}
ALL_TOOLS = READ_TOOLS | DRAFT_TOOLS
_CONFIRMATION_TTL_MINUTES = 15
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])")
_API_KEY_PATTERN = re.compile(r"(?i)\b(?:api[_-]?key|x-api-key)\s*([=:])\s*[^\s,;]+")
_COOKIE_PATTERN = re.compile(r"(?i)\bcookie\s*:\s*[^\r\n]+")
_QPU_BOUNDARY = "Platform execution is logical_virtual_qpu simulation; is_real_qpu=false and no real QPU is used."


class MolecularAssistantService:
    """Server-orchestrated, allowlisted tools for user-owned molecular work."""

    def __init__(self, session: Session, model_adapter: AssistantModelAdapter, workflow_service: MoleculeWorkflowService, study_service: MolecularStudyService, bond_scan_service: MolecularBondScanService, limits: AssistantRuntimeLimits | None = None):
        self.session = session
        self.model_adapter = model_adapter
        self.workflow_service = workflow_service
        self.study_service = study_service
        self.bond_scan_service = bond_scan_service
        self.limits = limits or assistant_runtime_limits()

    def assert_schema_ready(self) -> None:
        if not assistant_schema_ready(self.session.get_bind()):
            raise AssistantError("assistant_schema_not_ready", "Molecular Copilot persistence is not migrated on this server.", "schema_readiness", 503)

    def create_session(self, user_id: int, title: str | None) -> dict[str, Any]:
        self.assert_schema_ready()
        record = AssistantSessionRecord(session_id=f"asst_{uuid.uuid4().hex}", user_id=user_id, title=title)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return self._session_payload(record, include_children=False)

    def get_session(self, session_id: str, user_id: int) -> dict[str, Any]:
        self.assert_schema_ready()
        return self._session_payload(self._session(session_id, user_id), include_children=True)

    def validate_stream_request(self, session_id: str, user_id: int, ui_tool_name: str | None, ui_tool_arguments: dict[str, Any] | None) -> None:
        """Validate before constructing StreamingResponse so request errors stay HTTP errors."""
        self.assert_schema_ready()
        self._session(session_id, user_id)
        arguments = ui_tool_arguments or {}
        if ui_tool_name is None and arguments:
            raise AssistantError("assistant_ui_tool_arguments_without_tool", "UI shortcut arguments require ui_tool_name.", "tool_validation", 422, session_id=session_id)
        if ui_tool_name is not None and ui_tool_name not in ALL_TOOLS:
            raise AssistantError("assistant_ui_tool_not_allowed", "The requested UI shortcut is not allowed.", "tool_validation", 422, session_id=session_id, tool_name=ui_tool_name)

    def stream_message(self, session_id: str, user_id: int, message: str, ui_tool_name: str | None = None, ui_tool_arguments: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield stable SSE event payloads while model text actually arrives."""
        self.validate_stream_request(session_id, user_id, ui_tool_name, ui_tool_arguments)
        session_record = self._session(session_id, user_id)
        ui_tool_arguments = ui_tool_arguments or {}

        self._append_message(session_record, user_id, "user", self._redact_model_content(message))
        model_messages: list[dict[str, Any]] = [
            {"role": item.role, "content": item.content}
            for item in self._history(session_id, user_id, limit=self.limits.context_max_messages)
        ]
        try:
            tool_calls = 0
            if ui_tool_name is not None:
                yield self._event("tool_started", {"source": "ui_shortcut", "tool_name": ui_tool_name})
                ui_record = self._execute_selected_tool(session_record, user_id, ui_tool_name, ui_tool_arguments)
                yield self._event("tool_completed", {"source": "ui_shortcut", **self._execution_payload(ui_record)})
                model_messages.append(self._ui_shortcut_result_message(ui_record))

            full_content = ""
            while True:
                model_messages = self._fit_model_context(model_messages)
                turn_content = ""
                model_calls: list[dict[str, Any]] = []
                for raw_event in self.model_adapter.stream(system_prompt=SYSTEM_KNOWLEDGE, messages=model_messages, tools=self.tool_definitions(), max_output_tokens=self.limits.max_output_tokens):
                    event_type = raw_event.get("type")
                    if event_type == "message_delta":
                        delta = raw_event.get("delta")
                        if not isinstance(delta, str):
                            raise AssistantError("assistant_model_invalid_response", "Molecular Copilot model emitted an invalid text delta.", "model_completion", 502, session_id=session_id)
                        turn_content += delta
                        yield self._event("message_delta", {"delta": delta})
                    elif event_type == "tool_call":
                        model_calls.append(raw_event)
                    else:
                        raise AssistantError("assistant_model_invalid_response", "Molecular Copilot model emitted an unknown stream event.", "model_completion", 502, session_id=session_id)
                if not model_calls:
                    full_content = turn_content
                    break

                validated_calls: list[dict[str, Any]] = []
                for tool_call in model_calls:
                    tool_calls += 1
                    provider_tool_call_id = tool_call.get("id")
                    tool_name = tool_call.get("name")
                    arguments = tool_call.get("arguments")
                    if tool_calls > self.limits.max_tool_calls:
                        raise AssistantError("assistant_tool_call_limit_exceeded", "Molecular Copilot exceeded the maximum controlled tool calls for one message.", "tool_orchestration", 422, session_id=session_id)
                    if tool_name not in ALL_TOOLS:
                        raise AssistantError("assistant_model_tool_not_allowed", "Molecular Copilot selected a tool outside the allowlist.", "tool_orchestration", 422, session_id=session_id, tool_name=str(tool_name))
                    if not isinstance(arguments, dict):
                        raise AssistantError("assistant_model_tool_invalid_parameters", "Molecular Copilot emitted invalid tool parameters.", "tool_orchestration", 422, session_id=session_id, tool_name=tool_name)
                    if not isinstance(provider_tool_call_id, str) or not provider_tool_call_id:
                        raise AssistantError("assistant_model_invalid_tool_call", "Molecular Copilot emitted a tool call without a provider call identifier.", "tool_orchestration", 502, session_id=session_id, tool_name=tool_name)
                    raw_arguments = tool_call.get("raw_arguments")
                    if not isinstance(raw_arguments, str):
                        raw_arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
                    validated_calls.append({"id": provider_tool_call_id, "name": tool_name, "arguments": arguments, "raw_arguments": raw_arguments})

                # OpenAI-compatible APIs require the provider's assistant tool-call
                # envelope before their matching tool-result messages. Database
                # execution IDs remain strictly internal audit/idempotency keys.
                model_messages.append(self._assistant_tool_calls_message(validated_calls))
                for tool_call in validated_calls:
                    tool_name = tool_call["name"]
                    yield self._event("tool_started", {"source": "model", "tool_name": tool_name})
                    execution = self._execute_selected_tool(session_record, user_id, tool_name, tool_call["arguments"])
                    payload = self._execution_payload(execution)
                    yield self._event("tool_completed", {"source": "model", **payload})
                    model_messages.append(self._tool_result_message(tool_call["id"], execution))
        except AssistantModelError as exc:
            yield self._event("error", AssistantError(exc.code, exc.message, "model_completion", exc.status_code, session_id=session_id).as_dict())
            yield self._event("done", {})
            return
        except AssistantError as exc:
            yield self._event("error", exc.as_dict())
            yield self._event("done", {})
            return

        boundary = f"\n\n{_QPU_BOUNDARY}"
        full_content = f"{full_content.rstrip()}{boundary}"
        yield self._event("message_delta", {"delta": boundary})
        self._append_message(session_record, user_id, "assistant", full_content)
        yield self._event("message_completed", {"content": full_content})
        yield self._event("done", {})

    def confirm_tool(self, session_id: str, user_id: int, confirmation_id: str, tool_name: str, parameter_summary: str) -> dict[str, Any]:
        self.assert_schema_ready()
        record = self._confirmation_record(session_id, user_id, confirmation_id, tool_name, parameter_summary)
        now = self._now()
        if record.status == "confirmed":
            return {**self._execution_payload(record), "already_confirmed": True}
        if record.confirmation_expires_at is None or record.confirmation_expires_at < now:
            record.status = "expired"
            self.session.commit()
            raise AssistantError("assistant_confirmation_expired", "The draft confirmation has expired; create a new draft.", "confirmation", 409, session_id=session_id, tool_name=tool_name)
        claimed = self.session.execute(
            update(AssistantToolExecutionRecord)
            .where(AssistantToolExecutionRecord.execution_id == record.execution_id, AssistantToolExecutionRecord.status == "pending_confirmation")
            .values(status="executing", updated_at=now)
        ).rowcount == 1
        self.session.commit()
        if not claimed:
            record = self._wait_for_confirmation(record.execution_id, session_id, user_id, tool_name)
            if record.status == "confirmed":
                return {**self._execution_payload(record), "already_confirmed": True}
            if record.status == "executing":
                # A process may have created the domain task before it was able
                # to persist this audit result. Re-run only through the stable
                # domain idempotency key to recover that result safely.
                return self._recover_confirmation(record, user_id)
            raise AssistantError("assistant_confirmation_not_pending", "The draft is not available for confirmation.", "confirmation", 409, session_id=session_id, tool_name=tool_name)
        return self._execute_claimed_confirmation(record.execution_id, user_id)

    def _execute_claimed_confirmation(self, execution_id: str, user_id: int) -> dict[str, Any]:
        record = self.session.get(AssistantToolExecutionRecord, execution_id)
        assert record is not None
        try:
            result = self._create_task(record, user_id)
        except MoleculeWorkflowError as exc:
            self._fail_confirmation(record, exc.code, exc.message, exc.stage)
            raise AssistantError(exc.code, exc.message, exc.stage or "task_creation", exc.status_code, session_id=record.session_id, tool_name=record.tool_name) from exc
        except Exception as exc:
            self._fail_confirmation(record, "assistant_task_creation_failed", "Could not create the requested molecular task.", "task_creation")
            raise AssistantError("assistant_task_creation_failed", "Could not create the requested molecular task.", "task_creation", 503, session_id=record.session_id, tool_name=record.tool_name) from exc
        record.status, record.confirmed_at, record.result_json = "confirmed", self._now(), result
        self.session.commit()
        return {**self._execution_payload(record), "already_confirmed": False}

    def _recover_confirmation(self, record: AssistantToolExecutionRecord, user_id: int) -> dict[str, Any]:
        return self._execute_claimed_confirmation(record.execution_id, user_id)

    def _confirmation_record(self, session_id: str, user_id: int, confirmation_id: str, tool_name: str, parameter_summary: str) -> AssistantToolExecutionRecord:
        record = self.session.query(AssistantToolExecutionRecord).filter_by(confirmation_id=confirmation_id, session_id=session_id, user_id=user_id).one_or_none()
        if record is None:
            raise AssistantError("assistant_confirmation_not_found", "The confirmation does not exist or is not available to this user.", "confirmation", 404, session_id=session_id, tool_name=tool_name)
        if record.tool_name != tool_name:
            raise AssistantError("assistant_confirmation_tool_mismatch", "The confirmation does not match the requested tool.", "confirmation", 409, session_id=session_id, tool_name=tool_name)
        if record.parameter_summary != parameter_summary:
            raise AssistantError("assistant_confirmation_parameter_mismatch", "The confirmation parameters no longer match the draft.", "confirmation", 409, session_id=session_id, tool_name=tool_name)
        return record

    def _wait_for_confirmation(self, execution_id: str, session_id: str, user_id: int, tool_name: str) -> AssistantToolExecutionRecord:
        deadline = time.monotonic() + self.limits.confirmation_recovery_seconds
        while time.monotonic() < deadline:
            time.sleep(0.02)
            self.session.expire_all()
            record = self.session.get(AssistantToolExecutionRecord, execution_id)
            if record is not None and record.status != "executing":
                return record
        self.session.expire_all()
        record = self.session.get(AssistantToolExecutionRecord, execution_id)
        if record is None:
            raise AssistantError("assistant_confirmation_not_found", "The confirmation does not exist.", "confirmation", 404, session_id=session_id, tool_name=tool_name)
        return record

    def _fail_confirmation(self, record: AssistantToolExecutionRecord, code: str, message: str, stage: str | None) -> None:
        record.status = "failed"
        record.error_json = {"code": code, "message": message, "stage": stage}
        self.session.commit()

    def _execute_selected_tool(self, session_record: AssistantSessionRecord, user_id: int, tool_name: str, arguments: dict[str, Any]) -> AssistantToolExecutionRecord:
        if tool_name in READ_TOOLS:
            result, arguments = self._execute_read_tool(tool_name, arguments, user_id), dict(arguments)
            status, confirmation_id, expires_at = "completed", None, None
        elif tool_name in DRAFT_TOOLS:
            arguments = self._validate_draft_arguments(tool_name, arguments)
            result = {"draft": self._draft_summary(tool_name, arguments), "execution_mode": "logical_virtual_qpu", "is_real_qpu": False, "requires_confirmation": True}
            status, confirmation_id = "pending_confirmation", f"confirm_{uuid.uuid4().hex}"
            expires_at = self._now() + timedelta(minutes=_CONFIRMATION_TTL_MINUTES)
        else:
            raise AssistantError("assistant_tool_not_allowed", "The requested assistant tool is not allowed.", "tool_validation", 422, tool_name=tool_name)
        record = AssistantToolExecutionRecord(execution_id=f"assttool_{uuid.uuid4().hex}", session_id=session_record.session_id, user_id=user_id, tool_name=tool_name, tool_kind="read" if tool_name in READ_TOOLS else "draft", arguments_json=arguments, parameter_summary=self._parameter_summary(arguments), status=status, confirmation_id=confirmation_id, confirmation_expires_at=expires_at, result_json=result)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def _execute_read_tool(self, tool_name: str, arguments: dict[str, Any], user_id: int) -> dict[str, Any]:
        if tool_name == "platform_capabilities":
            if arguments:
                raise AssistantError("assistant_tool_invalid_parameters", "platform_capabilities does not accept parameters.", "tool_validation", 422, tool_name=tool_name)
            return {"supported_tasks": ["molecule_workflow", "molecular_study", "molecular_bond_scan"], "execution_mode": "logical_virtual_qpu", "is_real_qpu": False, "confirmation_required_for_task_creation": True}
        task_type, task_id = arguments.get("task_type"), arguments.get("task_id")
        if task_type not in {"molecule_workflow", "molecular_study", "molecular_bond_scan"} or not isinstance(task_id, str) or not task_id:
            raise AssistantError("assistant_tool_invalid_parameters", "Task tools require a valid task_type and task_id.", "tool_validation", 422, tool_name=tool_name)
        result = self._get_owned_task(task_type, task_id, user_id)
        if tool_name == "select_task":
            return {"task_type": task_type, "task_id": task_id, "status": result.get("status"), "selected": True, "execution_mode": "logical_virtual_qpu", "is_real_qpu": False}
        return {"task_type": task_type, "task_id": task_id, "result": self._compact_task_result(task_type, result), "execution_mode": "logical_virtual_qpu", "is_real_qpu": False}

    def _get_owned_task(self, task_type: str, task_id: str, user_id: int) -> dict[str, Any]:
        try:
            result = self.workflow_service.get(task_id, user_id) if task_type == "molecule_workflow" else self.study_service.get(task_id, user_id) if task_type == "molecular_study" else self.bond_scan_service.get(task_id, user_id)
        except MoleculeWorkflowError as exc:
            if exc.status_code != 404:
                raise AssistantError(exc.code, exc.message, exc.stage, exc.status_code, tool_name="get_current_user_result") from exc
            result = None
        if result is None:
            raise AssistantError("assistant_task_not_found", "The task does not exist or is not available to this user.", "task_lookup", 404)
        return result

    def _validate_draft_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        model = {"draft_molecule_workflow": MoleculeWorkflowRequest, "draft_molecular_study": MolecularStudyRequest, "draft_molecular_bond_scan": MolecularBondScanRequest}[tool_name]
        try:
            return model.model_validate(arguments).model_dump(mode="json")
        except ValidationError as exc:
            raise AssistantError("assistant_tool_invalid_parameters", "The draft parameters do not satisfy the molecular task contract.", "tool_validation", 422, tool_name=tool_name) from exc

    def _create_task(self, record: AssistantToolExecutionRecord, user_id: int) -> dict[str, Any]:
        request, key = dict(record.arguments_json), f"assistant-{record.execution_id}"
        if record.tool_name == "draft_molecule_workflow":
            created = self.workflow_service.execute(request, user_id, key)
            return {"task_type": "molecule_workflow", "task_id": created["workflow_id"], "status": created["status"], "response": self._compact_task_result("molecule_workflow", created)}
        if record.tool_name == "draft_molecular_study":
            # ``execution_id`` is durable before the task is created. Its
            # deterministic Study id is the recovery/idempotency basis even if
            # the process stops between domain creation and audit finalization.
            created = self.study_service.submit(
                request,
                user_id,
                study_id=f"study_asst_{record.execution_id.removeprefix('assttool_')}",
                molecular_problem_id=f"mprob_asst_{record.execution_id.removeprefix('assttool_')}",
            )
            return {"task_type": "molecular_study", "task_id": created["study_id"], "status": created["status"], "response": self._compact_task_result("molecular_study", created)}
        if record.tool_name == "draft_molecular_bond_scan":
            created = self.bond_scan_service.submit(request, user_id, key)
            return {"task_type": "molecular_bond_scan", "task_id": created["scan_id"], "status": created["status"], "response": self._compact_task_result("molecular_bond_scan", created)}
        raise AssistantError("assistant_tool_not_allowed", "The requested assistant tool is not allowed.", "task_creation", 422, tool_name=record.tool_name)

    @staticmethod
    def tool_definitions() -> list[dict[str, Any]]:
        task_ref = {"type": "object", "additionalProperties": False, "properties": {"task_type": {"type": "string", "enum": ["molecule_workflow", "molecular_study", "molecular_bond_scan"]}, "task_id": {"type": "string"}}, "required": ["task_type", "task_id"]}
        function = lambda name, description, parameters: {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
        return [
            function("platform_capabilities", "Read the molecular platform capability boundary.", {"type": "object", "additionalProperties": False, "properties": {}}),
            function("select_task", "Select one current user's task by type and id.", task_ref),
            function("get_current_user_result", "Read a compact summary of one current user's task.", task_ref),
            function("draft_molecule_workflow", "Prepare, but do not create, a Workflow pending confirmation.", MoleculeWorkflowRequest.model_json_schema()),
            function("draft_molecular_study", "Prepare, but do not create, a Study pending confirmation.", MolecularStudyRequest.model_json_schema()),
            function("draft_molecular_bond_scan", "Prepare, but do not create, a Bond Scan pending confirmation.", MolecularBondScanRequest.model_json_schema()),
        ]

    def _session(self, session_id: str, user_id: int) -> AssistantSessionRecord:
        record = self.session.query(AssistantSessionRecord).filter_by(session_id=session_id, user_id=user_id).one_or_none()
        if record is None:
            raise AssistantError("assistant_session_not_found", "The assistant session does not exist or is not available to this user.", "session_lookup", 404, session_id=session_id)
        return record

    def _append_message(self, session_record: AssistantSessionRecord, user_id: int, role: str, content: str) -> None:
        self.session.add(AssistantMessageRecord(message_id=f"asstmsg_{uuid.uuid4().hex}", session_id=session_record.session_id, user_id=user_id, role=role, content=content))
        session_record.updated_at = self._now()
        self.session.commit()

    def _history(self, session_id: str, user_id: int, *, limit: int = 40) -> list[AssistantMessageRecord]:
        """Read the newest bounded history, then restore chronological order."""
        newest_first = (
            self.session.query(AssistantMessageRecord)
            .filter_by(session_id=session_id, user_id=user_id)
            .order_by(AssistantMessageRecord.created_at.desc(), AssistantMessageRecord.message_id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(newest_first))

    def _fit_model_context(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the newest complete turns within deterministic estimated context limits."""
        current_user_index = next((index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"), None)
        if current_user_index is None:
            raise AssistantError("assistant_context_too_large", "Molecular Copilot context cannot be prepared within configured limits.", "context_window", 422)

        required_tail = messages[current_user_index:]
        if not required_tail or required_tail[0].get("role") != "user":
            raise AssistantError("assistant_context_too_large", "Molecular Copilot context cannot be prepared within configured limits.", "context_window", 422)

        prior_turns: list[list[dict[str, Any]]] = []
        active_turn: list[dict[str, Any]] | None = None
        for message in messages[:current_user_index]:
            if message.get("role") == "user":
                if active_turn:
                    prior_turns.append(active_turn)
                active_turn = [message]
            elif active_turn is not None:
                active_turn.append(message)
        if active_turn:
            prior_turns.append(active_turn)

        if self._estimated_context_tokens(required_tail) > self.limits.context_max_input_tokens:
            raise AssistantError("assistant_context_too_large", "Molecular Copilot context exceeds the configured safe limit.", "context_window", 422)

        selected = required_tail
        for turn in reversed(prior_turns):
            candidate = [*turn, *selected]
            if len(candidate) > self.limits.context_max_messages:
                break
            if self._estimated_context_tokens(candidate) > self.limits.context_max_input_tokens:
                break
            selected = candidate
        return selected

    def _estimated_context_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Conservative deterministic estimate; not provider billing-token accounting."""
        def estimate(value: Any) -> int:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return (len(encoded) + 1) // 2 + 4

        return (
            estimate({"role": "system", "content": SYSTEM_KNOWLEDGE})
            + estimate(self.tool_definitions())
            + sum(estimate(message) for message in messages)
            + self.limits.max_output_tokens
        )

    def _session_payload(self, record: AssistantSessionRecord, *, include_children: bool) -> dict[str, Any]:
        payload = {"session_id": record.session_id, "title": record.title, "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat(), "messages": [], "tool_executions": []}
        if include_children:
            payload["messages"] = [{"message_id": item.message_id, "role": item.role, "content": item.content, "created_at": item.created_at.isoformat()} for item in self._history(record.session_id, record.user_id)]
            rows = self.session.query(AssistantToolExecutionRecord).filter_by(session_id=record.session_id, user_id=record.user_id).order_by(AssistantToolExecutionRecord.created_at.asc()).all()
            payload["tool_executions"] = [self._execution_payload(item) for item in rows]
        return payload

    @staticmethod
    def _event(event: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"event": event, "data": data}

    @staticmethod
    def _assistant_tool_calls_message(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {"name": tool_call["name"], "arguments": tool_call["raw_arguments"]},
                }
                for tool_call in tool_calls
            ],
        }

    @staticmethod
    def _tool_result_message(provider_tool_call_id: str, record: AssistantToolExecutionRecord) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": provider_tool_call_id, "content": json.dumps(record.result_json, ensure_ascii=False, sort_keys=True)}

    @staticmethod
    def _ui_shortcut_result_message(record: AssistantToolExecutionRecord) -> dict[str, Any]:
        """UI shortcuts are controlled application actions, not provider tool calls."""
        return {
            "role": "assistant",
            "content": "A controlled UI shortcut completed. Tool: " + record.tool_name + ". Result: " + json.dumps(record.result_json, ensure_ascii=False, sort_keys=True),
        }

    @staticmethod
    def _parameter_summary(arguments: dict[str, Any]) -> str:
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}:{canonical}"

    @staticmethod
    def _draft_summary(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "draft_molecular_bond_scan":
            return {"molecule_type": arguments["molecule_type"], "scan": arguments["scan"], "architecture_count": len(arguments["deployment_architectures"])}
        return {"molecule_name": arguments["molecule_name"], "atom_count": len(arguments["geometry"]), "basis_set": arguments["basis_set"], "architecture_count": len(arguments.get("architectures", []))}

    @staticmethod
    def _compact_task_result(task_type: str, result: dict[str, Any]) -> dict[str, Any]:
        base = {key: result.get(key) for key in ("status", "current_stage", "execution_mode", "is_real_qpu", "error") if key in result}
        if task_type == "molecule_workflow":
            base.update({key: result.get(key) for key in ("workflow_id", "molecule_name", "validation_status", "validation_issues", "hf_energy_hartree", "fci_reference", "scientific_validation") if key in result})
            if "energies" in result:
                base["energies"] = {key: result["energies"].get(key) for key in ("unpartitioned_benchmark_energy_hartree", "distributed_simulation_energy_hartree", "absolute_error_hartree") if key in result["energies"]}
        elif task_type == "molecular_study":
            base.update({key: result.get(key) for key in ("study_id", "molecular_problem_id", "completed_evaluation_count", "total_evaluation_count") if key in result})
            if isinstance(result.get("result"), dict):
                summary = result["result"].get("summary")
                if isinstance(summary, dict): base["summary"] = summary
        else:
            base.update({key: result.get(key) for key in ("scan_id", "molecule_type", "total_point_count", "completed_point_count", "failed_point_count") if key in result})
            if isinstance(result.get("result"), dict):
                scan = result["result"]
                base["minimums"] = {key: scan.get(key) for key in ("hf_discrete_minimum", "vqe_discrete_minimum", "scientific_vqe_discrete_minimum", "fci_discrete_minimum")}
                base["engineering_only_deployment"] = scan.get("engineering_only_deployment")
        return base

    @staticmethod
    def _redact_model_content(content: str) -> str:
        redacted = _BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", content)
        redacted = _JWT_PATTERN.sub("[REDACTED]", redacted)
        redacted = _API_KEY_PATTERN.sub(lambda match: f"api_key{match.group(1)}[REDACTED]", redacted)
        return _COOKIE_PATTERN.sub("Cookie: [REDACTED]", redacted)

    @staticmethod
    def _execution_payload(record: AssistantToolExecutionRecord) -> dict[str, Any]:
        return {"execution_id": record.execution_id, "tool_name": record.tool_name, "tool_kind": record.tool_kind, "status": record.status, "parameter_summary": record.parameter_summary, "confirmation_id": record.confirmation_id, "confirmation_expires_at": record.confirmation_expires_at.isoformat() if record.confirmation_expires_at else None, "result": record.result_json}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)
