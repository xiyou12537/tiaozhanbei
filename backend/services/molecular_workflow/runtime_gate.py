"""Fail-closed Stage M-B runtime and immutable promotion-binding gates."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

from backend.database import DATABASE_PATH


class MolecularRuntimeGateError(RuntimeError):
    """Raised when the molecular write runtime has not been promoted."""


M_B_MIGRATION_ID = "20260730_01_molecular_m_b"
M_B_ACCEPTED_MANIFEST_SHA256 = (
    "e147a80532f5985b20823f5869fa6cb7e573ce054b2b59f9913777fbbf54b1e1"
)
M_B_ACCEPTED_MIGRATION_SOURCE_SHA256 = (
    "58a721a157c654c1b9f7717d3d12ec815e93106092e88dd2ea3757a8691d56b7"
)
M_B_ACCEPTED_SOURCE_EVIDENCE_SHA256 = (
    "17139a8110060aefb3be1ab59e431be68bd3ec4e3c117280ecd0cda56c40749d"
)
RUNTIME_BINDING_SCHEMA_ID = "molecular_runtime_binding_receipt"
RUNTIME_BINDING_SCHEMA_VERSION = "1.0.0"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
FORMAL_EVIDENCE_DATABASE = (WORKSPACE_ROOT / "data" / "partitioning.db").resolve()
FORMAL_ARTIFACT_ROOT = (WORKSPACE_ROOT / "data" / "structure_artifacts").resolve()
RUNTIME_ROOT = (WORKSPACE_ROOT / "data" / "runtime" / "molecular-v1").resolve()
RUNTIME_DATABASE = (RUNTIME_ROOT / "partitioning-runtime.db").resolve()
RUNTIME_ARTIFACT_ROOT = (RUNTIME_ROOT / "artifacts").resolve()
RUNTIME_LOCK_ROOT = (RUNTIME_ROOT / "locks").resolve()
RUNTIME_BINDING_RECEIPT = (
    RUNTIME_ROOT / "runtime-binding-receipt.json"
).resolve()
MIGRATION_SOURCE = (
    WORKSPACE_ROOT
    / "backend"
    / "db"
    / "migrations"
    / "legacy_sqlite"
    / "molecular_m_b.py"
).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _build_runtime_binding_receipt(
    *,
    manifest_sha256: str,
    migration_source_sha256: str,
    source_evidence_sha256: str,
    initial_runtime_database_sha256: str,
    promotion_authorization_reference: str,
    database_path: str | Path = RUNTIME_DATABASE,
    artifact_root_path: str | Path = RUNTIME_ARTIFACT_ROOT,
    source_evidence_database_path: str | Path = FORMAL_EVIDENCE_DATABASE,
) -> dict[str, Any]:
    """Build the exact immutable ledger written during a future promotion."""

    return {
        "artifact_root_path": Path(artifact_root_path).resolve().as_posix(),
        "database_path": Path(database_path).resolve().as_posix(),
        "initial_runtime_database_sha256": initial_runtime_database_sha256,
        "manifest_sha256": manifest_sha256,
        "migration_id": M_B_MIGRATION_ID,
        "migration_source_sha256": migration_source_sha256,
        "no_clobber": True,
        "promotion_authorization_reference": promotion_authorization_reference,
        "schema_id": RUNTIME_BINDING_SCHEMA_ID,
        "schema_version": RUNTIME_BINDING_SCHEMA_VERSION,
        "source_evidence_database_path": (
            Path(source_evidence_database_path).resolve().as_posix()
        ),
        "source_evidence_sha256": source_evidence_sha256,
    }


def _write_runtime_binding_receipt_no_clobber(
    receipt: dict[str, Any],
    target: str | Path = RUNTIME_BINDING_RECEIPT,
) -> str:
    """Persist a promotion receipt once; an existing target is never replaced."""

    target_path = Path(target).resolve()
    payload = _canonical_receipt_bytes(receipt)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(payload).hexdigest()


def _assert_engineering_test_context(artifact_root: Path) -> None:
    """Permit writes only inside a live pytest test and the system temp root."""

    if "pytest" not in sys.modules or not os.environ.get("PYTEST_CURRENT_TEST"):
        raise MolecularRuntimeGateError(
            "M_B_ENGINEERING_TEST_MODE requires an active pytest test."
        )
    system_temp_root = Path(tempfile.gettempdir()).resolve()
    database_path = DATABASE_PATH.resolve()
    resolved_artifact_root = artifact_root.resolve()
    if not database_path.is_relative_to(system_temp_root):
        raise MolecularRuntimeGateError(
            "Engineering database must be inside the system temporary directory."
        )
    if not resolved_artifact_root.is_relative_to(system_temp_root):
        raise MolecularRuntimeGateError(
            "Engineering Artifact root must be inside the system temporary directory."
        )


def assert_molecular_confirmation_lock_root_allowed(
    lock_root: Path,
    artifact_root: Path,
) -> None:
    """Keep attempt locks outside Artifact contracts and isolated during tests."""

    resolved_lock_root = lock_root.resolve()
    resolved_artifact_root = artifact_root.resolve()
    if resolved_lock_root.is_relative_to(resolved_artifact_root):
        raise MolecularRuntimeGateError(
            "M-B confirmation lock root must be outside the Artifact root."
        )
    engineering_test_mode = (
        os.environ.get("M_B_ENGINEERING_TEST_MODE", "").strip().lower() == "true"
    )
    if engineering_test_mode:
        system_temp_root = Path(tempfile.gettempdir()).resolve()
        if not resolved_lock_root.is_relative_to(system_temp_root):
            raise MolecularRuntimeGateError(
                "Engineering confirmation lock root must be inside the system temporary directory."
            )
        return
    if resolved_lock_root != RUNTIME_LOCK_ROOT:
        raise MolecularRuntimeGateError(
            "M-B confirmation lock root is not the frozen molecular-v1 locks path."
        )


def _load_bound_manifest() -> tuple[dict[str, Any], str]:
    manifest_path_value = os.environ.get("M_B_MIGRATION_MANIFEST_PATH", "").strip()
    expected_manifest_sha256 = os.environ.get(
        "M_B_MIGRATION_MANIFEST_SHA256",
        "",
    ).strip()
    if not manifest_path_value or len(expected_manifest_sha256) != 64:
        raise MolecularRuntimeGateError("M-B migration manifest binding is incomplete.")
    manifest_path = Path(manifest_path_value).resolve()
    if not manifest_path.is_file():
        raise MolecularRuntimeGateError("M-B migration manifest does not exist.")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
        raise MolecularRuntimeGateError("M-B migration manifest SHA-256 mismatch.")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MolecularRuntimeGateError("M-B migration manifest is invalid JSON.") from exc
    return manifest, expected_manifest_sha256


def _assert_exact_runtime_paths(artifact_root: Path) -> None:
    if DATABASE_PATH.resolve() != RUNTIME_DATABASE:
        raise MolecularRuntimeGateError(
            "M-B runtime database path is not the frozen molecular-v1 path."
        )
    if artifact_root.resolve() != RUNTIME_ARTIFACT_ROOT:
        raise MolecularRuntimeGateError(
            "M-B Artifact root is not the frozen molecular-v1 path."
        )


def _assert_frozen_bindings(
    manifest: dict[str, Any],
    manifest_sha256: str,
    artifact_root: Path,
) -> None:
    expected_migration_source_sha256 = os.environ.get(
        "M_B_MIGRATION_SOURCE_SHA256",
        "",
    ).strip()
    expected_source_evidence_sha256 = os.environ.get(
        "M_B_SOURCE_EVIDENCE_SHA256",
        "",
    ).strip()
    expected_receipt_sha256 = os.environ.get(
        "M_B_RUNTIME_BINDING_RECEIPT_SHA256",
        "",
    ).strip()
    expected_authorization_reference = os.environ.get(
        "M_B_RUNTIME_PROMOTION_AUTHORIZATION_REFERENCE",
        "",
    ).strip()
    if any(
        len(value) != 64
        for value in (
            expected_migration_source_sha256,
            expected_source_evidence_sha256,
            expected_receipt_sha256,
        )
    ) or not expected_authorization_reference:
        raise MolecularRuntimeGateError("M-B frozen runtime bindings are incomplete.")
    if (
        manifest_sha256 != M_B_ACCEPTED_MANIFEST_SHA256
        or expected_migration_source_sha256
        != M_B_ACCEPTED_MIGRATION_SOURCE_SHA256
        or expected_source_evidence_sha256
        != M_B_ACCEPTED_SOURCE_EVIDENCE_SHA256
    ):
        raise MolecularRuntimeGateError(
            "M-B runtime bindings do not match the product-accepted evidence."
        )
    _assert_exact_runtime_paths(artifact_root)
    if (
        Path(
            os.environ.get("HISTORICAL_EVIDENCE_DATABASE_PATH", "")
        ).resolve()
        != FORMAL_EVIDENCE_DATABASE
    ):
        raise MolecularRuntimeGateError(
            "Historical evidence database path is not explicitly bound."
        )
    if _sha256_file(FORMAL_EVIDENCE_DATABASE) != expected_source_evidence_sha256:
        raise MolecularRuntimeGateError("Source evidence database SHA-256 mismatch.")
    if _sha256_file(MIGRATION_SOURCE) != expected_migration_source_sha256:
        raise MolecularRuntimeGateError("M-B migration source SHA-256 mismatch.")
    if (
        manifest.get("migration_id") != M_B_MIGRATION_ID
        or manifest.get("runtime_promoted") is not False
        or manifest.get("migration_source_sha256")
        != expected_migration_source_sha256
        or manifest.get("source_sha256_before_copy")
        != expected_source_evidence_sha256
        or manifest.get("source_sha256_after_copy")
        != expected_source_evidence_sha256
    ):
        raise MolecularRuntimeGateError("M-B migration manifest bindings are invalid.")
    if not RUNTIME_BINDING_RECEIPT.is_file():
        raise MolecularRuntimeGateError("M-B runtime binding receipt does not exist.")
    receipt_bytes = RUNTIME_BINDING_RECEIPT.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha256:
        raise MolecularRuntimeGateError("M-B runtime binding receipt SHA-256 mismatch.")
    try:
        receipt = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MolecularRuntimeGateError(
            "M-B runtime binding receipt is invalid JSON."
        ) from exc
    expected_receipt = _build_runtime_binding_receipt(
        manifest_sha256=manifest_sha256,
        migration_source_sha256=expected_migration_source_sha256,
        source_evidence_sha256=expected_source_evidence_sha256,
        initial_runtime_database_sha256=manifest.get(
            "staging_sha256_after_migration",
            "",
        ),
        promotion_authorization_reference=expected_authorization_reference,
    )
    if receipt != expected_receipt:
        raise MolecularRuntimeGateError("M-B runtime binding receipt content mismatch.")


def assert_molecular_write_runtime_allowed(artifact_root: Path) -> None:
    """Allow a strictly isolated pytest context or an exactly bound runtime."""

    engineering_test_mode = (
        os.environ.get("M_B_ENGINEERING_TEST_MODE", "").strip().lower() == "true"
    )
    if engineering_test_mode:
        _assert_engineering_test_context(artifact_root)
        return
    if os.environ.get("M_B_RUNTIME_PROMOTION_AUTHORIZED", "").strip().lower() != "true":
        raise MolecularRuntimeGateError(
            "stage_m_b_runtime_promotion_authorized=false"
        )
    if (
        os.environ.get("EXPECTED_RUNTIME_MIGRATION_ID", "").strip()
        != M_B_MIGRATION_ID
    ):
        raise MolecularRuntimeGateError("M-B migration ID is not frozen.")
    _assert_exact_runtime_paths(artifact_root)
    manifest, manifest_sha256 = _load_bound_manifest()
    _assert_frozen_bindings(manifest, manifest_sha256, artifact_root)

    connection = sqlite3.connect(
        f"file:{RUNTIME_DATABASE.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        applied = connection.execute(
            "SELECT 1 FROM legacy_schema_migrations WHERE migration_id=?",
            (M_B_MIGRATION_ID,),
        ).fetchone()
        integrity_check = connection.execute("PRAGMA integrity_check").fetchall()
        quick_check = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        raise MolecularRuntimeGateError("M-B migration ledger is unavailable.") from exc
    finally:
        connection.close()
    if applied is None:
        raise MolecularRuntimeGateError("M-B migration has not been applied.")
    if integrity_check != [("ok",)] or quick_check != [("ok",)]:
        raise MolecularRuntimeGateError("M-B runtime database integrity gate failed.")
