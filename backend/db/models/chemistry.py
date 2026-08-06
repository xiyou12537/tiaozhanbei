import datetime as dt
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class MolecularStructure(Base):
    __tablename__ = "molecular_structures"

    structure_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    candidate_name: Mapped[str] = mapped_column(String(120))
    atom_count: Mapped[int] = mapped_column(Integer)
    geometry_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class ActiveSpaceDefinition(Base):
    __tablename__ = "active_space_definitions"

    active_space_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    orbital_count: Mapped[int] = mapped_column(Integer)
    electron_count: Mapped[int] = mapped_column(Integer)
    adsorption_energy: Mapped[float] = mapped_column(Float)
    descriptor_json: Mapped[dict] = mapped_column(JSONB, default=dict)
