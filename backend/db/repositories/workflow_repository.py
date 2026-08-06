from __future__ import annotations

import copy
import json
import uuid

from backend.core.enums import StageRunStatus, WorkflowStatus
from backend.core.time import utc_now


class WorkflowRepository:
    def __init__(self, enable_db_mirror: bool = True):
        self.enable_db_mirror = enable_db_mirror
        self.clear()

    def clear(self) -> None:
        self._workflows: dict[str, dict] = {}
        self._states: dict[str, dict] = {}
        self._stage_runs: dict[str, list[dict]] = {}
        self._events: dict[str, list[dict]] = {}
        self._result_views: dict[str, dict] = {}

    def create_workflow(self, workflow: dict, total_stage_count: int) -> dict:
        workflow_id = workflow["workflow_id"]
        record = {
            "workflow_id": workflow_id,
            "overall_status": workflow["overall_status"],
            "current_stage": workflow["current_stage"],
            "candidate_material": workflow["candidate_material"],
            "completed_stage_count": 0,
            "total_stage_count": total_stage_count,
        }
        self._workflows[workflow_id] = record
        self._states[workflow_id] = copy.deepcopy(workflow)
        self._stage_runs[workflow_id] = []
        self._events[workflow_id] = []
        self._mirror_create_workflow(workflow, total_stage_count)
        return copy.deepcopy(record)

    def has_workflow(self, workflow_id: str) -> bool:
        return workflow_id in self._workflows or self.get_workflow(workflow_id) is not None

    def get_workflow(self, workflow_id: str) -> dict | None:
        workflow = self._load_workflow_from_db(workflow_id)
        if workflow is not None:
            self._workflows[workflow_id] = workflow
            return copy.deepcopy(workflow)
        workflow = self._workflows.get(workflow_id)
        if workflow is not None:
            return copy.deepcopy(workflow)
        return None

    def get_state(self, workflow_id: str) -> dict | None:
        state = self._load_state_from_db(workflow_id)
        if state is not None:
            self._states[workflow_id] = state
            return copy.deepcopy(state)
        state = self._states.get(workflow_id)
        if state is not None:
            return copy.deepcopy(state)
        return None

    def save_state(self, workflow_id: str, state: dict) -> None:
        self._states[workflow_id] = copy.deepcopy(state)
        self._mirror_save_state(workflow_id, state)

    def update_workflow(
        self,
        workflow_id: str,
        *,
        current_stage: str,
        overall_status: str,
        completed_stage_count: int | None = None,
    ) -> dict:
        workflow = self._workflows.get(workflow_id) or self._load_workflow_from_db(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' not found.")
        self._workflows[workflow_id] = workflow
        workflow["current_stage"] = current_stage
        workflow["overall_status"] = overall_status
        if completed_stage_count is not None:
            workflow["completed_stage_count"] = completed_stage_count
        self._mirror_update_workflow(workflow_id, workflow)
        return copy.deepcopy(workflow)

    def append_event(self, workflow_id: str, event_type: str, stage_name: str | None, payload: dict) -> dict:
        self._events.setdefault(workflow_id, [])
        event = {
            "event_index": len(self._events[workflow_id]) + 1,
            "event_type": event_type,
            "stage_name": stage_name,
            "payload": copy.deepcopy(payload),
        }
        self._events[workflow_id].append(event)
        self._mirror_append_event(workflow_id, event)
        return copy.deepcopy(event)

    def list_events(self, workflow_id: str) -> list[dict]:
        events = self._load_events_from_db(workflow_id)
        if events:
            self._events[workflow_id] = events
            return copy.deepcopy(events)
        events = self._events.get(workflow_id)
        if events:
            return copy.deepcopy(events)
        return copy.deepcopy(events or [])

    def start_stage_run(self, workflow_id: str, stage_name: str, attempt_no: int = 1) -> dict:
        self._stage_runs.setdefault(workflow_id, [])
        run = {
            "stage_name": stage_name,
            "stage_status": StageRunStatus.RUNNING.value,
            "attempt_no": attempt_no,
            "service_name": stage_name,
            "output": None,
        }
        self._stage_runs[workflow_id].append(run)
        self._mirror_start_stage_run(workflow_id, run)
        return copy.deepcopy(run)

    def finish_stage_run(self, workflow_id: str, stage_name: str, output: dict) -> dict:
        for run in reversed(self._stage_runs[workflow_id]):
            if run["stage_name"] == stage_name and run["stage_status"] == StageRunStatus.RUNNING.value:
                run["stage_status"] = StageRunStatus.SUCCESS.value
                run["output"] = copy.deepcopy(output)
                self._mirror_finish_stage_run(workflow_id, run)
                return copy.deepcopy(run)
        raise KeyError(f"Running stage '{stage_name}' not found for workflow '{workflow_id}'.")

    def list_stage_runs(self, workflow_id: str) -> list[dict]:
        runs = self._load_stage_runs_from_db(workflow_id)
        if runs:
            self._stage_runs[workflow_id] = runs
            return copy.deepcopy(runs)
        runs = self._stage_runs.get(workflow_id)
        if runs:
            return copy.deepcopy(runs)
        return copy.deepcopy(runs or [])

    def save_result_view(self, workflow_id: str, result_view: dict) -> dict:
        self._result_views[workflow_id] = copy.deepcopy(result_view)
        self._mirror_save_result_view(workflow_id, result_view)
        self.update_workflow(
            workflow_id,
            current_stage=result_view["stage_name"],
            overall_status=WorkflowStatus.COMPLETED.value,
            completed_stage_count=self._workflows[workflow_id]["total_stage_count"],
        )
        return copy.deepcopy(result_view)

    def get_result_view(self, workflow_id: str) -> dict | None:
        result_view = self._load_result_view_from_db(workflow_id)
        if result_view is not None:
            self._result_views[workflow_id] = result_view
            return copy.deepcopy(result_view)
        result_view = self._result_views.get(workflow_id)
        if result_view is not None:
            return copy.deepcopy(result_view)
        return None

    def build_stage_payload(self, state: dict, stage_name: str) -> dict:
        payload = {"workflow_id": state["workflow_id"], "stage_name": stage_name}
        payload.update(state)
        return payload

    def merge_stage_output(self, state: dict, stage_output: dict) -> dict:
        merged = dict(state)
        merged.update({key: value for key, value in stage_output.items() if key != "status"})
        return merged

    def _with_session(self, action) -> None:
        if not self.enable_db_mirror:
            return
        try:
            from backend.database import get_session_local
            from backend.db.models.workflow import TaskEventLog, WorkflowInstance, WorkflowStageRun
            session_factory = get_session_local()
        except Exception:
            return

        session = session_factory()
        try:
            action(session, WorkflowInstance, WorkflowStageRun, TaskEventLog)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def _read_session(self, action):
        if not self.enable_db_mirror:
            return None
        try:
            from backend.database import get_session_local
            from backend.db.models.workflow import TaskEventLog, WorkflowInstance, WorkflowStageRun
            session_factory = get_session_local()
        except Exception:
            return None

        session = session_factory()
        try:
            return action(session, WorkflowInstance, WorkflowStageRun, TaskEventLog)
        except Exception:
            return None
        finally:
            session.close()

    def _mirror_create_workflow(self, workflow: dict, total_stage_count: int) -> None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            workflow_id = uuid.UUID(str(workflow["workflow_id"]))
            instance = session.get(WorkflowInstance, workflow_id)
            if instance is None:
                instance = WorkflowInstance(
                    workflow_id=workflow_id,
                    initiator_user_id=workflow.get("initiator_user_id"),
                    case_id=workflow.get("case_id"),
                    current_stage=workflow["current_stage"],
                    overall_status=workflow["overall_status"],
                    priority=workflow.get("priority", 0),
                    input_snapshot_ref=json.dumps(
                        {
                            "candidate_material": workflow.get("candidate_material"),
                            "total_stage_count": total_stage_count,
                        },
                        ensure_ascii=False,
                    ),
                    state_snapshot_ref=json.dumps(workflow, ensure_ascii=False),
                    started_at=utc_now(),
                )
                session.add(instance)

        self._with_session(action)

    def _mirror_update_workflow(self, workflow_id: str, workflow: dict) -> None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None:
                return
            instance.current_stage = workflow["current_stage"]
            instance.overall_status = workflow["overall_status"]
            instance.updated_at = utc_now()
            if workflow["overall_status"] == WorkflowStatus.COMPLETED.value:
                instance.finished_at = utc_now()

        self._with_session(action)

    def _mirror_append_event(self, workflow_id: str, event: dict) -> None:
        def action(session, _WorkflowInstance, _WorkflowStageRun, TaskEventLog):
            session.add(
                TaskEventLog(
                    workflow_id=uuid.UUID(str(workflow_id)),
                    stage_name=event["stage_name"],
                    event_type=event["event_type"],
                    payload=event["payload"],
                )
            )

        self._with_session(action)

    def _mirror_start_stage_run(self, workflow_id: str, run: dict) -> None:
        def action(session, _WorkflowInstance, WorkflowStageRun, _TaskEventLog):
            session.add(
                WorkflowStageRun(
                    workflow_id=uuid.UUID(str(workflow_id)),
                    stage_name=run["stage_name"],
                    stage_status=run["stage_status"],
                    attempt_no=run["attempt_no"],
                    service_name=run["service_name"],
                    created_at=utc_now(),
                    started_at=utc_now(),
                )
            )

        self._with_session(action)

    def _mirror_finish_stage_run(self, workflow_id: str, run: dict) -> None:
        def action(session, _WorkflowInstance, WorkflowStageRun, _TaskEventLog):
            row = (
                session.query(WorkflowStageRun)
                .filter(
                    WorkflowStageRun.workflow_id == uuid.UUID(str(workflow_id)),
                    WorkflowStageRun.stage_name == run["stage_name"],
                    WorkflowStageRun.attempt_no == run["attempt_no"],
                )
                .order_by(WorkflowStageRun.stage_run_id.desc())
                .first()
            )
            if row is None:
                return
            row.stage_status = run["stage_status"]
            row.output_ref = json.dumps(run["output"], ensure_ascii=False)
            row.finished_at = utc_now()

        self._with_session(action)

    def _mirror_save_result_view(self, workflow_id: str, result_view: dict) -> None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None:
                return
            instance.result_view_ref = json.dumps(result_view, ensure_ascii=False)
            instance.updated_at = utc_now()

        self._with_session(action)

    def _mirror_save_state(self, workflow_id: str, state: dict) -> None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None:
                return
            instance.state_snapshot_ref = json.dumps(state, ensure_ascii=False)
            instance.updated_at = utc_now()

        self._with_session(action)

    def _load_workflow_from_db(self, workflow_id: str) -> dict | None:
        def action(session, WorkflowInstance, WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None:
                return None
            total_stage_count = 0
            candidate_material = ""
            if instance.input_snapshot_ref:
                snapshot = json.loads(instance.input_snapshot_ref)
                total_stage_count = int(snapshot.get("total_stage_count", 0))
                candidate_material = snapshot.get("candidate_material", "")
            completed_stage_count = (
                session.query(WorkflowStageRun)
                .filter(
                    WorkflowStageRun.workflow_id == instance.workflow_id,
                    WorkflowStageRun.stage_status == StageRunStatus.SUCCESS.value,
                )
                .count()
            )
            return {
                "workflow_id": str(instance.workflow_id),
                "overall_status": instance.overall_status,
                "current_stage": instance.current_stage,
                "candidate_material": candidate_material,
                "completed_stage_count": completed_stage_count,
                "total_stage_count": total_stage_count,
            }

        return self._read_session(action)

    def _load_stage_runs_from_db(self, workflow_id: str) -> list[dict]:
        def action(session, _WorkflowInstance, WorkflowStageRun, _TaskEventLog):
            rows = (
                session.query(WorkflowStageRun)
                .filter(WorkflowStageRun.workflow_id == uuid.UUID(str(workflow_id)))
                .order_by(WorkflowStageRun.stage_run_id.asc())
                .all()
            )
            runs = []
            for row in rows:
                runs.append(
                    {
                        "stage_name": row.stage_name,
                        "stage_status": row.stage_status,
                        "attempt_no": row.attempt_no,
                        "service_name": row.service_name,
                        "output": json.loads(row.output_ref) if row.output_ref else None,
                    }
                )
            return runs

        return self._read_session(action) or []

    def _load_events_from_db(self, workflow_id: str) -> list[dict]:
        def action(session, _WorkflowInstance, _WorkflowStageRun, TaskEventLog):
            rows = (
                session.query(TaskEventLog)
                .filter(TaskEventLog.workflow_id == uuid.UUID(str(workflow_id)))
                .order_by(TaskEventLog.event_id.asc())
                .all()
            )
            events = []
            for index, row in enumerate(rows, start=1):
                events.append(
                    {
                        "event_index": index,
                        "event_type": row.event_type,
                        "stage_name": row.stage_name,
                        "payload": row.payload,
                    }
                )
            return events

        return self._read_session(action) or []

    def _load_result_view_from_db(self, workflow_id: str) -> dict | None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None or not instance.result_view_ref:
                return None
            return json.loads(instance.result_view_ref)

        return self._read_session(action)

    def _load_state_from_db(self, workflow_id: str) -> dict | None:
        def action(session, WorkflowInstance, _WorkflowStageRun, _TaskEventLog):
            instance = session.get(WorkflowInstance, uuid.UUID(str(workflow_id)))
            if instance is None or not instance.state_snapshot_ref:
                return None
            return json.loads(instance.state_snapshot_ref)

        return self._read_session(action)
