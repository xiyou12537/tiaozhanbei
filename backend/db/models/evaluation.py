import datetime as dt
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    simulation_run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    shot_count: Mapped[int] = mapped_column(Integer)
    energy_estimate: Mapped[float] = mapped_column(Float)
    counts_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class FidelityCheck(Base):
    __tablename__ = "fidelity_checks"

    fidelity_check_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    fidelity_score: Mapped[float] = mapped_column(Float)
    depth_delta: Mapped[int] = mapped_column(Integer)
    detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)
