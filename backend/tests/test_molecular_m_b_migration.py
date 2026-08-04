from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from backend.db.migrations.legacy_sqlite import molecular_m_b

FORMAL_DATABASE_SHA256 = (
    "17139a8110060aefb3be1ab59e431be68bd3ec4e3c117280ecd0cda56c40749d"
)


def _formal_database() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "partitioning.db"


def test_staging_migration_preserves_historical_rows_and_restores_constraints(
    tmp_path: Path,
) -> None:
    source = _formal_database()
    staging = tmp_path / "partitioning.stage-m-b.db"
    copy_evidence = molecular_m_b.create_verified_staging_copy(
        source,
        staging,
        FORMAL_DATABASE_SHA256,
    )
    assert copy_evidence["source_sha256_before_copy"] == FORMAL_DATABASE_SHA256
    assert copy_evidence["copy_method"] == "sqlite_backup_api"
    result = molecular_m_b.migrate_staging_database(staging)
    assert (
        result["staging_sha256_before_migration"]
        == copy_evidence["staging_sha256_before_migration"]
    )
    assert (
        result["staging_sha256_after_migration"]
        != result["staging_sha256_before_migration"]
    )
    assert result["foreign_key_check_unchanged"] is True
    assert result["integrity_check"] == ["ok"]
    assert result["quick_check"] == ["ok"]
    assert all(
        comparison["equal"]
        for comparison in result["rebuilt_table_comparison"].values()
    )
    assert molecular_m_b.sha256_file(source) == FORMAL_DATABASE_SHA256

    connection = sqlite3.connect(staging)
    try:
        purposes = connection.execute(
            "SELECT input_purpose,count(*) FROM structure_files GROUP BY input_purpose"
        ).fetchall()
        assert purposes == [("legacy_screening", 561)]
        workflow_nulls = connection.execute(
            "SELECT count(*) FROM parsed_structures WHERE workflow_id IS NULL"
        ).fetchone()[0]
        assert workflow_nulls == 0
        with pytest.raises(sqlite3.IntegrityError, match="input_purpose_immutable"):
            connection.execute(
                "UPDATE structure_files SET input_purpose='molecular_logical_circuit' "
                "WHERE file_id=(SELECT file_id FROM structure_files LIMIT 1)"
            )
        connection.rollback()
        assert connection.execute(
            "SELECT count(*) FROM legacy_schema_migrations WHERE migration_id=?",
            (molecular_m_b.MIGRATION_ID,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_injected_migration_failure_rolls_back_all_schema_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _formal_database()
    staging = tmp_path / "partitioning.rollback-test.db"
    molecular_m_b.create_verified_staging_copy(
        source,
        staging,
        FORMAL_DATABASE_SHA256,
    )

    def inject_failure(_connection: sqlite3.Connection) -> None:
        raise RuntimeError("injected migration interruption")

    monkeypatch.setattr(molecular_m_b, "_create_triggers", inject_failure)
    with pytest.raises(RuntimeError, match="injected migration interruption"):
        molecular_m_b.migrate_staging_database(staging)

    connection = sqlite3.connect(staging)
    try:
        structure_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(structure_files)")
        }
        assert "input_purpose" not in structure_columns
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='molecular_models'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM legacy_schema_migrations WHERE migration_id=?",
            (molecular_m_b.MIGRATION_ID,),
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        connection.close()
    assert molecular_m_b.sha256_file(source) == FORMAL_DATABASE_SHA256


def test_confirmation_flush_order_uses_migrated_sqlite_foreign_keys(
    tmp_path: Path,
) -> None:
    """Exercise confirmation in a fresh process bound to a migrated SQLite copy."""

    source = _formal_database()
    staging = tmp_path / "confirmation-foreign-keys.db"
    molecular_m_b.create_verified_staging_copy(
        source,
        staging,
        FORMAL_DATABASE_SHA256,
    )
    molecular_m_b.migrate_staging_database(staging)
    workspace = Path(__file__).resolve().parents[2]
    artifact_root = tmp_path / "molecular-artifacts"
    input_root = tmp_path / "molecular-inputs"
    child_environment = {
        **os.environ,
        "LEGACY_DATABASE_PATH": str(staging),
        "PLATFORM_DATA_ROOT": str(input_root),
        "MOLECULAR_ARTIFACT_ROOT": str(artifact_root),
        "M_B_ENGINEERING_TEST_MODE": "true",
        "PYTEST_CURRENT_TEST": "migrated_confirmation_foreign_keys",
    }
    child_program = r'''
import hashlib
import json
from pathlib import Path

import pytest

from backend.database import SessionLocal
from backend.models_db import (
    MolecularArtifactPublicationRecord,
    MolecularIdempotencyRecord,
    MolecularModelRecord,
    MolecularWorkflowRecord,
    QuantumRegionRecord,
)
from backend.services.molecular_workflow.service import (
    ConfirmationCrashInjected,
    MolecularWorkflowService,
)
from backend.services.structure_modeling.service import StructureModelingService

RAW_XYZ = (
    b"3\n"
    b"water example\n"
    b"O 0.000000 -0 +0.1173000E+00\n"
    b"H +0.000000 0.7571600 -0.469200\n"
    b"H .0 -7.571600e-1 -4.69200E-1\n"
)
RAW_SHA256 = "8afce8170d7283e6328010dc19fe4c180c8602c83f2a89edd16ba987058e79e7"
GEOMETRY_SHA256 = "0fa29a62d80b23dd91e04be0b6bdf0b1511cb908ea97e33f11da88a52a0586e2"
BOUNDARIES = (
    "after_confirmed_model_flush",
    "after_quantum_region_flush",
    "after_molecular_workflow_flush",
    "after_confirmation_records_flush",
    "before_confirmation_transaction_commit",
)

assert hashlib.sha256(RAW_XYZ).hexdigest() == RAW_SHA256
artifact_root = Path(__import__("os").environ["MOLECULAR_ARTIFACT_ROOT"])
session = SessionLocal()
try:
    owner_user_id = session.execute(
        __import__("sqlalchemy").text("SELECT id FROM users ORDER BY id LIMIT 1")
    ).scalar_one()
    foreign_keys_enabled = session.connection().exec_driver_sql(
        "PRAGMA foreign_keys"
    ).scalar_one()
finally:
    session.close()
assert foreign_keys_enabled == 1

structure_service = StructureModelingService()

def create_draft(index: int):
    uploaded = structure_service.upload_structure_file(
        owner_user_id=owner_user_id,
        material_name="water",
        material_family=None,
        description=None,
        original_filename=f"water-{index}.xyz",
        content=RAW_XYZ,
        input_purpose="molecular_logical_circuit",
        idempotency_key=f"migrated-upload-{index}",
    )
    parsed = structure_service.parse_structure_file(uploaded["file_id"], owner_user_id)
    service = MolecularWorkflowService(artifact_root)
    draft = service.create_model(
        structure_id=parsed["structure_id"],
        owner_user_id=owner_user_id,
        idempotency_key=f"migrated-model-{index}",
        request={
            "expected_source_file_id": uploaded["file_id"],
            "expected_source_file_sha256": RAW_SHA256,
            "expected_canonical_geometry_sha256": GEOMETRY_SHA256,
        },
    )
    return service, draft.payload["molecular_model_id"]

confirm_request = {
    "coordinate_unit": "angstrom",
    "total_charge": 0,
    "spin_multiplicity": 1,
    "expected_source_file_sha256": RAW_SHA256,
    "expected_canonical_geometry_sha256": GEOMETRY_SHA256,
    "confirmation": True,
}
rollback_results = {}
for index, boundary in enumerate(BOUNDARIES):
    service, model_id = create_draft(index)
    service._confirmation_fault_injector = (
        lambda current, expected=boundary: (
            (_ for _ in ()).throw(ConfirmationCrashInjected(expected))
            if current == expected else None
        )
    )
    key = f"migrated-confirm-rollback-{index}"
    try:
        service.confirm_model(
            molecular_model_id=model_id,
            owner_user_id=owner_user_id,
            idempotency_key=key,
            request=confirm_request,
        )
        raise AssertionError(f"fault boundary {boundary} did not raise")
    except ConfirmationCrashInjected:
        pass
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    session = SessionLocal()
    try:
        model = session.query(MolecularModelRecord).filter_by(
            molecular_model_id=model_id
        ).one()
        rollback_results[boundary] = {
            "confirmation_status": model.confirmation_status,
            "regions": session.query(QuantumRegionRecord).filter_by(
                molecular_model_id=model_id
            ).count(),
            "workflows": session.query(MolecularWorkflowRecord).filter_by(
                molecular_model_id=model_id
            ).count(),
            "journals": session.query(MolecularArtifactPublicationRecord).filter_by(
                molecular_model_id=model_id
            ).count(),
            "confirm_idempotency": session.query(MolecularIdempotencyRecord).filter_by(
                owner_user_id=owner_user_id,
                idempotency_key_hash=key_hash,
            ).count(),
        }
    finally:
        session.close()

service, normal_model_id = create_draft(len(BOUNDARIES))
normal = service.confirm_model(
    molecular_model_id=normal_model_id,
    owner_user_id=owner_user_id,
    idempotency_key="migrated-confirm-success",
    request=confirm_request,
)
session = SessionLocal()
try:
    m_c_counts = {
        table: session.connection().exec_driver_sql(
            f"SELECT count(*) FROM {table}"
        ).scalar_one()
        for table in (
            "molecular_electronic_structure_calculations",
            "molecular_stage_attempts",
            "molecular_observations",
            "molecular_logical_validations",
        )
    }
finally:
    session.close()
print(json.dumps({
    "foreign_keys_enabled": foreign_keys_enabled,
    "rollback_results": rollback_results,
    "normal_status_code": normal.status_code,
    "normal_workflow_status": normal.payload["workflow"]["workflow_status"],
    "normal_quantum_region_id": normal.payload["workflow"]["quantum_region_id"],
    "m_c_counts": m_c_counts,
    "artifact_entries": sorted(path.name for path in artifact_root.rglob("*") if path.is_file()),
}, sort_keys=True))
'''
    completed = subprocess.run(
        [sys.executable, "-c", child_program],
        cwd=workspace,
        env=child_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["foreign_keys_enabled"] == 1
    assert result["normal_status_code"] == 200
    assert result["normal_workflow_status"] == "molecular_input_frozen"
    assert result["normal_quantum_region_id"].startswith("qr_")
    assert result["m_c_counts"] == {
        "molecular_electronic_structure_calculations": 0,
        "molecular_logical_validations": 0,
        "molecular_observations": 0,
        "molecular_stage_attempts": 0,
    }
    assert len(result["artifact_entries"]) == 2
    for rollback_result in result["rollback_results"].values():
        assert rollback_result == {
            "confirmation_status": "pending_confirmation",
            "confirm_idempotency": 0,
            "journals": 0,
            "regions": 0,
            "workflows": 0,
        }
    assert molecular_m_b.sha256_file(source) == FORMAL_DATABASE_SHA256
