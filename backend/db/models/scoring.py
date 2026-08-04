import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ScoreBundle(Base):
    __tablename__ = "score_bundles"

    score_bundle_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    gatekeeping_passed: Mapped[bool] = mapped_column(Boolean)
    chem_score: Mapped[float] = mapped_column(Float)
    deploy_score: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float)
    component_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class RecommendationRank(Base):
    __tablename__ = "recommendation_ranks"

    recommendation_rank_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(120))
    rank_position: Mapped[int] = mapped_column(Integer)
    explanation_json: Mapped[dict] = mapped_column(JSONB, default=dict)
