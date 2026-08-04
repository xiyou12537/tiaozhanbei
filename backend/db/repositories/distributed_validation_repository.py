from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.database import SessionLocal
from backend.models_db import (
    DistributedCompilationRecord,
    DistributedIdempotencyRecord,
    DistributedSimulationRecord,
    QuantumClosureBenchmarkRecord,
    QubitHamiltonianRecord,
    VqeCircuitRecord,
    VqeExecutionRecord,
)


class DistributedRepositoryError(RuntimeError):
    """Base error for distributed-validation persistence."""


class DistributedNotFoundError(DistributedRepositoryError):
    """Raised when an owner-scoped resource does not exist."""


class DistributedStateConflictError(DistributedRepositoryError):
    """Raised when a requested state transition is no longer legal."""


class DistributedIdempotencyConflictError(DistributedRepositoryError):
    """Raised when an idempotency key is reused for another request."""


class DistributedValidationRepository:
    """Persist owner-scoped compilation and simulation facts in legacy SQLite."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | Callable[[], Session] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    def create_compilation(
        self,
        *,
        values: dict[str, Any],
        idempotency_key: str,
        request_fingerprint: str,
    ) -> DistributedCompilationRecord:
        """Create one compilation or return the same idempotent resource."""
        owner_user_id = int(values["owner_user_id"])
        return self._create_with_idempotency(
            owner_user_id=owner_user_id,
            action_type="create_compilation",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            resource_type="distributed_compilation",
            resource_id=str(values["compilation_id"]),
            create=lambda session: DistributedCompilationRecord(**values),
            load=lambda session, resource_id: session.get(
                DistributedCompilationRecord,
                resource_id,
            ),
        )

    def get_compilation(
        self,
        compilation_id: str,
        owner_user_id: int,
    ) -> DistributedCompilationRecord | None:
        """Return one owner-scoped compilation."""
        with self._session_factory() as session:
            record = session.get(DistributedCompilationRecord, compilation_id)
            if record is None or record.owner_user_id != owner_user_id:
                return None
            session.expunge(record)
            return record

    def list_compilations_for_execution(
        self,
        vqe_execution_id: str,
        owner_user_id: int,
    ) -> list[DistributedCompilationRecord]:
        """Return every compilation for one owner-bound VQE execution."""
        with self._session_factory() as session:
            execution = session.get(VqeExecutionRecord, vqe_execution_id)
            if execution is None or execution.owner_user_id != owner_user_id:
                raise DistributedNotFoundError("VQE execution does not exist.")
            records = (
                session.query(DistributedCompilationRecord)
                .filter(
                    DistributedCompilationRecord.vqe_execution_id
                    == vqe_execution_id,
                    DistributedCompilationRecord.owner_user_id == owner_user_id,
                )
                .order_by(
                    DistributedCompilationRecord.created_at.asc(),
                    DistributedCompilationRecord.compilation_id.asc(),
                )
                .all()
            )
            for record in records:
                session.expunge(record)
            return records

    def update_compilation(
        self,
        compilation_id: str,
        owner_user_id: int,
        *,
        expected_row_version: int,
        values: dict[str, Any],
    ) -> DistributedCompilationRecord:
        """Apply one optimistic-locking transition to a compilation."""
        with self._session_factory() as session, session.begin():
            result = session.execute(
                update(DistributedCompilationRecord)
                .where(
                    DistributedCompilationRecord.compilation_id == compilation_id,
                    DistributedCompilationRecord.owner_user_id == owner_user_id,
                    DistributedCompilationRecord.row_version == expected_row_version,
                )
                .values(**values, row_version=expected_row_version + 1)
            )
            if result.rowcount != 1:
                raise DistributedStateConflictError(
                    "Compilation row version or owner does not match."
                )
            record = session.get(DistributedCompilationRecord, compilation_id)
            if record is None:
                raise DistributedNotFoundError("Compilation does not exist.")
            session.flush()
            session.expunge(record)
            return record

    def resolve_qualified_closure(
        self,
        *,
        owner_user_id: int,
        vqe_execution_id: str,
        benchmark_role: str,
        qualification_protocol_id: str,
        qualification_protocol_version: str,
        qualification_status: str,
    ) -> QuantumClosureBenchmarkRecord:
        """Resolve exactly one immutable qualification evidence chain."""
        with self._session_factory() as session:
            matches = (
                session.query(QuantumClosureBenchmarkRecord)
                .filter(
                    QuantumClosureBenchmarkRecord.owner_user_id == owner_user_id,
                    QuantumClosureBenchmarkRecord.vqe_execution_id
                    == vqe_execution_id,
                    QuantumClosureBenchmarkRecord.benchmark_role == benchmark_role,
                    QuantumClosureBenchmarkRecord.qualification_protocol_id
                    == qualification_protocol_id,
                    QuantumClosureBenchmarkRecord.qualification_protocol_version
                    == qualification_protocol_version,
                    QuantumClosureBenchmarkRecord.qualification_status
                    == qualification_status,
                    QuantumClosureBenchmarkRecord.qualification_recomputed.is_(False),
                )
                .all()
            )
            if len(matches) != 1:
                raise DistributedStateConflictError(
                    "Qualification evidence must resolve to exactly one immutable record."
                )
            record = matches[0]
            session.expunge(record)
            return record

    def resolve_compilation_inputs(
        self,
        *,
        owner_user_id: int,
        vqe_execution_id: str,
    ) -> tuple[
        VqeExecutionRecord,
        VqeCircuitRecord,
        QubitHamiltonianRecord,
    ]:
        """Resolve the owner-bound execution, circuit, and Hamiltonian chain."""
        with self._session_factory() as session:
            execution = session.get(VqeExecutionRecord, vqe_execution_id)
            if execution is None or execution.owner_user_id != owner_user_id:
                raise DistributedNotFoundError("VQE execution does not exist.")
            circuit = session.get(VqeCircuitRecord, execution.vqe_circuit_id)
            if circuit is None or circuit.owner_user_id != owner_user_id:
                raise DistributedStateConflictError(
                    "Owner-bound VQE circuit lineage is incomplete."
                )
            qubit_hamiltonian = session.get(
                QubitHamiltonianRecord,
                circuit.qubit_hamiltonian_id,
            )
            if (
                qubit_hamiltonian is None
                or qubit_hamiltonian.owner_user_id != owner_user_id
            ):
                raise DistributedStateConflictError(
                    "Owner-bound qubit Hamiltonian lineage is incomplete."
                )
            for record in (execution, circuit, qubit_hamiltonian):
                session.expunge(record)
            return execution, circuit, qubit_hamiltonian

    def start_formal_simulation(
        self,
        *,
        compilation_id: str,
        owner_user_id: int,
        simulation_values: dict[str, Any],
        idempotency_key: str,
        request_fingerprint: str,
    ) -> DistributedSimulationRecord:
        """Atomically consume the only formal attempt and create its simulation."""
        action_type = "start_formal_simulation"
        try:
            with self._session_factory() as session, session.begin():
                existing = self._get_idempotency(
                    session,
                    owner_user_id,
                    action_type,
                    idempotency_key,
                )
                if existing is not None:
                    self._assert_same_fingerprint(existing, request_fingerprint)
                    if existing.resource_id is None:
                        raise DistributedStateConflictError(
                            "Formal simulation idempotency record is incomplete."
                        )
                    record = session.get(
                        DistributedSimulationRecord,
                        existing.resource_id,
                    )
                    if record is None:
                        raise DistributedStateConflictError(
                            "Formal simulation resource is missing."
                        )
                    session.expunge(record)
                    return record

                consumed = session.execute(
                    update(DistributedCompilationRecord)
                    .where(
                        DistributedCompilationRecord.compilation_id == compilation_id,
                        DistributedCompilationRecord.owner_user_id == owner_user_id,
                        DistributedCompilationRecord.status
                        == "distributed_executable_ready",
                        DistributedCompilationRecord.formal_attempts_started == 0,
                        DistributedCompilationRecord.formal_attempt_limit == 1,
                    )
                    .values(
                        formal_attempts_started=1,
                        status="formal_attempt_consumed",
                        row_version=DistributedCompilationRecord.row_version + 1,
                    )
                )
                if consumed.rowcount != 1:
                    raise DistributedStateConflictError(
                        "The formal attempt is unavailable or already consumed."
                    )
                simulation = DistributedSimulationRecord(**simulation_values)
                idempotency = DistributedIdempotencyRecord(
                    owner_user_id=owner_user_id,
                    action_type=action_type,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    resource_type="distributed_simulation",
                    resource_id=simulation.simulation_id,
                    response_status="completed",
                    completed_at=datetime.utcnow(),
                )
                session.add_all((simulation, idempotency))
                session.flush()
                session.expunge(simulation)
                return simulation
        except IntegrityError as exc:
            raise DistributedStateConflictError(
                "Concurrent formal attempt consumption was rejected."
            ) from exc

    def get_simulation(
        self,
        simulation_id: str,
        owner_user_id: int,
    ) -> DistributedSimulationRecord | None:
        """Return one owner-scoped simulation."""
        with self._session_factory() as session:
            record = session.get(DistributedSimulationRecord, simulation_id)
            if record is None or record.owner_user_id != owner_user_id:
                return None
            session.expunge(record)
            return record

    def update_simulation(
        self,
        simulation_id: str,
        owner_user_id: int,
        *,
        expected_row_version: int,
        values: dict[str, Any],
    ) -> DistributedSimulationRecord:
        """Apply one optimistic-locking transition to a simulation."""
        with self._session_factory() as session, session.begin():
            result = session.execute(
                update(DistributedSimulationRecord)
                .where(
                    DistributedSimulationRecord.simulation_id == simulation_id,
                    DistributedSimulationRecord.owner_user_id == owner_user_id,
                    DistributedSimulationRecord.row_version == expected_row_version,
                )
                .values(**values, row_version=expected_row_version + 1)
            )
            if result.rowcount != 1:
                raise DistributedStateConflictError(
                    "Simulation row version or owner does not match."
                )
            record = session.get(DistributedSimulationRecord, simulation_id)
            if record is None:
                raise DistributedNotFoundError("Simulation does not exist.")
            session.flush()
            session.expunge(record)
            return record

    def _create_with_idempotency(
        self,
        *,
        owner_user_id: int,
        action_type: str,
        idempotency_key: str,
        request_fingerprint: str,
        resource_type: str,
        resource_id: str,
        create: Callable[[Session], Any],
        load: Callable[[Session, str], Any],
    ) -> Any:
        try:
            with self._session_factory() as session, session.begin():
                existing = self._get_idempotency(
                    session,
                    owner_user_id,
                    action_type,
                    idempotency_key,
                )
                if existing is not None:
                    self._assert_same_fingerprint(existing, request_fingerprint)
                    if existing.resource_id is None:
                        raise DistributedStateConflictError(
                            "Idempotent resource is incomplete."
                        )
                    record = load(session, existing.resource_id)
                    if record is None:
                        raise DistributedStateConflictError(
                            "Idempotent resource does not exist."
                        )
                    session.expunge(record)
                    return record
                record = create(session)
                session.add(record)
                session.add(
                    DistributedIdempotencyRecord(
                        owner_user_id=owner_user_id,
                        action_type=action_type,
                        idempotency_key=idempotency_key,
                        request_fingerprint=request_fingerprint,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        response_status="completed",
                        completed_at=datetime.utcnow(),
                    )
                )
                session.flush()
                session.expunge(record)
                return record
        except IntegrityError as exc:
            with self._session_factory() as session:
                existing = self._get_idempotency(
                    session,
                    owner_user_id,
                    action_type,
                    idempotency_key,
                )
                if existing is not None:
                    self._assert_same_fingerprint(existing, request_fingerprint)
                    if existing.resource_id is not None:
                        record = load(session, existing.resource_id)
                        if record is not None:
                            session.expunge(record)
                            return record
            raise DistributedStateConflictError(
                "Concurrent idempotent creation could not be resolved."
            ) from exc

    @staticmethod
    def _get_idempotency(
        session: Session,
        owner_user_id: int,
        action_type: str,
        idempotency_key: str,
    ) -> DistributedIdempotencyRecord | None:
        return (
            session.query(DistributedIdempotencyRecord)
            .filter(
                DistributedIdempotencyRecord.owner_user_id == owner_user_id,
                DistributedIdempotencyRecord.action_type == action_type,
                DistributedIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    @staticmethod
    def _assert_same_fingerprint(
        record: DistributedIdempotencyRecord,
        request_fingerprint: str,
    ) -> None:
        if record.request_fingerprint != request_fingerprint:
            raise DistributedIdempotencyConflictError(
                "Idempotency key was already used for another request."
            )
