import datetime as dt
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class PartitionResult(Base):
    __tablename__ = "partition_results"

    partition_result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    partition_count: Mapped[int] = mapped_column(Integer)
    teleportations: Mapped[int] = mapped_column(Integer)
    elapsed_seconds: Mapped[float] = mapped_column(Float)
    partitions_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class MappingResult(Base):
    __tablename__ = "mapping_results"

    mapping_result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.workflow_id"),
        index=True,
    )
    subgraph_cost: Mapped[float] = mapped_column(Float)
    total_epr_cost: Mapped[int] = mapped_column(Integer)
    mapping_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    topology_json: Mapped[dict] = mapped_column(JSONB, default=dict)
