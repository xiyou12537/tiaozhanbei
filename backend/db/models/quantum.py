import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class QubitHamiltonian(Base):
    __tablename__ = "qubit_hamiltonians"

    hamiltonian_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    qubit_count: Mapped[int] = mapped_column(Integer)
    pauli_term_count: Mapped[int] = mapped_column(Integer)
    terms_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class QasmArtifact(Base):
    __tablename__ = "qasm_artifacts"

    artifact_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    circuit_name: Mapped[str] = mapped_column(String(120))
    qasm_content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
