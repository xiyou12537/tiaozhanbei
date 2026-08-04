from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from backend.services.molecular_workflow.runtime_gate import (
    M_B_MIGRATION_ID,
    MIGRATION_SOURCE,
)
from backend.services.molecular_workflow.runtime_promotion import (
    MolecularRuntimePromotionError,
    promote_molecular_runtime_no_clobber,
    validate_promoted_runtime_lineage,
)


class SyntheticPromotionCrash(RuntimeError):
    """Simulate process termination at a promotion durability boundary."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _promotion_fixture(
    root: Path,
    *,
    manifest_staging_sha256: str | None = None,
) -> dict[str, Path | str]:
    root.mkdir(parents=True, exist_ok=True)
    source_evidence = root / "source-evidence.db"
    source_evidence.write_bytes(b"synthetic source evidence for M-B-R2")
    source_evidence_sha256 = _sha256(source_evidence)

    staging = root / "staging.db"
    connection = sqlite3.connect(staging)
    try:
        connection.executescript(
            """
            CREATE TABLE legacy_schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO legacy_schema_migrations(migration_id)
            VALUES ('20260730_01_molecular_m_b');
            CREATE TABLE synthetic_business_records (
                record_id INTEGER PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        connection.commit()
    finally:
        connection.close()
    staging_sha256 = _sha256(staging)
    migration_source_sha256 = _sha256(MIGRATION_SOURCE)
    manifest = {
        "migration_id": M_B_MIGRATION_ID,
        "migration_source_sha256": migration_source_sha256,
        "runtime_promoted": False,
        "source_sha256_before_copy": source_evidence_sha256,
        "source_sha256_after_copy": source_evidence_sha256,
        "staging_database_path": staging.as_posix(),
        "staging_sha256_after_migration": (
            manifest_staging_sha256 or staging_sha256
        ),
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(
        (
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    )
    runtime_root = root / "runtime"
    return {
        "manifest_path": manifest_path,
        "expected_manifest_sha256": _sha256(manifest_path),
        "staging_database_path": staging,
        "runtime_database_path": runtime_root / "partitioning-runtime.db",
        "artifact_root": runtime_root / "artifacts",
        "receipt_path": runtime_root / "runtime-binding-receipt.json",
        "source_evidence_database_path": source_evidence,
        "expected_source_evidence_sha256": source_evidence_sha256,
        "migration_source_path": MIGRATION_SOURCE,
        "expected_migration_source_sha256": migration_source_sha256,
        "promotion_authorization_reference": "synthetic-product-approval",
        "staging_sha256": staging_sha256,
    }


def _promote(fixture: dict[str, Path | str], **overrides):
    arguments = {
        key: value
        for key, value in fixture.items()
        if key
        not in {
            "staging_sha256",
        }
    }
    arguments.update(overrides)
    return promote_molecular_runtime_no_clobber(**arguments)


def test_promotion_rejects_wrong_staging_sha256(tmp_path: Path) -> None:
    fixture = _promotion_fixture(
        tmp_path / "wrong-staging",
        manifest_staging_sha256="0" * 64,
    )
    with pytest.raises(MolecularRuntimePromotionError) as error:
        _promote(fixture)
    assert error.value.code == "staging_database_sha256_mismatch"
    assert not Path(fixture["runtime_database_path"]).exists()
    assert not Path(fixture["receipt_path"]).exists()


def test_promotion_detects_post_copy_sha256_mismatch(tmp_path: Path) -> None:
    fixture = _promotion_fixture(tmp_path / "post-copy-mismatch")
    runtime_database = Path(fixture["runtime_database_path"])

    def tamper_after_copy(boundary: str) -> None:
        if boundary == "after_runtime_copy_fsync":
            with runtime_database.open("ab") as handle:
                handle.write(b"tampered-after-copy")
                handle.flush()

    with pytest.raises(MolecularRuntimePromotionError) as error:
        _promote(fixture, fault_injector=tamper_after_copy)
    assert error.value.code == "runtime_database_post_copy_sha256_mismatch"
    assert runtime_database.exists()
    assert not Path(fixture["receipt_path"]).exists()


def test_promotion_refuses_existing_receipt_without_copy(tmp_path: Path) -> None:
    fixture = _promotion_fixture(tmp_path / "receipt-exists")
    receipt_path = Path(fixture["receipt_path"])
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(b"pre-existing receipt")
    before = receipt_path.read_bytes()
    with pytest.raises(MolecularRuntimePromotionError) as error:
        _promote(fixture)
    assert error.value.code == "runtime_binding_receipt_exists"
    assert receipt_path.read_bytes() == before
    assert not Path(fixture["runtime_database_path"]).exists()


def test_promotion_crash_after_copy_before_receipt_is_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _promotion_fixture(tmp_path / "crash-before-receipt")

    def crash_before_receipt(boundary: str) -> None:
        if boundary == "before_runtime_receipt":
            raise SyntheticPromotionCrash(boundary)

    with pytest.raises(SyntheticPromotionCrash):
        _promote(fixture, fault_injector=crash_before_receipt)
    assert Path(fixture["runtime_database_path"]).is_file()
    assert Path(fixture["artifact_root"]).is_dir()
    assert not Path(fixture["receipt_path"]).exists()
    with pytest.raises(MolecularRuntimePromotionError) as retry:
        _promote(fixture)
    assert retry.value.code == "runtime_database_target_exists"


def test_promotion_rejects_legal_sqlite_write_before_receipt(
    tmp_path: Path,
) -> None:
    fixture = _promotion_fixture(tmp_path / "write-before-receipt")
    runtime_database = Path(fixture["runtime_database_path"])

    def write_before_receipt(boundary: str) -> None:
        if boundary == "before_runtime_receipt":
            connection = sqlite3.connect(runtime_database)
            try:
                connection.execute(
                    "INSERT INTO synthetic_business_records(value) VALUES (?)",
                    ("must not be bound before receipt",),
                )
                connection.commit()
            finally:
                connection.close()

    with pytest.raises(MolecularRuntimePromotionError) as error:
        _promote(fixture, fault_injector=write_before_receipt)
    assert error.value.code == "runtime_database_pre_receipt_sha256_mismatch"
    assert Path(fixture["runtime_database_path"]).is_file()
    assert not Path(fixture["receipt_path"]).exists()


def test_correct_promotion_and_restart_after_business_write(tmp_path: Path) -> None:
    assert "initial_runtime_database_sha256" not in inspect.signature(
        promote_molecular_runtime_no_clobber
    ).parameters
    fixture = _promotion_fixture(tmp_path / "success")
    result = _promote(fixture)
    runtime_database = Path(fixture["runtime_database_path"])
    receipt_path = Path(fixture["receipt_path"])
    assert result.runtime_database_initial_sha256 == fixture["staging_sha256"]
    assert result.integrity_check == ("ok",)
    assert result.quick_check == ("ok",)
    assert _sha256(runtime_database) == fixture["staging_sha256"]
    assert _sha256(receipt_path) == result.receipt_sha256

    initial_runtime_sha256 = _sha256(runtime_database)
    initial_receipt_sha256 = _sha256(receipt_path)
    connection = sqlite3.connect(runtime_database)
    try:
        connection.execute(
            "INSERT INTO synthetic_business_records(value) VALUES (?)",
            ("business write changes the whole-database SHA",),
        )
        connection.commit()
    finally:
        connection.close()
    assert _sha256(runtime_database) != initial_runtime_sha256
    assert _sha256(receipt_path) == initial_receipt_sha256

    validate_promoted_runtime_lineage(
        manifest_path=fixture["manifest_path"],
        expected_manifest_sha256=fixture["expected_manifest_sha256"],
        runtime_database_path=runtime_database,
        artifact_root=fixture["artifact_root"],
        receipt_path=receipt_path,
        expected_receipt_sha256=result.receipt_sha256,
        source_evidence_database_path=fixture[
            "source_evidence_database_path"
        ],
        expected_source_evidence_sha256=fixture[
            "expected_source_evidence_sha256"
        ],
        migration_source_path=fixture["migration_source_path"],
        expected_migration_source_sha256=fixture[
            "expected_migration_source_sha256"
        ],
        promotion_authorization_reference=fixture[
            "promotion_authorization_reference"
        ],
    )
