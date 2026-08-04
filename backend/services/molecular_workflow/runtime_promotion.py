"""Single no-clobber Stage M-B runtime promotion primitive."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_gate import (
    FORMAL_EVIDENCE_DATABASE,
    M_B_ACCEPTED_MANIFEST_SHA256,
    M_B_ACCEPTED_MIGRATION_SOURCE_SHA256,
    M_B_ACCEPTED_SOURCE_EVIDENCE_SHA256,
    M_B_MIGRATION_ID,
    MIGRATION_SOURCE,
    RUNTIME_ARTIFACT_ROOT,
    RUNTIME_BINDING_RECEIPT,
    RUNTIME_DATABASE,
    _build_runtime_binding_receipt,
    _write_runtime_binding_receipt_no_clobber,
)


class MolecularRuntimePromotionError(RuntimeError):
    """Stable fail-closed promotion error."""

    def __init__(self, code: str, stage: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage


@dataclass(frozen=True)
class MolecularRuntimePromotionResult:
    """Actual evidence produced by one successful promotion."""

    runtime_database_path: str
    runtime_database_initial_sha256: str
    artifact_root_path: str
    receipt_path: str
    receipt_sha256: str
    migration_id: str
    integrity_check: tuple[str, ...]
    quick_check: tuple[str, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(
    manifest_path: Path,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise MolecularRuntimePromotionError(
            "promotion_manifest_missing",
            "manifest_validation",
            "Accepted migration manifest does not exist.",
        )
    manifest_bytes = manifest_path.read_bytes()
    actual_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_sha256 != expected_manifest_sha256:
        raise MolecularRuntimePromotionError(
            "promotion_manifest_sha256_mismatch",
            "manifest_validation",
            "Migration manifest SHA-256 does not match the accepted binding.",
        )
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MolecularRuntimePromotionError(
            "promotion_manifest_invalid",
            "manifest_validation",
            "Migration manifest is not valid UTF-8 JSON.",
        ) from exc
    return manifest


def _is_product_layout(
    runtime_database_path: Path,
    artifact_root: Path,
    receipt_path: Path,
) -> bool:
    return (
        runtime_database_path == RUNTIME_DATABASE
        and artifact_root == RUNTIME_ARTIFACT_ROOT
        and receipt_path == RUNTIME_BINDING_RECEIPT
    )


def _assert_promotion_authority_and_paths(
    *,
    manifest_path: Path,
    staging_database_path: Path,
    runtime_database_path: Path,
    artifact_root: Path,
    receipt_path: Path,
    source_evidence_database_path: Path,
    migration_source_path: Path,
    expected_manifest_sha256: str,
    expected_migration_source_sha256: str,
    expected_source_evidence_sha256: str,
) -> None:
    if _is_product_layout(runtime_database_path, artifact_root, receipt_path):
        if (
            os.environ.get("M_B_RUNTIME_PROMOTION_AUTHORIZED", "").strip().lower()
            != "true"
        ):
            raise MolecularRuntimePromotionError(
                "runtime_promotion_not_authorized",
                "promotion_authority",
                "stage_m_b_runtime_promotion_authorized=false",
            )
        if (
            expected_manifest_sha256 != M_B_ACCEPTED_MANIFEST_SHA256
            or expected_migration_source_sha256
            != M_B_ACCEPTED_MIGRATION_SOURCE_SHA256
            or expected_source_evidence_sha256
            != M_B_ACCEPTED_SOURCE_EVIDENCE_SHA256
            or source_evidence_database_path != FORMAL_EVIDENCE_DATABASE
            or migration_source_path != MIGRATION_SOURCE
        ):
            raise MolecularRuntimePromotionError(
                "runtime_promotion_binding_not_accepted",
                "promotion_authority",
                "Production promotion bindings differ from accepted evidence.",
            )
        return

    if "pytest" not in sys.modules or not os.environ.get("PYTEST_CURRENT_TEST"):
        raise MolecularRuntimePromotionError(
            "synthetic_promotion_requires_pytest",
            "promotion_authority",
            "Synthetic promotion is allowed only inside an active pytest test.",
        )
    system_temp_root = Path(tempfile.gettempdir()).resolve()
    mutable_or_fixture_paths = (
        manifest_path,
        staging_database_path,
        runtime_database_path,
        artifact_root,
        receipt_path,
        source_evidence_database_path,
    )
    if any(
        not path.is_relative_to(system_temp_root)
        for path in mutable_or_fixture_paths
    ):
        raise MolecularRuntimePromotionError(
            "synthetic_promotion_path_not_temporary",
            "promotion_authority",
            "Synthetic promotion paths must all be inside the system temp root.",
        )


def _validate_manifest_lineage(
    *,
    manifest: dict[str, Any],
    migration_source_path: Path,
    source_evidence_database_path: Path,
    expected_migration_source_sha256: str,
    expected_source_evidence_sha256: str,
) -> str:
    actual_migration_source_sha256 = _sha256_file(migration_source_path)
    actual_source_evidence_sha256 = _sha256_file(source_evidence_database_path)
    staging_sha256 = manifest.get("staging_sha256_after_migration")
    if (
        manifest.get("migration_id") != M_B_MIGRATION_ID
        or manifest.get("runtime_promoted") is not False
        or manifest.get("migration_source_sha256")
        != expected_migration_source_sha256
        or actual_migration_source_sha256 != expected_migration_source_sha256
        or manifest.get("source_sha256_before_copy")
        != expected_source_evidence_sha256
        or manifest.get("source_sha256_after_copy")
        != expected_source_evidence_sha256
        or actual_source_evidence_sha256 != expected_source_evidence_sha256
        or not isinstance(staging_sha256, str)
        or len(staging_sha256) != 64
    ):
        raise MolecularRuntimePromotionError(
            "promotion_lineage_binding_invalid",
            "lineage_validation",
            "Manifest, migration source, or source evidence lineage is invalid.",
        )
    return staging_sha256


def _copy_file_no_clobber(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            while True:
                chunk = source_handle.read(1024 * 1024)
                if not chunk:
                    break
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
    except FileExistsError as exc:
        raise MolecularRuntimePromotionError(
            "runtime_database_target_exists",
            "runtime_copy_no_clobber",
            "Runtime database target already exists.",
        ) from exc


def _check_runtime_database(
    runtime_database_path: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    connection = sqlite3.connect(
        f"file:{runtime_database_path.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        applied = connection.execute(
            "SELECT 1 FROM legacy_schema_migrations WHERE migration_id=?",
            (M_B_MIGRATION_ID,),
        ).fetchone()
        integrity = tuple(
            row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()
        )
        quick = tuple(
            row[0] for row in connection.execute("PRAGMA quick_check").fetchall()
        )
    except sqlite3.Error as exc:
        raise MolecularRuntimePromotionError(
            "runtime_database_validation_failed",
            "runtime_database_validation",
            "Runtime migration ledger or SQLite checks are unavailable.",
        ) from exc
    finally:
        connection.close()
    if applied is None:
        raise MolecularRuntimePromotionError(
            "runtime_migration_ledger_missing",
            "runtime_database_validation",
            "Frozen M-B migration ID is missing from the runtime ledger.",
        )
    if integrity != ("ok",) or quick != ("ok",):
        raise MolecularRuntimePromotionError(
            "runtime_database_integrity_failed",
            "runtime_database_validation",
            "Runtime integrity_check or quick_check failed.",
        )
    return integrity, quick


def promote_molecular_runtime_no_clobber(
    *,
    manifest_path: str | Path,
    expected_manifest_sha256: str,
    staging_database_path: str | Path,
    runtime_database_path: str | Path,
    artifact_root: str | Path,
    receipt_path: str | Path,
    source_evidence_database_path: str | Path,
    expected_source_evidence_sha256: str,
    migration_source_path: str | Path,
    expected_migration_source_sha256: str,
    promotion_authorization_reference: str,
    fault_injector: Callable[[str], None] | None = None,
) -> MolecularRuntimePromotionResult:
    """Promote verified staging bytes and derive the receipt from actual bytes."""

    paths = {
        "manifest": Path(manifest_path).resolve(),
        "staging": Path(staging_database_path).resolve(),
        "runtime": Path(runtime_database_path).resolve(),
        "artifact_root": Path(artifact_root).resolve(),
        "receipt": Path(receipt_path).resolve(),
        "source_evidence": Path(source_evidence_database_path).resolve(),
        "migration_source": Path(migration_source_path).resolve(),
    }
    _assert_promotion_authority_and_paths(
        manifest_path=paths["manifest"],
        staging_database_path=paths["staging"],
        runtime_database_path=paths["runtime"],
        artifact_root=paths["artifact_root"],
        receipt_path=paths["receipt"],
        source_evidence_database_path=paths["source_evidence"],
        migration_source_path=paths["migration_source"],
        expected_manifest_sha256=expected_manifest_sha256,
        expected_migration_source_sha256=expected_migration_source_sha256,
        expected_source_evidence_sha256=expected_source_evidence_sha256,
    )
    manifest = _read_manifest(paths["manifest"], expected_manifest_sha256)
    expected_staging_sha256 = _validate_manifest_lineage(
        manifest=manifest,
        migration_source_path=paths["migration_source"],
        source_evidence_database_path=paths["source_evidence"],
        expected_migration_source_sha256=expected_migration_source_sha256,
        expected_source_evidence_sha256=expected_source_evidence_sha256,
    )
    manifest_staging_path = manifest.get("staging_database_path")
    if (
        not isinstance(manifest_staging_path, str)
        or Path(manifest_staging_path).resolve() != paths["staging"]
    ):
        raise MolecularRuntimePromotionError(
            "staging_database_path_mismatch",
            "staging_validation",
            "Staging database path differs from the accepted manifest.",
        )
    if not paths["staging"].is_file():
        raise MolecularRuntimePromotionError(
            "staging_database_missing",
            "staging_validation",
            "Staging database does not exist.",
        )
    actual_staging_sha256 = _sha256_file(paths["staging"])
    if actual_staging_sha256 != expected_staging_sha256:
        raise MolecularRuntimePromotionError(
            "staging_database_sha256_mismatch",
            "staging_validation",
            "Staging database SHA-256 differs from the accepted manifest.",
        )
    if paths["runtime"].exists():
        raise MolecularRuntimePromotionError(
            "runtime_database_target_exists",
            "promotion_preflight",
            "Runtime database target already exists.",
        )
    if paths["receipt"].exists():
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_exists",
            "promotion_preflight",
            "Runtime binding receipt already exists.",
        )
    if paths["artifact_root"].exists():
        raise MolecularRuntimePromotionError(
            "runtime_artifact_root_exists",
            "promotion_preflight",
            "Runtime Artifact root already exists.",
        )

    _copy_file_no_clobber(paths["staging"], paths["runtime"])
    if fault_injector is not None:
        fault_injector("after_runtime_copy_fsync")
    actual_runtime_sha256 = _sha256_file(paths["runtime"])
    if actual_runtime_sha256 != expected_staging_sha256:
        raise MolecularRuntimePromotionError(
            "runtime_database_post_copy_sha256_mismatch",
            "runtime_copy_verification",
            "Copied runtime database differs from accepted staging bytes.",
        )
    try:
        paths["artifact_root"].mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise MolecularRuntimePromotionError(
            "runtime_artifact_root_exists",
            "artifact_root_no_clobber",
            "Runtime Artifact root was created concurrently.",
        ) from exc
    if fault_injector is not None:
        fault_injector("before_runtime_receipt")
    integrity, quick = _check_runtime_database(paths["runtime"])
    final_runtime_sha256 = _sha256_file(paths["runtime"])
    if final_runtime_sha256 != expected_staging_sha256:
        raise MolecularRuntimePromotionError(
            "runtime_database_pre_receipt_sha256_mismatch",
            "pre_receipt_runtime_verification",
            "Runtime database changed before its binding receipt was written.",
        )
    receipt = _build_runtime_binding_receipt(
        manifest_sha256=expected_manifest_sha256,
        migration_source_sha256=expected_migration_source_sha256,
        source_evidence_sha256=expected_source_evidence_sha256,
        initial_runtime_database_sha256=final_runtime_sha256,
        promotion_authorization_reference=promotion_authorization_reference,
        database_path=paths["runtime"],
        artifact_root_path=paths["artifact_root"],
        source_evidence_database_path=paths["source_evidence"],
    )
    try:
        receipt_sha256 = _write_runtime_binding_receipt_no_clobber(
            receipt,
            paths["receipt"],
        )
    except FileExistsError as exc:
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_exists",
            "receipt_no_clobber",
            "Runtime binding receipt already exists.",
        ) from exc
    return MolecularRuntimePromotionResult(
        runtime_database_path=paths["runtime"].as_posix(),
        runtime_database_initial_sha256=final_runtime_sha256,
        artifact_root_path=paths["artifact_root"].as_posix(),
        receipt_path=paths["receipt"].as_posix(),
        receipt_sha256=receipt_sha256,
        migration_id=M_B_MIGRATION_ID,
        integrity_check=integrity,
        quick_check=quick,
    )


def validate_promoted_runtime_lineage(
    *,
    manifest_path: str | Path,
    expected_manifest_sha256: str,
    runtime_database_path: str | Path,
    artifact_root: str | Path,
    receipt_path: str | Path,
    expected_receipt_sha256: str,
    source_evidence_database_path: str | Path,
    expected_source_evidence_sha256: str,
    migration_source_path: str | Path,
    expected_migration_source_sha256: str,
    promotion_authorization_reference: str,
) -> None:
    """Validate immutable lineage without pinning the mutable runtime DB SHA."""

    manifest_path = Path(manifest_path).resolve()
    runtime_database_path = Path(runtime_database_path).resolve()
    artifact_root = Path(artifact_root).resolve()
    receipt_path = Path(receipt_path).resolve()
    source_evidence_database_path = Path(source_evidence_database_path).resolve()
    migration_source_path = Path(migration_source_path).resolve()
    manifest = _read_manifest(manifest_path, expected_manifest_sha256)
    initial_runtime_sha256 = _validate_manifest_lineage(
        manifest=manifest,
        migration_source_path=migration_source_path,
        source_evidence_database_path=source_evidence_database_path,
        expected_migration_source_sha256=expected_migration_source_sha256,
        expected_source_evidence_sha256=expected_source_evidence_sha256,
    )
    if not receipt_path.is_file():
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_missing",
            "lineage_restart_validation",
            "Runtime binding receipt is missing.",
        )
    receipt_bytes = receipt_path.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != expected_receipt_sha256:
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_sha256_mismatch",
            "lineage_restart_validation",
            "Runtime binding receipt SHA-256 mismatch.",
        )
    try:
        actual_receipt = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_invalid",
            "lineage_restart_validation",
            "Runtime binding receipt is not valid JSON.",
        ) from exc
    expected_receipt = _build_runtime_binding_receipt(
        manifest_sha256=expected_manifest_sha256,
        migration_source_sha256=expected_migration_source_sha256,
        source_evidence_sha256=expected_source_evidence_sha256,
        initial_runtime_database_sha256=initial_runtime_sha256,
        promotion_authorization_reference=promotion_authorization_reference,
        database_path=runtime_database_path,
        artifact_root_path=artifact_root,
        source_evidence_database_path=source_evidence_database_path,
    )
    if actual_receipt != expected_receipt:
        raise MolecularRuntimePromotionError(
            "runtime_binding_receipt_content_mismatch",
            "lineage_restart_validation",
            "Runtime binding receipt content differs from frozen lineage.",
        )
    if not artifact_root.is_dir():
        raise MolecularRuntimePromotionError(
            "runtime_artifact_root_missing",
            "lineage_restart_validation",
            "Bound runtime Artifact root is missing.",
        )
    _check_runtime_database(runtime_database_path)
