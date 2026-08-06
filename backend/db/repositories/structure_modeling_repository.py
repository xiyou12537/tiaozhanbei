from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.database import SessionLocal, engine
from backend.models_db import (
    ActiveSiteRecord,
    ActiveSpaceRecord,
    AdsorptionModelRecord,
    BenchmarkCaseRecord,
    ClassicalReferenceRecord,
    DftImportRecord,
    DftCalculationRecord,
    ElectronicStructureCandidateRecord,
    GeometryOptimizationRecord,
    FermionicHamiltonianRecord,
    QubitHamiltonianRecord,
    VqeCircuitRecord,
    VqeExecutionRecord,
    ParsedStructureRecord,
    QuantumRegionRecord,
    StructureFileRecord,
    StructureWorkflowRecord,
    ResearchBenchmarkArtifactRecord,
    ResearchBenchmarkCandidateRecord,
    ResearchBenchmarkRecord,
    ResearchBenchmarkSelectionRecord,
)


class StructureModelingRepository:
    """Persist user-owned structure modeling resources in the legacy SQLite database."""

    _MODELS = (
        StructureFileRecord,
        ParsedStructureRecord,
        ActiveSiteRecord,
        ActiveSpaceRecord,
        BenchmarkCaseRecord,
        ElectronicStructureCandidateRecord,
        DftImportRecord,
        DftCalculationRecord,
        ResearchBenchmarkRecord,
        ResearchBenchmarkArtifactRecord,
        ResearchBenchmarkCandidateRecord,
        ResearchBenchmarkSelectionRecord,
        ClassicalReferenceRecord,
        AdsorptionModelRecord,
        GeometryOptimizationRecord,
        FermionicHamiltonianRecord,
        QubitHamiltonianRecord,
        VqeCircuitRecord,
        VqeExecutionRecord,
        QuantumRegionRecord,
        StructureWorkflowRecord,
    )

    def __init__(self) -> None:
        self._schema_ready = False

    def create_file(self, values: dict[str, Any]) -> StructureFileRecord:
        return self._write(lambda session: self._create(session, StructureFileRecord, values))

    def get_file(self, file_id: str, owner_user_id: int) -> StructureFileRecord | None:
        return self._read(lambda session: self._owned(session, StructureFileRecord, "file_id", file_id, owner_user_id))

    def list_files(self, owner_user_id: int, parse_status: str | None, offset: int, limit: int) -> tuple[list[StructureFileRecord], int]:
        self._ensure_schema()
        session = SessionLocal()
        try:
            query = session.query(StructureFileRecord).filter(StructureFileRecord.owner_user_id == owner_user_id)
            if parse_status:
                query = query.filter(StructureFileRecord.parse_status == parse_status)
            total = query.count()
            records = query.order_by(StructureFileRecord.created_at.desc()).offset(offset).limit(limit).all()
            return records, total
        finally:
            session.close()

    def update_file(self, file_id: str, owner_user_id: int, **values: Any) -> StructureFileRecord | None:
        return self._write(lambda session: self._update_owned(session, StructureFileRecord, "file_id", file_id, owner_user_id, values))

    def save_structure(self, values: dict[str, Any]) -> ParsedStructureRecord:
        return self._write(lambda session: self._create(session, ParsedStructureRecord, values))

    def get_structure(self, structure_id: str, owner_user_id: int) -> ParsedStructureRecord | None:
        return self._read(lambda session: self._owned(session, ParsedStructureRecord, "structure_id", structure_id, owner_user_id))

    def create_workflow(self, values: dict[str, Any]) -> StructureWorkflowRecord:
        return self._write(lambda session: self._create(session, StructureWorkflowRecord, values))

    def get_workflow(self, workflow_id: str, owner_user_id: int) -> StructureWorkflowRecord | None:
        return self._read(lambda session: self._owned(session, StructureWorkflowRecord, "workflow_id", workflow_id, owner_user_id))

    def list_workflows(
        self,
        owner_user_id: int,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[StructureWorkflowRecord], int]:
        self._ensure_schema()
        session = SessionLocal()
        try:
            query = session.query(StructureWorkflowRecord).filter(
                StructureWorkflowRecord.owner_user_id == owner_user_id
            )
            if status:
                query = query.filter(StructureWorkflowRecord.status == status)
            total = query.count()
            records = query.order_by(StructureWorkflowRecord.updated_at.desc()).offset(offset).limit(limit).all()
            return records, total
        finally:
            session.close()

    def get_workflow_resources(self, workflow_id: str, owner_user_id: int) -> dict[str, Any] | None:
        """Load the owned object graph used by workflow stages and Artifact authorization."""
        self._ensure_schema()
        session = SessionLocal()
        try:
            workflow = self._owned(
                session,
                StructureWorkflowRecord,
                "workflow_id",
                workflow_id,
                owner_user_id,
            )
            if workflow is None:
                return None
            structure = self._owned(
                session,
                ParsedStructureRecord,
                "structure_id",
                workflow.structure_id,
                owner_user_id,
            )
            source_file = (
                self._owned(session, StructureFileRecord, "file_id", structure.file_id, owner_user_id)
                if structure is not None
                else None
            )
            active_sites = (
                session.query(ActiveSiteRecord)
                .filter(
                    ActiveSiteRecord.structure_id == workflow.structure_id,
                    ActiveSiteRecord.owner_user_id == owner_user_id,
                )
                .order_by(ActiveSiteRecord.created_at.asc())
                .all()
            )
            active_site_ids = [record.active_site_id for record in active_sites]
            adsorption_models = self._query_owned_by_ids(
                session,
                AdsorptionModelRecord,
                AdsorptionModelRecord.active_site_id,
                active_site_ids,
                owner_user_id,
            )
            adsorption_model_ids = [record.adsorption_model_id for record in adsorption_models]
            geometry_optimizations = self._query_owned_by_ids(
                session,
                GeometryOptimizationRecord,
                GeometryOptimizationRecord.adsorption_model_id,
                adsorption_model_ids,
                owner_user_id,
            )
            dft_imports = self._query_owned_by_ids(
                session,
                DftImportRecord,
                DftImportRecord.adsorption_model_id,
                adsorption_model_ids,
                owner_user_id,
            )
            dft_calculations = self._query_owned_by_ids(
                session,
                DftCalculationRecord,
                DftCalculationRecord.adsorption_model_id,
                adsorption_model_ids,
                owner_user_id,
            )
            quantum_regions = self._query_owned_by_ids(
                session,
                QuantumRegionRecord,
                QuantumRegionRecord.adsorption_model_id,
                adsorption_model_ids,
                owner_user_id,
            )
            quantum_region_ids = [record.quantum_region_id for record in quantum_regions]
            electronic_candidates = self._query_owned_by_ids(
                session,
                ElectronicStructureCandidateRecord,
                ElectronicStructureCandidateRecord.quantum_region_id,
                quantum_region_ids,
                owner_user_id,
            )
            active_spaces = self._query_owned_by_ids(
                session,
                ActiveSpaceRecord,
                ActiveSpaceRecord.quantum_region_id,
                quantum_region_ids,
                owner_user_id,
            )
            active_space_ids = [record.active_space_id for record in active_spaces]
            fermionic_hamiltonians = self._query_owned_by_ids(
                session,
                FermionicHamiltonianRecord,
                FermionicHamiltonianRecord.active_space_id,
                active_space_ids,
                owner_user_id,
            )
            fermionic_ids = [record.hamiltonian_id for record in fermionic_hamiltonians]
            classical_references = self._query_owned_by_ids(
                session,
                ClassicalReferenceRecord,
                ClassicalReferenceRecord.fermionic_hamiltonian_id,
                fermionic_ids,
                owner_user_id,
            )
            qubit_hamiltonians = self._query_owned_by_ids(
                session,
                QubitHamiltonianRecord,
                QubitHamiltonianRecord.fermionic_hamiltonian_id,
                fermionic_ids,
                owner_user_id,
            )
            qubit_ids = [record.qubit_hamiltonian_id for record in qubit_hamiltonians]
            vqe_circuits = self._query_owned_by_ids(
                session,
                VqeCircuitRecord,
                VqeCircuitRecord.qubit_hamiltonian_id,
                qubit_ids,
                owner_user_id,
            )
            circuit_ids = [record.vqe_circuit_id for record in vqe_circuits]
            vqe_executions = self._query_owned_by_ids(
                session,
                VqeExecutionRecord,
                VqeExecutionRecord.vqe_circuit_id,
                circuit_ids,
                owner_user_id,
            )
            benchmark_cases = (
                session.query(BenchmarkCaseRecord)
                .filter(BenchmarkCaseRecord.owner_user_id == owner_user_id)
                .order_by(BenchmarkCaseRecord.created_at.asc())
                .all()
            )
            literature_selections = (
                session.query(ResearchBenchmarkSelectionRecord)
                .filter(
                    ResearchBenchmarkSelectionRecord.workflow_id == workflow_id,
                    ResearchBenchmarkSelectionRecord.owner_user_id == owner_user_id,
                )
                .all()
            )
            literature_candidate_ids = [record.candidate_id for record in literature_selections]
            literature_candidates = (
                session.query(ResearchBenchmarkCandidateRecord)
                .filter(ResearchBenchmarkCandidateRecord.candidate_id.in_(literature_candidate_ids))
                .all()
                if literature_candidate_ids
                else []
            )
            return {
                "workflow": workflow,
                "structure": structure,
                "source_file": source_file,
                "active_sites": active_sites,
                "adsorption_models": adsorption_models,
                "geometry_optimizations": geometry_optimizations,
                "dft_imports": dft_imports,
                "dft_calculations": dft_calculations,
                "quantum_regions": quantum_regions,
                "electronic_candidates": electronic_candidates,
                "active_spaces": active_spaces,
                "fermionic_hamiltonians": fermionic_hamiltonians,
                "classical_references": classical_references,
                "qubit_hamiltonians": qubit_hamiltonians,
                "vqe_circuits": vqe_circuits,
                "vqe_executions": vqe_executions,
                "benchmark_cases": benchmark_cases,
                "literature_selections": literature_selections,
                "literature_candidates": literature_candidates,
            }
        finally:
            session.close()

    def update_workflow(self, workflow_id: str, owner_user_id: int, **values: Any) -> StructureWorkflowRecord | None:
        return self._write(lambda session: self._update_owned(session, StructureWorkflowRecord, "workflow_id", workflow_id, owner_user_id, values))

    def create_active_site(self, values: dict[str, Any]) -> ActiveSiteRecord:
        return self._write(lambda session: self._create(session, ActiveSiteRecord, values))

    def get_active_site(self, active_site_id: str, owner_user_id: int) -> ActiveSiteRecord | None:
        return self._read(lambda session: self._owned(session, ActiveSiteRecord, "active_site_id", active_site_id, owner_user_id))

    def list_active_sites(self, structure_id: str, owner_user_id: int) -> list[ActiveSiteRecord]:
        return self._read(
            lambda session: session.query(ActiveSiteRecord)
            .filter(ActiveSiteRecord.structure_id == structure_id, ActiveSiteRecord.owner_user_id == owner_user_id)
            .order_by(ActiveSiteRecord.created_at.asc())
            .all()
        ) or []

    def update_active_site(self, active_site_id: str, owner_user_id: int, **values: Any) -> ActiveSiteRecord | None:
        return self._write(lambda session: self._update_owned(session, ActiveSiteRecord, "active_site_id", active_site_id, owner_user_id, values))

    def create_adsorption_model(self, values: dict[str, Any]) -> AdsorptionModelRecord:
        return self._write(lambda session: self._create(session, AdsorptionModelRecord, values))

    def get_adsorption_model(self, adsorption_model_id: str, owner_user_id: int) -> AdsorptionModelRecord | None:
        return self._read(
            lambda session: self._owned(session, AdsorptionModelRecord, "adsorption_model_id", adsorption_model_id, owner_user_id)
        )

    def create_geometry_optimization(self, values: dict[str, Any]) -> GeometryOptimizationRecord:
        return self._write(lambda session: self._create(session, GeometryOptimizationRecord, values))

    def get_geometry_optimization(self, geometry_optimization_id: str, owner_user_id: int) -> GeometryOptimizationRecord | None:
        return self._read(
            lambda session: self._owned(
                session,
                GeometryOptimizationRecord,
                "geometry_optimization_id",
                geometry_optimization_id,
                owner_user_id,
            )
        )

    def create_quantum_region(self, values: dict[str, Any]) -> QuantumRegionRecord:
        return self._write(lambda session: self._create(session, QuantumRegionRecord, values))

    def get_quantum_region(self, quantum_region_id: str, owner_user_id: int) -> QuantumRegionRecord | None:
        return self._read(lambda session: self._owned(session, QuantumRegionRecord, "quantum_region_id", quantum_region_id, owner_user_id))

    def update_quantum_region(self, quantum_region_id: str, owner_user_id: int, **values: Any) -> QuantumRegionRecord | None:
        return self._write(
            lambda session: self._update_owned(
                session,
                QuantumRegionRecord,
                "quantum_region_id",
                quantum_region_id,
                owner_user_id,
                values,
            )
        )

    def create_active_space(self, values: dict[str, Any]) -> ActiveSpaceRecord:
        return self._write(lambda session: self._create(session, ActiveSpaceRecord, values))

    def get_active_space(self, active_space_id: str, owner_user_id: int) -> ActiveSpaceRecord | None:
        return self._read(lambda session: self._owned(session, ActiveSpaceRecord, "active_space_id", active_space_id, owner_user_id))

    def update_active_space(self, active_space_id: str, owner_user_id: int, **values: Any) -> ActiveSpaceRecord | None:
        return self._write(lambda session: self._update_owned(session, ActiveSpaceRecord, "active_space_id", active_space_id, owner_user_id, values))

    def create_benchmark_case(self, values: dict[str, Any]) -> BenchmarkCaseRecord:
        return self._write(lambda session: self._create(session, BenchmarkCaseRecord, values))

    def get_benchmark_case(self, benchmark_case_id: str, owner_user_id: int) -> BenchmarkCaseRecord | None:
        return self._read(lambda session: self._owned(session, BenchmarkCaseRecord, "benchmark_case_id", benchmark_case_id, owner_user_id))

    def update_benchmark_case(self, benchmark_case_id: str, owner_user_id: int, **values: Any) -> BenchmarkCaseRecord | None:
        return self._write(
            lambda session: self._update_owned(
                session,
                BenchmarkCaseRecord,
                "benchmark_case_id",
                benchmark_case_id,
                owner_user_id,
                values,
            )
        )

    def create_electronic_structure_candidate(self, values: dict[str, Any]) -> ElectronicStructureCandidateRecord:
        return self._write(lambda session: self._create(session, ElectronicStructureCandidateRecord, values))

    def get_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int) -> ElectronicStructureCandidateRecord | None:
        return self._read(lambda session: self._owned(session, ElectronicStructureCandidateRecord, "candidate_id", candidate_id, owner_user_id))

    def update_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int, **values: Any) -> ElectronicStructureCandidateRecord | None:
        return self._write(lambda session: self._update_owned(session, ElectronicStructureCandidateRecord, "candidate_id", candidate_id, owner_user_id, values))

    def create_dft_import(self, values: dict[str, Any]) -> DftImportRecord:
        return self._write(lambda session: self._create(session, DftImportRecord, values))

    def get_dft_import(self, dft_import_id: str, owner_user_id: int) -> DftImportRecord | None:
        return self._read(lambda session: self._owned(session, DftImportRecord, "dft_import_id", dft_import_id, owner_user_id))

    def create_dft_calculation(self, values: dict[str, Any]) -> DftCalculationRecord:
        return self._write(lambda session: self._create(session, DftCalculationRecord, values))

    def get_dft_calculation(self, dft_calculation_id: str, owner_user_id: int) -> DftCalculationRecord | None:
        return self._read(
            lambda session: self._owned(session, DftCalculationRecord, "dft_calculation_id", dft_calculation_id, owner_user_id)
        )

    def update_dft_calculation(self, dft_calculation_id: str, owner_user_id: int, **values: Any) -> DftCalculationRecord | None:
        return self._write(
            lambda session: self._update_owned(
                session,
                DftCalculationRecord,
                "dft_calculation_id",
                dft_calculation_id,
                owner_user_id,
                values,
            )
        )

    def create_research_benchmark(self, values: dict[str, Any]) -> ResearchBenchmarkRecord:
        return self._write(lambda session: self._create(session, ResearchBenchmarkRecord, values))

    def get_research_benchmark_by_key(self, benchmark_key: str) -> ResearchBenchmarkRecord | None:
        return self._read(
            lambda session: session.query(ResearchBenchmarkRecord).filter(ResearchBenchmarkRecord.benchmark_key == benchmark_key).first()
        )

    def get_research_benchmark(self, benchmark_id: str) -> ResearchBenchmarkRecord | None:
        return self._read(
            lambda session: session.query(ResearchBenchmarkRecord).filter(ResearchBenchmarkRecord.benchmark_id == benchmark_id).first()
        )

    def list_research_benchmarks(self, benchmark_key: str | None = None) -> list[ResearchBenchmarkRecord]:
        """Return imported public benchmarks, optionally narrowed to one stable key."""
        def query_benchmarks(session):
            query = session.query(ResearchBenchmarkRecord)
            if benchmark_key:
                query = query.filter(ResearchBenchmarkRecord.benchmark_key == benchmark_key)
            return query.order_by(ResearchBenchmarkRecord.created_at.desc()).all()

        return self._read(query_benchmarks) or []

    def create_research_benchmark_artifact(self, values: dict[str, Any]) -> ResearchBenchmarkArtifactRecord:
        return self._write(lambda session: self._create(session, ResearchBenchmarkArtifactRecord, values))

    def create_research_benchmark_candidate(self, values: dict[str, Any]) -> ResearchBenchmarkCandidateRecord:
        return self._write(lambda session: self._create(session, ResearchBenchmarkCandidateRecord, values))

    def list_research_benchmark_candidates(self, benchmark_id: str) -> list[ResearchBenchmarkCandidateRecord]:
        return self._read(
            lambda session: session.query(ResearchBenchmarkCandidateRecord)
            .filter(ResearchBenchmarkCandidateRecord.benchmark_id == benchmark_id)
            .order_by(ResearchBenchmarkCandidateRecord.priority_rank.asc())
            .all()
        ) or []

    def get_research_benchmark_candidate(self, benchmark_id: str, candidate_id: str) -> ResearchBenchmarkCandidateRecord | None:
        return self._read(
            lambda session: session.query(ResearchBenchmarkCandidateRecord)
            .filter(
                ResearchBenchmarkCandidateRecord.benchmark_id == benchmark_id,
                ResearchBenchmarkCandidateRecord.candidate_id == candidate_id,
            )
            .first()
        )

    def create_research_benchmark_selection(self, values: dict[str, Any]) -> ResearchBenchmarkSelectionRecord:
        return self._write(lambda session: self._create(session, ResearchBenchmarkSelectionRecord, values))

    def create_classical_reference(self, values: dict[str, Any]) -> ClassicalReferenceRecord:
        return self._write(lambda session: self._create(session, ClassicalReferenceRecord, values))

    def get_latest_classical_reference(
        self,
        fermionic_hamiltonian_id: str,
        owner_user_id: int,
    ) -> ClassicalReferenceRecord | None:
        self._ensure_schema()
        session = SessionLocal()
        try:
            return (
                session.query(ClassicalReferenceRecord)
                .filter(
                    ClassicalReferenceRecord.fermionic_hamiltonian_id == fermionic_hamiltonian_id,
                    ClassicalReferenceRecord.owner_user_id == owner_user_id,
                    ClassicalReferenceRecord.status == "completed",
                )
                .order_by(ClassicalReferenceRecord.created_at.desc())
                .first()
            )
        finally:
            session.close()

    def create_fermionic_hamiltonian(self, values: dict[str, Any]) -> FermionicHamiltonianRecord:
        return self._write(lambda session: self._create(session, FermionicHamiltonianRecord, values))

    def get_fermionic_hamiltonian(self, hamiltonian_id: str, owner_user_id: int) -> FermionicHamiltonianRecord | None:
        return self._read(lambda session: self._owned(session, FermionicHamiltonianRecord, "hamiltonian_id", hamiltonian_id, owner_user_id))

    def create_qubit_hamiltonian(self, values: dict[str, Any]) -> QubitHamiltonianRecord:
        return self._write(lambda session: self._create(session, QubitHamiltonianRecord, values))

    def get_qubit_hamiltonian(self, qubit_hamiltonian_id: str, owner_user_id: int) -> QubitHamiltonianRecord | None:
        return self._read(lambda session: self._owned(session, QubitHamiltonianRecord, "qubit_hamiltonian_id", qubit_hamiltonian_id, owner_user_id))

    def create_vqe_circuit(self, values: dict[str, Any]) -> VqeCircuitRecord:
        return self._write(lambda session: self._create(session, VqeCircuitRecord, values))

    def get_vqe_circuit(self, vqe_circuit_id: str, owner_user_id: int) -> VqeCircuitRecord | None:
        return self._read(lambda session: self._owned(session, VqeCircuitRecord, "vqe_circuit_id", vqe_circuit_id, owner_user_id))

    def create_vqe_execution(self, values: dict[str, Any]) -> VqeExecutionRecord:
        return self._write(lambda session: self._create(session, VqeExecutionRecord, values))

    def get_vqe_execution(self, execution_id: str, owner_user_id: int) -> VqeExecutionRecord | None:
        return self._read(lambda session: self._owned(session, VqeExecutionRecord, "execution_id", execution_id, owner_user_id))

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for model in self._MODELS:
            model.__table__.create(bind=engine, checkfirst=True)
        self._ensure_additive_columns(
            "quantum_region_models",
            {"geometry_optimization_id": "VARCHAR(64)"},
        )
        self._ensure_additive_columns(
            "structure_qubit_hamiltonians",
            {
                "qubit_count_before_tapering": "INTEGER",
                "symmetry_tapering_applied": "INTEGER NOT NULL DEFAULT 0",
                "tapered_symmetries": "JSON NOT NULL DEFAULT '[]'",
                "tapering_reason": "TEXT",
                "truncation_error_estimate": "FLOAT NOT NULL DEFAULT 0.0",
            },
        )
        self._ensure_additive_columns(
            "vqe_executions",
            {
                "execution_backend_detail": "VARCHAR(128)",
                "energy_uncertainty_method": "VARCHAR(64)",
            },
        )
        self._ensure_additive_columns(
            "active_sites",
            {"confirmed_at": "DATETIME"},
        )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE active_sites SET confirmed_at = updated_at "
                    "WHERE status = 'confirmed' AND confirmed_at IS NULL"
                )
            )
        self._schema_ready = True

    @staticmethod
    def _ensure_additive_columns(table_name: str, columns: dict[str, str]) -> None:
        """Apply only additive SQLite migrations so existing local research data is preserved."""
        column_names = {column["name"] for column in inspect(engine).get_columns(table_name)}
        with engine.begin() as connection:
            for column_name, column_type in columns.items():
                if column_name not in column_names:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

    def _read(self, action: Callable[[Session], Any]) -> Any:
        self._ensure_schema()
        session = SessionLocal()
        try:
            return action(session)
        finally:
            session.close()

    def _write(self, action: Callable[[Session], Any]) -> Any:
        self._ensure_schema()
        session = SessionLocal()
        try:
            value = action(session)
            if value is None:
                session.rollback()
                return None
            session.commit()
            session.refresh(value)
            return value
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _create(session: Session, model: type, values: dict[str, Any]):
        record = model(**values)
        session.add(record)
        session.flush()
        return record

    @staticmethod
    def _query_owned_by_ids(
        session: Session,
        model: type,
        relation_column,
        resource_ids: list[str],
        owner_user_id: int,
    ) -> list[Any]:
        if not resource_ids:
            return []
        query = session.query(model).filter(
            relation_column.in_(resource_ids),
            model.owner_user_id == owner_user_id,
        )
        created_at = getattr(model, "created_at", None)
        return query.order_by(created_at.asc()).all() if created_at is not None else query.all()

    @staticmethod
    def _owned(session: Session, model: type, id_field: str, resource_id: str, owner_user_id: int):
        return session.query(model).filter(
            getattr(model, id_field) == resource_id,
            model.owner_user_id == owner_user_id,
        ).first()

    def _update_owned(
        self,
        session: Session,
        model: type,
        id_field: str,
        resource_id: str,
        owner_user_id: int,
        values: dict[str, Any],
    ):
        record = self._owned(session, model, id_field, resource_id, owner_user_id)
        if record is None:
            return None
        for key, value in values.items():
            setattr(record, key, value)
        session.flush()
        return record
