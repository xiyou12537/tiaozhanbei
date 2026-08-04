from __future__ import annotations

import uuid

from backend.core.enums import StageName, WorkflowStatus
from backend.db.repositories.workflow_repository import WorkflowRepository
from backend.orchestrator.dispatcher import build_stage_message
from backend.orchestrator.stage_machine import execution_stage_names, next_stage_after_success, result_stage_names
from backend.workers.runtime import run_stage


class OrchestratorEngine:
    def __init__(self, dispatcher=None, repository: WorkflowRepository | None = None):
        self.dispatcher = dispatcher
        self.repository = repository or WorkflowRepository()

    def execution_stage_names(self) -> list[str]:
        return execution_stage_names()

    def result_stage_names(self) -> list[str]:
        return result_stage_names()

    def full_stage_names(self) -> list[str]:
        return self.execution_stage_names() + self.result_stage_names()

    def initial_stage(self) -> StageName:
        return StageName.SCREENING

    def initial_status(self) -> WorkflowStatus:
        return WorkflowStatus.CREATED

    def build_initial_workflow_payload(self, workflow_id: str | None, candidate_material: str) -> dict:
        workflow_id = workflow_id or str(uuid.uuid4())
        return {
            "workflow_id": workflow_id,
            "overall_status": self.initial_status().value,
            "current_stage": self.initial_stage().value,
            "candidate_material": candidate_material,
        }

    def build_stage_payload(self, state: dict, stage_name: str) -> dict:
        return self.repository.build_stage_payload(state, stage_name)

    def next_stage_name(self, current_stage: str) -> str | None:
        next_stage = next_stage_after_success(StageName(current_stage))
        return None if next_stage is None else next_stage.value

    def create_workflow_record(self, workflow: dict) -> dict:
        workflow_id = workflow["workflow_id"]
        state = dict(workflow)
        self.repository.create_workflow(state, total_stage_count=len(self.full_stage_names()))
        self.repository.append_event(
            workflow_id,
            "workflow_created",
            None,
            {"current_stage": state["current_stage"], "candidate_material": state["candidate_material"]},
        )
        self.repository.save_state(workflow_id, state)
        created = self.repository.get_workflow(workflow_id)
        if created is None:
            raise KeyError(f"Workflow '{workflow_id}' was not created.")
        return created

    def enqueue_workflow(self, workflow: dict, trace_id: str | None = None) -> dict:
        self.create_workflow_record(workflow)
        self.dispatch_stage(
            workflow_id=workflow["workflow_id"],
            stage_name=self.initial_stage().value,
            attempt_no=1,
            trace_id=trace_id or str(uuid.uuid4()),
        )
        queued = self.repository.get_workflow(workflow["workflow_id"])
        if queued is None:
            raise KeyError(f"Workflow '{workflow['workflow_id']}' not found after enqueue.")
        return queued

    def execute_workflow(self, workflow: dict) -> dict:
        workflow_id = workflow["workflow_id"]
        state = dict(workflow)
        self.create_workflow_record(state)

        for index, stage_name in enumerate(self.full_stage_names(), start=1):
            state = self._execute_single_stage(
                workflow_id=workflow_id,
                state=state,
                stage_name=stage_name,
                attempt_no=1,
                completed_stage_count=index - 1,
            )

        self._complete_workflow(workflow_id, state)
        final_workflow = self.repository.get_workflow(workflow_id)
        if final_workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' not found after execution.")
        return final_workflow

    def process_stage_message(self, message: dict) -> dict:
        workflow_id = message["workflow_id"]
        stage_name = message["stage_name"]
        attempt_no = message.get("attempt_no", 1)
        state = self.repository.get_state(workflow_id)
        workflow = self.repository.get_workflow(workflow_id)
        if state is None or workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' state not found.")

        updated_state = self._execute_single_stage(
            workflow_id=workflow_id,
            state=state,
            stage_name=stage_name,
            attempt_no=attempt_no,
            completed_stage_count=workflow["completed_stage_count"],
        )
        next_stage = self.next_stage_name(stage_name)
        if next_stage is None:
            self._complete_workflow(workflow_id, updated_state)
        else:
            self.dispatch_stage(
                workflow_id=workflow_id,
                stage_name=next_stage,
                attempt_no=1,
                trace_id=message.get("trace_id", str(uuid.uuid4())),
            )
        current = self.repository.get_workflow(workflow_id)
        if current is None:
            raise KeyError(f"Workflow '{workflow_id}' not found after stage processing.")
        return current

    def dispatch_stage(self, workflow_id: str, stage_name: str, attempt_no: int, trace_id: str) -> dict:
        payload = build_stage_message(workflow_id, stage_name, attempt_no, trace_id)
        self.repository.append_event(workflow_id, "stage_dispatched", stage_name, {"attempt_no": attempt_no})
        if self.dispatcher is not None:
            self.dispatcher.dispatch(payload)
        return payload

    def dispatch_first_stage(self, workflow_id: str, trace_id: str) -> dict:
        return self.dispatch_stage(workflow_id, self.initial_stage().value, 1, trace_id)

    def _execute_single_stage(
        self,
        *,
        workflow_id: str,
        state: dict,
        stage_name: str,
        attempt_no: int,
        completed_stage_count: int,
    ) -> dict:
        self.repository.start_stage_run(workflow_id, stage_name, attempt_no=attempt_no)
        self.repository.update_workflow(
            workflow_id,
            current_stage=stage_name,
            overall_status=stage_name,
            completed_stage_count=completed_stage_count,
        )
        self.repository.append_event(workflow_id, "stage_started", stage_name, {"attempt_no": attempt_no})
        stage_payload = self.repository.build_stage_payload(state, stage_name)
        stage_output = run_stage(stage_name, stage_payload)
        next_state = self.repository.merge_stage_output(state, stage_output)
        self.repository.save_state(workflow_id, next_state)
        self.repository.finish_stage_run(workflow_id, stage_name, stage_output)
        self.repository.update_workflow(
            workflow_id,
            current_stage=stage_name,
            overall_status=stage_name,
            completed_stage_count=completed_stage_count + 1,
        )
        self.repository.append_event(workflow_id, "stage_succeeded", stage_name, {"attempt_no": attempt_no})
        return next_state

    def _complete_workflow(self, workflow_id: str, state: dict) -> None:
        if "result_view" in state:
            self.repository.save_result_view(workflow_id, state["result_view"])
        self.repository.append_event(
            workflow_id,
            "workflow_completed",
            StageName.AGGREGATING.value,
            {"completed_stage_count": len(self.full_stage_names())},
        )
