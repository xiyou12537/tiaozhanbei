from __future__ import annotations

import copy
import datetime as dt

from sqlalchemy.orm import Session

from backend.database import SessionLocal, engine
from backend.models_db import ScreeningWorkflowRecord


class ScreeningWorkflowRepository:
    """Persist screening workflow payloads in the legacy SQLite database."""

    def __init__(self):
        self._schema_ready = False

    def save_workflow(self, workflow: dict) -> dict:
        self._ensure_schema()
        session = SessionLocal()
        try:
            record = session.get(ScreeningWorkflowRecord, workflow["workflow_id"])
            if record is None:
                record = ScreeningWorkflowRecord(workflow_id=workflow["workflow_id"])
                session.add(record)

            record.case_id = workflow["case_id"]
            record.status = workflow["status"]
            record.candidate_count = workflow["candidate_count"]
            record.recommended_material = workflow["recommended_material"]
            record.workflow_payload = copy.deepcopy(workflow)
            session.commit()
            session.refresh(record)
            return self._to_payload(record)
        finally:
            session.close()

    def get_workflow(self, workflow_id: str) -> dict | None:
        self._ensure_schema()
        session = SessionLocal()
        try:
            record = session.get(ScreeningWorkflowRecord, workflow_id)
            if record is None:
                return None
            return self._to_payload(record)
        finally:
            session.close()

    def list_workflows(self, limit: int = 20) -> list[dict]:
        self._ensure_schema()
        session = SessionLocal()
        try:
            rows = (
                session.query(ScreeningWorkflowRecord)
                .order_by(ScreeningWorkflowRecord.created_at.desc(), ScreeningWorkflowRecord.workflow_id.desc())
                .limit(limit)
                .all()
            )
            return [self._to_summary(row) for row in rows]
        finally:
            session.close()

    def delete_workflow(self, workflow_id: str) -> None:
        self._ensure_schema()
        session = SessionLocal()
        try:
            session.query(ScreeningWorkflowRecord).filter(
                ScreeningWorkflowRecord.workflow_id == workflow_id
            ).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()

    def _to_payload(self, record: ScreeningWorkflowRecord) -> dict:
        payload = copy.deepcopy(record.workflow_payload or {})
        payload["created_at"] = self._format_dt(record.created_at)
        payload["updated_at"] = self._format_dt(record.updated_at)
        return payload

    def _to_summary(self, record: ScreeningWorkflowRecord) -> dict:
        return {
            "workflow_id": record.workflow_id,
            "case_id": record.case_id,
            "status": record.status,
            "candidate_count": record.candidate_count,
            "recommended_material": record.recommended_material,
            "created_at": self._format_dt(record.created_at),
            "updated_at": self._format_dt(record.updated_at),
        }

    def _format_dt(self, value: dt.datetime | None) -> str:
        if value is None:
            return ""
        return value.isoformat()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        ScreeningWorkflowRecord.__table__.create(bind=engine, checkfirst=True)
        self._schema_ready = True
