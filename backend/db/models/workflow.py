import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.time import utc_now
from backend.db.base import Base


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    initiator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_stage: Mapped[str] = mapped_column(String(64))
    overall_status: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    input_snapshot_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_snapshot_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_view_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowStageRun(Base):
    __tablename__ = "workflow_stage_runs"

    stage_run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.workflow_id"), index=True)
    stage_name: Mapped[str] = mapped_column(String(64), index=True)
    stage_status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    service_name: Mapped[str] = mapped_column(String(100))
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskEventLog(Base):
    __tablename__ = "task_event_logs"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.workflow_id"), index=True)
    stage_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
