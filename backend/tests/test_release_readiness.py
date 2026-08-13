from __future__ import annotations

import subprocess
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.services.electronic_structure.docker_adapter import (
    DockerPySCFAdapter,
    ElectronicStructureRuntimeError,
)


def test_timed_out_qchem_container_is_force_removed(monkeypatch):
    """A Docker CLI timeout must not rely solely on ``--rm`` for cleanup."""
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["docker", "version"]:
            return SimpleNamespace(returncode=0, stdout="29.6.2\n", stderr="")
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, timeout=1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(ElectronicStructureRuntimeError):
        DockerPySCFAdapter(timeout_seconds=1).generate_active_space_candidates({"operation": "test"})

    run_command = next(command for command in commands if command[:2] == ["docker", "run"])
    cleanup_command = next(command for command in commands if command[:3] == ["docker", "rm", "-f"])
    assert "--name" in run_command
    assert cleanup_command[:3] == ["docker", "rm", "-f"]


def test_transient_docker_daemon_failure_is_retried_with_safe_diagnostics(monkeypatch, caplog):
    """A cold Docker CLI failure retries once without leaking daemon output."""
    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[:2] == ["docker", "version"]:
            return SimpleNamespace(returncode=0, stdout="29.6.2\n", stderr="")
        if len([item for item in calls if item[:2] == ["docker", "run"]]) == 1:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="error during connect: open //./pipe/dockerDesktopLinuxEngine: unavailable C:/sensitive/path",
            )
        return SimpleNamespace(returncode=0, stdout='{"status":"completed"}', stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    with caplog.at_level("WARNING"):
        result = DockerPySCFAdapter().generate_active_space_candidates({"operation": "test"})

    assert result == {"status": "completed"}
    assert len([item for item in calls if item[:2] == ["docker", "run"]]) == 2
    assert "category=docker_daemon_unavailable return_code=1" in caplog.text
    assert "sensitive/path" not in caplog.text


def test_compute_capacity_rejection_is_explicit_and_does_not_run_workflow():
    """A saturated production compute slot rejects a new synchronous workflow as 503."""
    from backend.services.molecule_workflow.runtime_guard import MolecularComputeAdmissionController
    from backend.services.molecule_workflow.service import MoleculeWorkflowError, MoleculeWorkflowService

    guard = MolecularComputeAdmissionController(max_concurrent=1)
    assert guard.try_acquire() is True
    service = MoleculeWorkflowService(repository=None, compute_admission=guard)
    try:
        with pytest.raises(MoleculeWorkflowError) as error:
            service.execute({}, owner_user_id=1)
        assert error.value.code == "molecular_compute_capacity_exhausted"
        assert error.value.status_code == 503
    finally:
        guard.release()


def test_release_migration_adds_missing_columns_and_is_idempotent(tmp_path: Path):
    """The release migration upgrades a legacy SQLite copy without replacing it."""
    from backend.scripts.migrate_molecular_release import apply_molecular_release_migration

    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE molecular_bond_scans (scan_id VARCHAR(64) PRIMARY KEY, user_id INTEGER NOT NULL, request_json JSON NOT NULL)"))

    first = apply_molecular_release_migration(
        f"sqlite:///{database_path}", backup_dir=tmp_path / "backups"
    )
    second = apply_molecular_release_migration(
        f"sqlite:///{database_path}", backup_dir=tmp_path / "backups"
    )

    assert first.applied is True
    assert first.backup_path is not None and Path(first.backup_path).is_file()
    assert second.applied is False
    with engine.connect() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(molecular_bond_scans)"))}
        assert {"status", "current_stage", "result_json", "error_json", "created_at", "started_at", "completed_at"} <= columns


def test_legacy_study_and_scan_keep_unknown_release_fields_nullable():
    """GET adapters must not turn absent historical evidence into false."""
    from backend.models_db import (
        DeploymentStudyRecord,
        MolecularBondScanPointRecord,
        MolecularBondScanRecord,
        MolecularProblemRecord,
        User,
    )
    from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
    from backend.services.molecule_workflow.study_service import MolecularStudyService

    session: Session
    from backend.database import SessionLocal
    session = SessionLocal()
    suffix = "release_legacy_semantics"
    user = User(username=suffix, password_hash="v2$" + "a" * 32 + "$" + "b" * 64)
    session.add(user)
    session.flush()
    problem = MolecularProblemRecord(
        problem_id=f"mprob_{suffix}", user_id=user.id, molecule_name="H2", status="completed",
        request_json={}, result_json={"status": "completed"},
    )
    study = DeploymentStudyRecord(
        study_id=f"study_{suffix}", user_id=user.id, problem_id=problem.problem_id, status="completed",
        request_json={"architectures": []}, result_json={"molecular_problem": {"status": "completed"}, "deployment_evaluations": [], "summary": {}},
    )
    scan = MolecularBondScanRecord(
        scan_id=f"bondscan_{suffix}", user_id=user.id, request_json={"molecule_type": "LiH"},
        # This mirrors a pre-P1.2 terminal result: it exists, but lacks the
        # later deployment-selection field.
        status="completed", current_stage="completed", result_json={
            "points": [], "hf_discrete_minimum": None, "vqe_discrete_minimum": None,
            "scientific_vqe_discrete_minimum": None, "fci_discrete_minimum": None,
            "deployment_reference_point_index": None, "deployment_study_id": None,
            "deployment_result": None, "summary": {"issues": [], "minimum_at_boundary": False},
        },
    )
    point = MolecularBondScanPointRecord(
        point_id=f"bondpoint_{suffix}", scan_id=scan.scan_id, point_index=0, distance_angstrom=1.6,
        status="completed",
    )
    session.add_all([problem, study, scan, point])
    session.commit()
    try:
        study_response = MolecularStudyService(session, workflow_service=None).get(study.study_id, user.id)
        scan_response = MolecularBondScanService(session, workflow_service=None).get(scan.scan_id, user.id)
        assert study_response["result"]["molecular_problem"]["fci_reference"]["status"] == "not_configured"
        assert study_response["result"]["molecular_problem"]["fci_reference"]["energy_hartree"] is None
        assert scan_response["result"]["engineering_only_deployment"] is None
        assert "legacy_result_missing_release_fields" in scan_response["result"]["summary"]["issues"]
        assert scan_response["result"]["points"] == []
    finally:
        session.delete(point)
        session.delete(scan)
        session.delete(study)
        session.delete(problem)
        session.delete(user)
        session.commit()
        session.close()


def test_queued_and_running_scans_have_no_deployment_conclusion():
    """Partial results are unknown, not a negative engineering-only decision."""
    from backend.database import SessionLocal
    from backend.models_db import MolecularBondScanRecord, User
    from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService

    session = SessionLocal()
    suffix = "release_partial_semantics"
    user = User(username=suffix, password_hash="v2$" + "a" * 32 + "$" + "b" * 64)
    session.add(user)
    session.flush()
    scans = [
        MolecularBondScanRecord(scan_id=f"bondscan_{suffix}_{status}", user_id=user.id, request_json={"molecule_type": "LiH"}, status=status, current_stage=status)
        for status in ("queued", "running")
    ]
    session.add_all(scans)
    session.commit()
    try:
        service = MolecularBondScanService(session, workflow_service=None)
        assert all(service.get(scan.scan_id, user.id)["result"]["engineering_only_deployment"] is None for scan in scans)
    finally:
        for scan in scans:
            session.delete(scan)
        session.delete(user)
        session.commit()
        session.close()


def test_all_failed_scan_without_deployment_evidence_keeps_engineering_only_unknown():
    """A failed scan cannot claim a scientific deployment decision was made."""
    from backend.database import SessionLocal
    from backend.models_db import MolecularBondScanPointRecord, MolecularBondScanRecord, MolecularProblemRecord, User
    from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
    from backend.services.molecule_workflow.service import MoleculeWorkflowError

    class UnavailableWorkflowService:
        def execute(self, *_args, **_kwargs):
            raise MoleculeWorkflowError(
                "electronic_structure_runtime_unavailable",
                "PySCF runtime unavailable for this point.",
                "electronic_structure",
                503,
            )

    session = SessionLocal()
    suffix = "release_all_failed_semantics"
    user = User(username=suffix, password_hash="v2$" + "a" * 32 + "$" + "b" * 64)
    session.add(user)
    session.flush()
    request = {
        "molecule_type": "LiH",
        "scan": {"start_distance_angstrom": 1.0, "end_distance_angstrom": 1.1, "point_count": 2},
        "chemistry": {
            "charge": 0, "spin_multiplicity": 1, "basis_set": "sto-3g",
            "active_space_orbitals": 2, "pauli_coefficient_cutoff": 0.000001,
            "vqe": {"ansatz_layers": 1, "max_iterations": 1, "convergence_tolerance": 0.001, "shots": 64},
        },
        "deployment_architectures": [],
    }
    service = MolecularBondScanService(session, UnavailableWorkflowService())
    accepted = service.submit(request, user.id, None)
    try:
        service.execute(accepted["scan_id"], user.id)
        response = service.get(accepted["scan_id"], user.id)

        assert response["status"] == "failed"
        assert response["result"]["deployment_reference_point_index"] is None
        assert response["result"]["deployment_result"] is None
        assert response["result"]["engineering_only_deployment"] is None
    finally:
        scan_ids = [scan_id for (scan_id,) in session.query(MolecularBondScanRecord.scan_id).filter_by(user_id=user.id).all()]
        if scan_ids:
            session.query(MolecularBondScanPointRecord).filter(MolecularBondScanPointRecord.scan_id.in_(scan_ids)).delete(synchronize_session=False)
        session.query(MolecularBondScanRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
        session.query(MolecularProblemRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
        session.delete(user)
        session.commit()
        session.close()


def test_new_scan_preserves_actual_engineering_deployment_boolean():
    """New completed records retain their persisted true/false evidence on GET."""
    from backend.database import SessionLocal
    from backend.models_db import MolecularBondScanRecord, User
    from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService

    session = SessionLocal()
    suffix = "release_new_semantics"
    user = User(username=suffix, password_hash="v2$" + "a" * 32 + "$" + "b" * 64)
    session.add(user)
    session.flush()
    scans = []
    for value in (False, True):
        scan = MolecularBondScanRecord(
            scan_id=f"bondscan_{suffix}_{str(value).lower()}", user_id=user.id, request_json={"molecule_type": "LiH"},
            status="completed", current_stage="completed", result_json={
                "points": [], "hf_discrete_minimum": None, "vqe_discrete_minimum": None,
                "scientific_vqe_discrete_minimum": None, "engineering_only_deployment": value,
                "fci_discrete_minimum": None, "deployment_reference_point_index": None,
                "deployment_study_id": None, "deployment_result": None,
                "summary": {"issues": [], "minimum_at_boundary": False},
            },
        )
        scans.append(scan)
        session.add(scan)
    session.commit()
    try:
        service = MolecularBondScanService(session, workflow_service=None)
        assert [service.get(scan.scan_id, user.id)["result"]["engineering_only_deployment"] for scan in scans] == [False, True]
    finally:
        for scan in scans:
            session.delete(scan)
        session.delete(user)
        session.commit()
        session.close()


def test_frozen_openapi_contract_matches_the_release_manifest():
    """P1.2 changes deployment mechanics, never the already published API shape."""
    from backend.main import app

    manifest = Path("docs/openapi-p12.sha256")
    expected = manifest.read_text(encoding="utf-8").strip()
    canonical = json.dumps(app.openapi(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == expected
