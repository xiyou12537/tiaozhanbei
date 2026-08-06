from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models_db import MoleculeWorkflowRecord


class MoleculeWorkflowRepository:
    """Transactional persistence for user-owned molecule workflow results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, values: dict[str, Any]) -> MoleculeWorkflowRecord:
        record = MoleculeWorkflowRecord(**values)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get(self, workflow_id: str, user_id: int) -> MoleculeWorkflowRecord | None:
        return (
            self.session.query(MoleculeWorkflowRecord)
            .filter(
                MoleculeWorkflowRecord.workflow_id == workflow_id,
                MoleculeWorkflowRecord.user_id == user_id,
            )
            .first()
        )

    def get_by_idempotency_key(self, user_id: int, idempotency_key: str) -> MoleculeWorkflowRecord | None:
        return (
            self.session.query(MoleculeWorkflowRecord)
            .filter(
                MoleculeWorkflowRecord.user_id == user_id,
                MoleculeWorkflowRecord.idempotency_key == idempotency_key,
            )
            .first()
        )

    def list_for_user(
        self,
        user_id: int,
        *,
        page: int,
        page_size: int,
        molecule_name: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
    ) -> tuple[list[MoleculeWorkflowRecord], int]:
        query = self.session.query(MoleculeWorkflowRecord).filter(MoleculeWorkflowRecord.user_id == user_id)
        if molecule_name is not None:
            query = query.filter(MoleculeWorkflowRecord.molecule_name == molecule_name)
        if status is not None:
            query = query.filter(MoleculeWorkflowRecord.status == status)
        if validation_status is not None:
            query = query.filter(
                MoleculeWorkflowRecord.result_json["validation_status"].as_string() == validation_status
            )
        total = query.count()
        records = (
            query.order_by(MoleculeWorkflowRecord.created_at.desc(), MoleculeWorkflowRecord.workflow_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return records, total

    def update_progress(self, record: MoleculeWorkflowRecord, current_stage: str, stages: list[dict]) -> None:
        record.current_stage = current_stage
        record.stages_json = stages
        self.session.commit()

    def complete(self, record: MoleculeWorkflowRecord, result: dict) -> None:
        record.status = "completed"
        record.current_stage = "completed"
        record.stages_json = result["stages"]
        record.result_json = result
        record.error_json = None
        self.session.commit()

    def fail(self, record: MoleculeWorkflowRecord, error: dict, stages: list[dict]) -> None:
        record.status = "failed"
        record.current_stage = error.get("stage") or record.current_stage
        record.stages_json = stages
        record.error_json = error
        self.session.commit()
