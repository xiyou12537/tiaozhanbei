import datetime as dt

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class CandidateMaterial(Base):
    __tablename__ = "candidate_materials"

    candidate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    family: Mapped[str] = mapped_column(String(80))
    active_site_hint: Mapped[str] = mapped_column(String(120))
    adsorption_strength: Mapped[float] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ExperimentCase(Base):
    __tablename__ = "experiment_cases"

    case_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    candidate_name: Mapped[str] = mapped_column(String(120))
    configuration_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
