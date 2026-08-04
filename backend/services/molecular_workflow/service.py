"""Persisted, owner-scoped Stage M-B molecular model workflow."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models_db import (
    MolecularArtifactPublicationRecord,
    MolecularIdempotencyRecord,
    MolecularModelRecord,
    MolecularWorkflowRecord,
    ParsedStructureRecord,
    QuantumRegionRecord,
    StructureFileRecord,
)

from .artifact_publisher import ArtifactPublicationError, NoClobberArtifactPublisher
from .attempt_lock import (
    ConfirmationAttemptLockBusy,
    ExclusiveConfirmationAttemptLock,
    confirmation_attempt_lock_id,
)
from .canonical import parse_strict_xyz_file, rfc8785_jcs_sha256_v1
from .resource_limits import (
    STO3G_SPATIAL_AO_LIMIT,
    estimate_sto3g_spatial_ao,
)
from .runtime_gate import (
    RUNTIME_LOCK_ROOT,
    MolecularRuntimeGateError,
    assert_molecular_confirmation_lock_root_allowed,
    assert_molecular_write_runtime_allowed,
)

MOLECULAR_PROTOCOL_ID = "molecular_logical_circuit_closed_shell_cas22"
MOLECULAR_PROTOCOL_VERSION = "1.0.0-design-frozen"
PROTOCOL_DESCRIPTOR = {
    "protocol_id": MOLECULAR_PROTOCOL_ID,
    "protocol_version": MOLECULAR_PROTOCOL_VERSION,
    "stage_m_c_authorized": False,
}
ATOMIC_NUMBERS = {
    "H": 1, "He": 2, "Li": 3, "Be": 4, "B": 5,
    "C": 6, "N": 7, "O": 8, "F": 9, "Ne": 10,
}


class MolecularWorkflowError(RuntimeError):
    """HTTP-ready molecular workflow failure."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConfirmationCrashInjected(RuntimeError):
    """Test-only process-crash surrogate raised at a persisted boundary."""


@dataclass(frozen=True)
class MolecularMutationResult:
    """Status and exact response selected by idempotency handling."""

    status_code: int
    payload: dict[str, Any]


class MolecularWorkflowService:
    """Implement only the non-computational M-B input-freezing boundary."""

    def __init__(
        self,
        artifact_root: str | Path | None = None,
        *,
        lock_root: str | Path | None = None,
        confirmation_fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        configured = artifact_root or os.environ.get(
            "MOLECULAR_ARTIFACT_ROOT",
            str(Path(__file__).resolve().parents[3] / "data" / "structure_artifacts" / "molecular"),
        )
        self.artifact_root = Path(configured).resolve()
        if lock_root is not None:
            configured_lock_root = lock_root
        elif os.environ.get("M_B_ENGINEERING_TEST_MODE", "").strip().lower() == "true":
            configured_lock_root = self.artifact_root.parent / "locks"
        else:
            configured_lock_root = RUNTIME_LOCK_ROOT
        self.lock_root = Path(configured_lock_root).resolve()
        self.publisher = NoClobberArtifactPublisher(self.artifact_root)
        self._confirmation_fault_injector = confirmation_fault_injector

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    @staticmethod
    def _key_hash(idempotency_key: str) -> str:
        if not 1 <= len(idempotency_key.encode("utf-8")) <= 128:
            raise MolecularWorkflowError(
                "idempotency_key_invalid",
                "Idempotency-Key 必须为 1–128 UTF-8 bytes。",
                422,
            )
        return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_request_sha256(request: dict[str, Any]) -> str:
        try:
            return rfc8785_jcs_sha256_v1(request)[1]
        except (TypeError, ValueError) as exc:
            raise MolecularWorkflowError(
                "request_not_canonicalizable",
                str(exc),
                422,
            ) from exc

    def _assert_write_gate(self) -> None:
        try:
            assert_molecular_write_runtime_allowed(self.artifact_root)
            assert_molecular_confirmation_lock_root_allowed(
                self.lock_root,
                self.artifact_root,
            )
        except MolecularRuntimeGateError as exc:
            raise MolecularWorkflowError(
                "molecular_runtime_not_promoted",
                str(exc),
                503,
            ) from exc

    def _inject_confirmation_fault(self, boundary: str) -> None:
        if self._confirmation_fault_injector is not None:
            self._confirmation_fault_injector(boundary)

    @staticmethod
    def _estimated_sto3g_spatial_ao(model: MolecularModelRecord) -> int:
        return estimate_sto3g_spatial_ao(model.canonical_geometry_payload["atoms"])

    @staticmethod
    def _assert_sto3g_ao_admission(estimated_ao: int) -> None:
        if estimated_ao > STO3G_SPATIAL_AO_LIMIT:
            raise MolecularWorkflowError(
                "estimated_sto3g_spatial_ao_resource_limit",
                (
                    "estimated_sto3g_spatial_ao="
                    f"{estimated_ao} exceeds the frozen M-B limit "
                    f"{STO3G_SPATIAL_AO_LIMIT}."
                ),
                422,
            )

    @staticmethod
    def _owned_structure(
        session: Session,
        structure_id: str,
        owner_user_id: int,
    ) -> tuple[ParsedStructureRecord, StructureFileRecord]:
        structure = (
            session.query(ParsedStructureRecord)
            .filter(
                ParsedStructureRecord.structure_id == structure_id,
                ParsedStructureRecord.owner_user_id == owner_user_id,
            )
            .first()
        )
        if structure is None:
            raise MolecularWorkflowError(
                "structure_not_found",
                "未找到结构或无权访问。",
                404,
            )
        source_file = (
            session.query(StructureFileRecord)
            .filter(
                StructureFileRecord.file_id == structure.file_id,
                StructureFileRecord.owner_user_id == owner_user_id,
            )
            .first()
        )
        if source_file is None:
            raise MolecularWorkflowError(
                "molecular_source_inconsistent",
                "parsed_structure 的源文件或 owner 不一致。",
                409,
            )
        if source_file.input_purpose != "molecular_logical_circuit":
            raise MolecularWorkflowError(
                "molecular_input_purpose_required",
                "该结构不是 molecular_logical_circuit 输入。",
                409,
            )
        if source_file.file_type != "xyz":
            raise MolecularWorkflowError("molecular_xyz_required", "首版只接受 XYZ。", 409)
        if structure.validation_status not in {"valid", "valid_with_warnings"}:
            raise MolecularWorkflowError(
                "molecular_structure_validation_failed",
                "结构未通过原子数、坐标有限性或最小原子间距检查。",
                409,
            )
        return structure, source_file

    @staticmethod
    def _existing_idempotency(
        session: Session,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
        request_sha256: str,
    ) -> MolecularMutationResult | None:
        record = (
            session.query(MolecularIdempotencyRecord)
            .filter(
                MolecularIdempotencyRecord.owner_user_id == owner_user_id,
                MolecularIdempotencyRecord.route_scope == route_scope,
                MolecularIdempotencyRecord.idempotency_key_hash == key_hash,
            )
            .first()
        )
        if record is None:
            return None
        if record.request_sha256 != request_sha256:
            raise MolecularWorkflowError(
                "idempotency_key_reused_with_different_request",
                "同一 Idempotency-Key 已绑定不同请求。",
                409,
            )
        if not record.terminal:
            raise MolecularWorkflowError(
                "idempotency_request_in_progress",
                "同一幂等请求仍在处理，不能并发重入。",
                409,
            )
        return MolecularMutationResult(
            status_code=record.response_status_code or 500,
            payload=dict(record.response_payload or {}),
        )

    def create_model(
        self,
        *,
        structure_id: str,
        owner_user_id: int,
        idempotency_key: str,
        request: dict[str, Any],
    ) -> MolecularMutationResult:
        """Create one immutable draft from strict source bytes."""
        self._assert_write_gate()
        key_hash = self._key_hash(idempotency_key)
        request_sha256 = self._canonical_request_sha256(request)
        route_scope = f"create_molecular_model:{structure_id}"
        session = SessionLocal()
        try:
            replay = self._existing_idempotency(
                session, owner_user_id, route_scope, key_hash, request_sha256
            )
            if replay:
                return replay
            structure, source_file = self._owned_structure(
                session, structure_id, owner_user_id
            )
            strict = parse_strict_xyz_file(source_file.storage_path)
            estimated_ao = estimate_sto3g_spatial_ao(
                strict.canonical_payload["atoms"]
            )
            self._assert_sto3g_ao_admission(estimated_ao)
            if strict.source_sha256 != source_file.file_hash:
                raise MolecularWorkflowError(
                    "source_file_sha256_mismatch",
                    "源文件 bytes 与上传记录 SHA-256 不一致。",
                    409,
                )
            if request.get("expected_source_file_id") != source_file.file_id:
                raise MolecularWorkflowError(
                    "expected_source_file_id_mismatch", "客户端 source file ID 不匹配。", 409
                )
            expected_source = request.get("expected_source_file_sha256")
            expected_geometry = request.get("expected_canonical_geometry_sha256")
            if expected_source != strict.source_sha256:
                raise MolecularWorkflowError(
                    "expected_source_sha256_mismatch", "客户端源文件 SHA-256 不匹配。", 409
                )
            if expected_geometry != strict.canonical_sha256:
                raise MolecularWorkflowError(
                    "expected_geometry_sha256_mismatch", "客户端 canonical geometry SHA-256 不匹配。", 409
                )
            predecessor_id = request.get("supersedes_molecular_model_id")
            model_version = 1
            if predecessor_id:
                predecessor = (
                    session.query(MolecularModelRecord)
                    .filter(
                        MolecularModelRecord.molecular_model_id == predecessor_id,
                        MolecularModelRecord.owner_user_id == owner_user_id,
                        MolecularModelRecord.structure_id == structure_id,
                    )
                    .first()
                )
                if predecessor is None:
                    raise MolecularWorkflowError(
                        "superseded_model_not_found", "前一模型版本不存在或 lineage 不一致。", 409
                    )
                if predecessor.confirmation_status != "confirmed":
                    raise MolecularWorkflowError(
                        "superseded_model_not_confirmed", "前一模型版本必须已 confirmed。", 409
                    )
                model_version = predecessor.model_version + 1

            model = MolecularModelRecord(
                molecular_model_id=self._id("mm"),
                owner_user_id=owner_user_id,
                structure_id=structure.structure_id,
                source_file_id=source_file.file_id,
                source_input_purpose=source_file.input_purpose,
                model_version=model_version,
                supersedes_molecular_model_id=predecessor_id,
                source_format="xyz",
                source_file_sha256=strict.source_sha256,
                canonical_geometry_sha256=strict.canonical_sha256,
                canonical_geometry_payload=strict.canonical_payload,
                coordinate_unit="angstrom",
                atom_count=strict.parsed_structure["atom_count"],
                formula=strict.parsed_structure["formula"],
                element_set=strict.parsed_structure["elements"],
                dimensionality="non_periodic",
                confirmation_status="pending_confirmation",
            )
            session.add(model)
            payload = self._serialize_model(model)
            idempotency = MolecularIdempotencyRecord(
                idempotency_id=self._id("mid"),
                owner_user_id=owner_user_id,
                route_scope=route_scope,
                parent_resource_id=structure_id,
                idempotency_key_hash=key_hash,
                request_sha256=request_sha256,
                response_resource_type="molecular_model",
                response_resource_id=model.molecular_model_id,
                response_status_code=201,
                response_payload=payload,
                terminal=1,
                completed_at=datetime.utcnow(),
            )
            session.add(idempotency)
            session.commit()
            return MolecularMutationResult(201, payload)
        except IntegrityError as exc:
            session.rollback()
            raise MolecularWorkflowError(
                "molecular_model_state_conflict",
                "模型版本、直接后继或幂等键发生并发冲突。",
                409,
            ) from exc
        finally:
            session.close()

    def get_model(self, molecular_model_id: str, owner_user_id: int) -> dict[str, Any]:
        """Return one owner-scoped model."""
        session = SessionLocal()
        try:
            model = (
                session.query(MolecularModelRecord)
                .filter(
                    MolecularModelRecord.molecular_model_id == molecular_model_id,
                    MolecularModelRecord.owner_user_id == owner_user_id,
                )
                .first()
            )
            if model is None:
                raise MolecularWorkflowError("molecular_model_not_found", "未找到模型或无权访问。", 404)
            payload = self._serialize_model(model)
            workflow = (
                session.query(MolecularWorkflowRecord)
                .filter_by(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                )
                .first()
            )
            if workflow:
                payload["molecular_workflow_id"] = workflow.molecular_workflow_id
                payload["quantum_region_id"] = workflow.quantum_region_id
            return payload
        finally:
            session.close()

    def confirm_model(
        self,
        *,
        molecular_model_id: str,
        owner_user_id: int,
        idempotency_key: str,
        request: dict[str, Any],
    ) -> MolecularMutationResult:
        """Run one confirmation while holding its deterministic OS lock."""

        self._assert_write_gate()
        key_hash = self._key_hash(idempotency_key)
        request_sha256 = self._canonical_request_sha256(request)
        route_scope = f"confirm_molecular_model:{molecular_model_id}"
        attempt_lock_id = confirmation_attempt_lock_id(
            owner_user_id,
            molecular_model_id,
            key_hash,
        )
        lock = ExclusiveConfirmationAttemptLock(
            self.lock_root,
            attempt_lock_id,
        )
        try:
            with lock:
                return self._confirm_model_locked(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                    request=request,
                    key_hash=key_hash,
                    request_sha256=request_sha256,
                    route_scope=route_scope,
                )
        except ConfirmationAttemptLockBusy as exc:
            raise MolecularWorkflowError(
                "idempotency_request_in_progress",
                "同一 confirmation attempt 仍持有 OS exclusive lock。",
                409,
            ) from exc

    def _confirm_model_locked(
        self,
        *,
        molecular_model_id: str,
        owner_user_id: int,
        request: dict[str, Any],
        key_hash: str,
        request_sha256: str,
        route_scope: str,
    ) -> MolecularMutationResult:
        """Re-read durable state only after the exclusive lock is acquired."""

        session = SessionLocal()
        try:
            existing_idempotency = (
                session.query(MolecularIdempotencyRecord)
                .filter(
                    MolecularIdempotencyRecord.owner_user_id == owner_user_id,
                    MolecularIdempotencyRecord.route_scope == route_scope,
                    MolecularIdempotencyRecord.idempotency_key_hash == key_hash,
                )
                .first()
            )
            if existing_idempotency is not None:
                if existing_idempotency.request_sha256 != request_sha256:
                    raise MolecularWorkflowError(
                        "idempotency_key_reused_with_different_request",
                        "同一 Idempotency-Key 已绑定不同请求。",
                        409,
                    )
                if existing_idempotency.terminal:
                    return MolecularMutationResult(
                        status_code=existing_idempotency.response_status_code or 500,
                        payload=dict(existing_idempotency.response_payload or {}),
                    )
                session.close()
                return self._recover_confirmation_attempt(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                    route_scope=route_scope,
                    key_hash=key_hash,
                )
            model = (
                session.query(MolecularModelRecord)
                .filter(
                    MolecularModelRecord.molecular_model_id == molecular_model_id,
                    MolecularModelRecord.owner_user_id == owner_user_id,
                )
                .first()
            )
            if model is None:
                raise MolecularWorkflowError("molecular_model_not_found", "未找到模型或无权访问。", 404)
            if model.confirmation_status != "pending_confirmation":
                raise MolecularWorkflowError("molecular_model_already_confirmed", "模型已冻结，不能原地修改。", 409)
            if request.get("coordinate_unit") != "angstrom":
                raise MolecularWorkflowError("coordinate_unit_invalid", "坐标单位必须明确确认为 angstrom。", 422)
            if request.get("spin_multiplicity") != 1:
                raise MolecularWorkflowError("closed_shell_singlet_required", "首版只支持闭壳层单重态。", 422)
            total_charge = request.get("total_charge")
            if isinstance(total_charge, bool) or not isinstance(total_charge, int):
                raise MolecularWorkflowError("total_charge_invalid", "total_charge 必须为整数。", 422)
            if request.get("expected_source_file_sha256") != model.source_file_sha256:
                raise MolecularWorkflowError("source_file_sha256_mismatch", "确认的源文件 SHA-256 不匹配。", 409)
            if request.get("expected_canonical_geometry_sha256") != model.canonical_geometry_sha256:
                raise MolecularWorkflowError("canonical_geometry_sha256_mismatch", "确认的几何 SHA-256 不匹配。", 409)
            if request.get("confirmation") is not True:
                raise MolecularWorkflowError("molecular_confirmation_required", "confirmation 必须明确为 true。", 422)
            electron_count = sum(
                ATOMIC_NUMBERS[atom["element"]]
                for atom in model.canonical_geometry_payload["atoms"]
            ) - total_charge
            if electron_count <= 0:
                raise MolecularWorkflowError(
                    "electron_count_not_positive",
                    "总电子数必须为正。",
                    422,
                )
            if electron_count > 128:
                raise MolecularWorkflowError(
                    "electron_count_resource_limit",
                    "首版总电子数不得超过 128。",
                    422,
                )
            if electron_count % 2:
                raise MolecularWorkflowError(
                    "closed_shell_electron_parity_invalid",
                    "总电子数必须为正偶数。",
                    422,
                )
            estimated_ao = self._estimated_sto3g_spatial_ao(model)
            self._assert_sto3g_ao_admission(estimated_ao)

            quantum_region_id = self._id("qr")
            workflow_id = self._id("mwf")
            geometry_publication_id = self._id("pub")
            manifest_publication_id = self._id("pub")
            artifact_parent = (
                f"{owner_user_id}/{model.molecular_model_id}/{workflow_id}"
            )
            geometry_path = (
                f"{artifact_parent}/canonical_molecular_geometry.json"
            )
            manifest_path = f"{artifact_parent}/molecular_input_manifest.json"
            geometry_bytes, geometry_sha = rfc8785_jcs_sha256_v1(
                model.canonical_geometry_payload
            )
            if geometry_sha != model.canonical_geometry_sha256:
                raise MolecularWorkflowError(
                    "stored_geometry_payload_mismatch",
                    "数据库 canonical payload 与冻结 SHA-256 不一致。",
                    409,
                )
            source_file = (
                session.query(StructureFileRecord)
                .filter_by(
                    file_id=model.source_file_id,
                    owner_user_id=owner_user_id,
                )
                .one()
            )
            strict_source = parse_strict_xyz_file(source_file.storage_path)
            if (
                strict_source.source_sha256 != model.source_file_sha256
                or strict_source.canonical_sha256
                != model.canonical_geometry_sha256
            ):
                raise MolecularWorkflowError(
                    "molecular_source_changed_after_draft",
                    "draft 创建后源文件或 canonical geometry 已变化。",
                    409,
                )
            frozen_input_preimage = {
                "atom_count": model.atom_count,
                "canonical_geometry_sha256": geometry_sha,
                "coordinate_unit": "angstrom",
                "dimensionality": model.dimensionality,
                "electron_count": electron_count,
                "estimated_sto3g_spatial_ao": estimated_ao,
                "molecular_model_id": model.molecular_model_id,
                "model_version": model.model_version,
                "owner_user_id": owner_user_id,
                "protocol_eligibility_version": "molecular_input_eligibility_v1",
                "source_file_id": model.source_file_id,
                "source_file_sha256": model.source_file_sha256,
                "source_format": model.source_format,
                "spin_multiplicity": 1,
                "structure_id": model.structure_id,
                "supersedes_molecular_model_id": model.supersedes_molecular_model_id,
                "total_charge": total_charge,
            }
            _, frozen_input_sha = rfc8785_jcs_sha256_v1(frozen_input_preimage)
            protocol_sha = rfc8785_jcs_sha256_v1(PROTOCOL_DESCRIPTOR)[1]
            now = datetime.utcnow()
            created_at_utc = now.isoformat(timespec="microseconds") + "Z"
            manifest_payload = {
                **frozen_input_preimage,
                "comment_line_sha256": strict_source.comment_line_sha256,
                "frozen_input_sha256": frozen_input_sha,
                "geometry_artifact": {
                    "filename": "canonical_molecular_geometry.json",
                    "file_sha256": geometry_sha,
                    "relative_path": geometry_path,
                },
                "molecular_workflow_id": workflow_id,
                "quantum_region_id": quantum_region_id,
            }
            _, manifest_payload_sha = rfc8785_jcs_sha256_v1(manifest_payload)
            manifest_envelope = {
                "artifact_id": manifest_publication_id,
                "artifact_role": "molecular_input_manifest",
                "created_at_utc": created_at_utc,
                "molecular_model_id": model.molecular_model_id,
                "molecular_workflow_id": workflow_id,
                "owner_user_id": owner_user_id,
                "parent_payload_hashes": {
                    "canonical_geometry_sha256": geometry_sha,
                    "source_file_sha256": model.source_file_sha256,
                },
                "parent_resource_ids": {
                    "quantum_region_id": quantum_region_id,
                    "source_file_id": model.source_file_id,
                    "structure_id": model.structure_id,
                },
                "payload": manifest_payload,
                "payload_sha256": manifest_payload_sha,
                "protocol_id": MOLECULAR_PROTOCOL_ID,
                "protocol_payload_sha256": protocol_sha,
                "protocol_version": MOLECULAR_PROTOCOL_VERSION,
                "schema_id": "molecular_input_manifest",
                "schema_version": "1.0.0",
            }
            manifest_bytes, manifest_file_sha = rfc8785_jcs_sha256_v1(
                manifest_envelope
            )
            self._inject_confirmation_fault("before_confirmation_state_write")
            model.total_charge = total_charge
            model.spin_multiplicity = 1
            model.electron_count = electron_count
            model.confirmation_status = "confirmed"
            model.confirmed_by_user_id = owner_user_id
            model.confirmed_at = now
            model.frozen_input_sha256 = frozen_input_sha
            session.flush()
            self._inject_confirmation_fault("after_confirmed_model_flush")
            region_atom_indices = list(range(model.atom_count))
            region_indices_sha256 = rfc8785_jcs_sha256_v1(
                region_atom_indices
            )[1]
            region = QuantumRegionRecord(
                quantum_region_id=quantum_region_id,
                source_type="molecular_model",
                molecular_model_id=model.molecular_model_id,
                adsorption_model_id=None,
                geometry_optimization_id=None,
                owner_user_id=owner_user_id,
                region_atom_indices=region_atom_indices,
                frozen_environment_atom_indices=[],
                embedding_method="none",
                total_charge=total_charge,
                spin_multiplicity=1,
                geometry_source_type="frozen_molecular_model_artifact",
                geometry_method="strict_xyz_canonical_geometry_v1",
                geometry_artifact_path=geometry_path,
                source_geometry_artifact_path=geometry_path,
                source_geometry_sha256=geometry_sha,
                region_atom_count=model.atom_count,
                region_indices_sha256=region_indices_sha256,
                status="pending_artifact_publication",
                warnings=[],
            )
            session.add(region)
            session.flush()
            self._inject_confirmation_fault("after_quantum_region_flush")
            workflow = MolecularWorkflowRecord(
                molecular_workflow_id=workflow_id,
                owner_user_id=owner_user_id,
                molecular_model_id=model.molecular_model_id,
                quantum_region_id=quantum_region_id,
                protocol_id=MOLECULAR_PROTOCOL_ID,
                protocol_version=MOLECULAR_PROTOCOL_VERSION,
                protocol_payload_sha256=protocol_sha,
                current_stage="input_artifact_publication",
                workflow_status="publication_pending",
                qualification_status="not_assessed",
                qualification_granted=0,
                partial=0,
            )
            session.add(workflow)
            session.flush()
            self._inject_confirmation_fault("after_molecular_workflow_flush")
            journals = [
                MolecularArtifactPublicationRecord(
                    publication_id=publication_id,
                    molecular_workflow_id=workflow_id,
                    molecular_model_id=model.molecular_model_id,
                    owner_user_id=owner_user_id,
                    artifact_role=role,
                    filename=filename,
                    schema_id=schema_id,
                    schema_version="1.0.0",
                    target_relative_path=path,
                    expected_payload_sha256=payload_digest,
                    expected_file_sha256=file_digest,
                    status="pending",
                )
                for (
                    publication_id,
                    role,
                    filename,
                    schema_id,
                    path,
                    payload_digest,
                    file_digest,
                ) in (
                    (
                        geometry_publication_id,
                        "canonical_geometry",
                        "canonical_molecular_geometry.json",
                        "canonical_molecular_geometry",
                        geometry_path,
                        geometry_sha,
                        geometry_sha,
                    ),
                    (
                        manifest_publication_id,
                        "input_manifest",
                        "molecular_input_manifest.json",
                        "molecular_input_manifest",
                        manifest_path,
                        manifest_payload_sha,
                        manifest_file_sha,
                    ),
                )
            ]
            idempotency = MolecularIdempotencyRecord(
                idempotency_id=self._id("mid"),
                owner_user_id=owner_user_id,
                route_scope=route_scope,
                parent_resource_id=molecular_model_id,
                idempotency_key_hash=key_hash,
                request_sha256=request_sha256,
                response_status_code=None,
                terminal=0,
            )
            session.add_all([*journals, idempotency])
            session.flush()
            self._inject_confirmation_fault("after_confirmation_records_flush")
            self._inject_confirmation_fault(
                "before_confirmation_transaction_commit"
            )
            session.commit()
        except (IntegrityError, OperationalError) as exc:
            session.rollback()
            raise MolecularWorkflowError(
                "molecular_confirmation_state_conflict",
                "确认事务发生并发或不可变约束冲突。",
                409,
            ) from exc
        finally:
            session.close()

        self._inject_confirmation_fault("after_confirmation_transaction_commit")
        try:
            terminal = self._terminal_idempotency_result(
                owner_user_id, route_scope, key_hash
            )
            if terminal is not None:
                return terminal
            geometry_result = self.publisher.publish(geometry_path, geometry_bytes)
            self._inject_confirmation_fault("after_geometry_promote")
            terminal = self._mark_publication_published(
                workflow_id,
                "canonical_geometry",
                geometry_result.sha256,
                owner_user_id,
                route_scope,
                key_hash,
            )
            if terminal is not None:
                return terminal
            self._inject_confirmation_fault("after_geometry_journal")
            terminal = self._terminal_idempotency_result(
                owner_user_id, route_scope, key_hash
            )
            if terminal is not None:
                return terminal
            manifest_result = self.publisher.publish(manifest_path, manifest_bytes)
            self._inject_confirmation_fault("after_manifest_promote")
            terminal = self._mark_publication_published(
                workflow_id,
                "input_manifest",
                manifest_result.sha256,
                owner_user_id,
                route_scope,
                key_hash,
            )
            if terminal is not None:
                return terminal
            return self._complete_confirmation(
                molecular_model_id, owner_user_id, route_scope, key_hash, 200
            )
        except ArtifactPublicationError as exc:
            status_code = 409 if exc.code == "artifact_target_exists" else 500
            response_code = (
                "artifact_no_clobber_conflict"
                if status_code == 409
                else "molecular_confirmation_publication_failed"
            )
            return self._fail_confirmation_publication(
                molecular_model_id,
                owner_user_id,
                workflow_id,
                route_scope,
                key_hash,
                exc,
                status_code,
                response_code,
            )

    def _recover_confirmation_attempt(
        self,
        *,
        molecular_model_id: str,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
    ) -> MolecularMutationResult:
        """Derive one interrupted confirmation outcome from durable evidence only."""

        session = SessionLocal()
        try:
            idempotency = (
                session.query(MolecularIdempotencyRecord)
                .filter_by(
                    owner_user_id=owner_user_id,
                    route_scope=route_scope,
                    idempotency_key_hash=key_hash,
                )
                .one()
            )
            if idempotency.terminal:
                return MolecularMutationResult(
                    idempotency.response_status_code or 500,
                    dict(idempotency.response_payload or {}),
                )
            model = (
                session.query(MolecularModelRecord)
                .filter_by(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                )
                .one()
            )
            workflow = (
                session.query(MolecularWorkflowRecord)
                .filter_by(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                )
                .one()
            )
            publications = (
                session.query(MolecularArtifactPublicationRecord)
                .filter_by(
                    molecular_workflow_id=workflow.molecular_workflow_id,
                    owner_user_id=owner_user_id,
                )
                .all()
            )
            by_role = {record.artifact_role: record for record in publications}
            required_roles = {"canonical_geometry", "input_manifest"}
            if set(by_role) != required_roles:
                return self._terminalize_recovery_failure(
                    session=session,
                    model=model,
                    workflow=workflow,
                    idempotency=idempotency,
                    publications=publications,
                    failures={
                        "publication_journal": ArtifactPublicationError(
                            "publication_journal_incomplete",
                            "confirmation_recovery",
                            "Confirmation publication journal is incomplete.",
                        )
                    },
                )

            verified: dict[str, str] = {}
            failures: dict[str, ArtifactPublicationError] = {}
            for role in ("canonical_geometry", "input_manifest"):
                record = by_role[role]
                try:
                    result = self.publisher.reconcile_existing(
                        record.target_relative_path,
                        record.expected_file_sha256,
                    )
                    verified[role] = result.sha256
                except ArtifactPublicationError as exc:
                    failures[role] = exc

            if failures:
                return self._terminalize_recovery_failure(
                    session=session,
                    model=model,
                    workflow=workflow,
                    idempotency=idempotency,
                    publications=publications,
                    failures=failures,
                    verified=verified,
                )

            now = datetime.utcnow()
            for role, record in by_role.items():
                if record.status not in {"published", "reconciled"}:
                    record.status = "reconciled"
                    record.reconciled_at = now
                record.actual_file_sha256 = verified[role]
                record.failure_stage = None
                record.failure_code = None
                record.failure_detail = None
            model.canonical_geometry_artifact_path = by_role[
                "canonical_geometry"
            ].target_relative_path
            model.input_manifest_artifact_path = by_role[
                "input_manifest"
            ].target_relative_path
            if workflow.workflow_status not in {
                "molecular_input_frozen",
                "stopped_publication_failed",
            }:
                workflow.current_stage = "molecular_input_frozen"
                workflow.workflow_status = "molecular_input_frozen"
            if workflow.workflow_status == "stopped_publication_failed":
                return self._terminalize_existing_workflow_failure(
                    session, model, workflow, idempotency
                )
            region = session.query(QuantumRegionRecord).filter_by(
                quantum_region_id=workflow.quantum_region_id
            ).one()
            region.status = "molecular_input_frozen"
            payload = {
                "molecular_model": self._serialize_model(model),
                "workflow": self._serialize_workflow(workflow),
            }
            idempotency.response_resource_type = "molecular_workflow"
            idempotency.response_resource_id = workflow.molecular_workflow_id
            idempotency.response_status_code = 200
            idempotency.response_payload = payload
            idempotency.terminal = 1
            idempotency.completed_at = now
            session.commit()
            return MolecularMutationResult(200, payload)
        except IntegrityError as exc:
            session.rollback()
            raise MolecularWorkflowError(
                "molecular_confirmation_recovery_conflict",
                "确认恢复事务发生并发或不可变约束冲突。",
                409,
            ) from exc
        finally:
            session.close()

    def _terminalize_recovery_failure(
        self,
        *,
        session: Session,
        model: MolecularModelRecord,
        workflow: MolecularWorkflowRecord,
        idempotency: MolecularIdempotencyRecord,
        publications: list[MolecularArtifactPublicationRecord],
        failures: dict[str, ArtifactPublicationError],
        verified: dict[str, str] | None = None,
    ) -> MolecularMutationResult:
        """Persist a stable failure without reconstructing or republishing bytes."""

        verified = verified or {}
        now = datetime.utcnow()
        for record in publications:
            if record.artifact_role in verified:
                if record.status not in {"published", "reconciled"}:
                    record.status = "reconciled"
                    record.reconciled_at = now
                record.actual_file_sha256 = verified[record.artifact_role]
                continue
            error = failures.get(record.artifact_role) or failures.get(
                "publication_journal"
            )
            if error is not None:
                record.status = "failed"
                record.failure_stage = error.stage
                record.failure_code = error.code
                record.failure_detail = str(error)
        first_error = next(iter(failures.values()))
        if workflow.workflow_status not in {
            "molecular_input_frozen",
            "stopped_publication_failed",
        }:
            workflow.current_stage = "input_artifact_publication"
            workflow.workflow_status = "stopped_publication_failed"
            workflow.terminal_failure_code = first_error.code
            workflow.terminal_failure_detail = str(first_error)
            workflow.completed_at = now
        return self._terminalize_existing_workflow_failure(
            session, model, workflow, idempotency
        )

    def _terminalize_existing_workflow_failure(
        self,
        session: Session,
        model: MolecularModelRecord,
        workflow: MolecularWorkflowRecord,
        idempotency: MolecularIdempotencyRecord,
    ) -> MolecularMutationResult:
        payload = {
            "code": "molecular_confirmation_recovery_evidence_invalid",
            "message": (
                workflow.terminal_failure_detail
                or "Interrupted confirmation evidence is incomplete or inconsistent."
            ),
            "molecular_model_id": model.molecular_model_id,
            "molecular_workflow_id": workflow.molecular_workflow_id,
            "workflow_status": workflow.workflow_status,
            "confirmation_status": model.confirmation_status,
            "retry_allowed": False,
            "failure_stage": "confirmation_recovery",
            "correlation_id": f"corr_{idempotency.idempotency_id}",
        }
        idempotency.response_resource_type = "molecular_workflow"
        idempotency.response_resource_id = workflow.molecular_workflow_id
        idempotency.response_status_code = 500
        idempotency.response_payload = payload
        idempotency.terminal = 1
        idempotency.completed_at = datetime.utcnow()
        session.commit()
        return MolecularMutationResult(500, payload)

    def get_logical_workflow(
        self,
        molecular_model_id: str,
        owner_user_id: int,
    ) -> dict[str, Any]:
        """Return the persisted M-B workflow; no task-manager state is consulted."""
        session = SessionLocal()
        try:
            model = (
                session.query(MolecularModelRecord)
                .filter(
                    MolecularModelRecord.molecular_model_id == molecular_model_id,
                    MolecularModelRecord.owner_user_id == owner_user_id,
                )
                .first()
            )
            if model is None:
                raise MolecularWorkflowError("molecular_model_not_found", "未找到模型或无权访问。", 404)
            workflow = (
                session.query(MolecularWorkflowRecord)
                .filter(
                    MolecularWorkflowRecord.molecular_model_id == molecular_model_id,
                    MolecularWorkflowRecord.owner_user_id == owner_user_id,
                )
                .first()
            )
            journals = []
            if workflow:
                journals = (
                    session.query(MolecularArtifactPublicationRecord)
                    .filter(
                        MolecularArtifactPublicationRecord.molecular_workflow_id
                        == workflow.molecular_workflow_id,
                        MolecularArtifactPublicationRecord.owner_user_id == owner_user_id,
                    )
                    .order_by(MolecularArtifactPublicationRecord.created_at.asc())
                    .all()
                )
            return {
                "molecular_model": self._serialize_model(model),
                "workflow": self._serialize_workflow(workflow) if workflow else None,
                "artifact_publications": [
                    self._serialize_publication(record) for record in journals
                ],
                "electronic_structure_calculation": None,
                "electronic_structure_admission_allowed": False,
                "electronic_structure_admission_reasons": [
                    "stage_m_c_not_authorized"
                ],
                "eligible_for_distributed_compilation": False,
                "missing_reasons": (
                    []
                    if workflow
                    and workflow.workflow_status == "molecular_input_frozen"
                    else ["required_input_artifacts_not_fully_published"]
                ),
                "stage_m_c_authorized": False,
            }
        finally:
            session.close()

    def reject_electronic_structure_admission(
        self,
        molecular_model_id: str,
        owner_user_id: int,
    ) -> None:
        """Fail before creating any calculation or attempt because M-C is sealed."""
        self.get_model(molecular_model_id, owner_user_id)
        raise MolecularWorkflowError(
            "stage_m_c_not_authorized",
            "stage_m_c_authorized=false；未创建 calculation 或 attempt。",
            409,
        )

    def reconcile_publication_evidence(
        self,
        molecular_model_id: str,
        owner_user_id: int,
    ) -> dict[str, Any]:
        """Validate existing bytes and fill references without publishing bytes.

        Reconciliation deliberately preserves the workflow and idempotency
        terminal outcome. It never reconstructs a missing Artifact.
        """
        self._assert_write_gate()
        session = SessionLocal()
        try:
            model = (
                session.query(MolecularModelRecord)
                .filter_by(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                )
                .first()
            )
            if model is None:
                raise MolecularWorkflowError(
                    "molecular_model_not_found",
                    "未找到模型或无权访问。",
                    404,
                )
            workflow = (
                session.query(MolecularWorkflowRecord)
                .filter_by(
                    molecular_model_id=molecular_model_id,
                    owner_user_id=owner_user_id,
                )
                .first()
            )
            if workflow is None:
                raise MolecularWorkflowError(
                    "molecular_workflow_not_found",
                    "模型尚无 publication journal。",
                    404,
                )
            records = (
                session.query(MolecularArtifactPublicationRecord)
                .filter_by(
                    molecular_workflow_id=workflow.molecular_workflow_id,
                    owner_user_id=owner_user_id,
                )
                .order_by(MolecularArtifactPublicationRecord.created_at.asc())
                .all()
            )
            for record in records:
                if record.status == "published":
                    continue
                try:
                    result = self.publisher.reconcile_existing(
                        record.target_relative_path,
                        record.expected_file_sha256,
                    )
                except ArtifactPublicationError as exc:
                    record.status = "failed"
                    record.failure_stage = exc.stage
                    record.failure_code = exc.code
                    record.failure_detail = str(exc)
                    session.commit()
                    raise MolecularWorkflowError(
                        "publication_reconciliation_failed",
                        str(exc),
                        409,
                    ) from exc
                record.status = "reconciled"
                record.actual_file_sha256 = result.sha256
                record.reconciled_at = datetime.utcnow()
                if record.artifact_role == "canonical_geometry":
                    model.canonical_geometry_artifact_path = (
                        record.target_relative_path
                    )
                elif record.artifact_role == "input_manifest":
                    model.input_manifest_artifact_path = record.target_relative_path
            session.commit()
            return {
                "molecular_model_id": molecular_model_id,
                "molecular_workflow_id": workflow.molecular_workflow_id,
                "workflow_status_preserved": workflow.workflow_status,
                "qualification_status_preserved": workflow.qualification_status,
                "artifact_publications": [
                    self._serialize_publication(record) for record in records
                ],
            }
        finally:
            session.close()

    def _mark_publication_published(
        self,
        workflow_id: str,
        role: str,
        actual_sha256: str,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
    ) -> MolecularMutationResult | None:
        session = SessionLocal()
        try:
            terminal = self._terminal_idempotency_result_in_session(
                session,
                owner_user_id,
                route_scope,
                key_hash,
            )
            if terminal is not None:
                return terminal
            record = (
                session.query(MolecularArtifactPublicationRecord)
                .filter(
                    MolecularArtifactPublicationRecord.molecular_workflow_id == workflow_id,
                    MolecularArtifactPublicationRecord.artifact_role == role,
                )
                .one()
            )
            if record.expected_file_sha256 != actual_sha256:
                raise MolecularWorkflowError("published_sha256_mismatch", "发布后的 SHA-256 不匹配。", 500)
            record.status = "published"
            record.actual_file_sha256 = actual_sha256
            record.published_at = datetime.utcnow()
            session.commit()
            return None
        finally:
            session.close()

    def _complete_confirmation(
        self,
        model_id: str,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
        status_code: int,
    ) -> MolecularMutationResult:
        session = SessionLocal()
        try:
            terminal = self._terminal_idempotency_result_in_session(
                session,
                owner_user_id,
                route_scope,
                key_hash,
            )
            if terminal is not None:
                return terminal
            model = session.query(MolecularModelRecord).filter_by(
                molecular_model_id=model_id, owner_user_id=owner_user_id
            ).one()
            workflow = session.query(MolecularWorkflowRecord).filter_by(
                molecular_model_id=model_id, owner_user_id=owner_user_id
            ).one()
            geometry = session.query(MolecularArtifactPublicationRecord).filter_by(
                molecular_workflow_id=workflow.molecular_workflow_id,
                artifact_role="canonical_geometry",
            ).one()
            manifest = session.query(MolecularArtifactPublicationRecord).filter_by(
                molecular_workflow_id=workflow.molecular_workflow_id,
                artifact_role="input_manifest",
            ).one()
            model.canonical_geometry_artifact_path = geometry.target_relative_path
            model.input_manifest_artifact_path = manifest.target_relative_path
            workflow.current_stage = "molecular_input_frozen"
            workflow.workflow_status = "molecular_input_frozen"
            region = session.query(QuantumRegionRecord).filter_by(
                quantum_region_id=workflow.quantum_region_id
            ).one()
            region.status = "molecular_input_frozen"
            payload = {
                "molecular_model": self._serialize_model(model),
                "workflow": self._serialize_workflow(workflow),
            }
            idem = session.query(MolecularIdempotencyRecord).filter_by(
                owner_user_id=owner_user_id,
                route_scope=route_scope,
                idempotency_key_hash=key_hash,
            ).one()
            idem.response_resource_type = "molecular_workflow"
            idem.response_resource_id = workflow.molecular_workflow_id
            idem.response_status_code = status_code
            idem.response_payload = payload
            idem.terminal = 1
            idem.completed_at = datetime.utcnow()
            self._inject_confirmation_fault(
                "before_confirmation_terminal_transaction_commit"
            )
            session.commit()
            return MolecularMutationResult(status_code, payload)
        finally:
            session.close()

    def _fail_confirmation_publication(
        self,
        model_id: str,
        owner_user_id: int,
        workflow_id: str,
        route_scope: str,
        key_hash: str,
        error: ArtifactPublicationError,
        status_code: int,
        response_code: str,
    ) -> MolecularMutationResult:
        session = SessionLocal()
        try:
            terminal = self._terminal_idempotency_result_in_session(
                session,
                owner_user_id,
                route_scope,
                key_hash,
            )
            if terminal is not None:
                return terminal
            workflow = session.query(MolecularWorkflowRecord).filter_by(
                molecular_workflow_id=workflow_id, owner_user_id=owner_user_id
            ).one()
            workflow.current_stage = "input_artifact_publication"
            workflow.workflow_status = "stopped_publication_failed"
            workflow.terminal_failure_code = error.code
            workflow.terminal_failure_detail = str(error)
            pending = (
                session.query(MolecularArtifactPublicationRecord)
                .filter(
                    MolecularArtifactPublicationRecord.molecular_workflow_id == workflow_id,
                    MolecularArtifactPublicationRecord.status == "pending",
                )
                .all()
            )
            for record in pending:
                record.status = "failed"
                record.failure_stage = error.stage
                record.failure_code = error.code
                record.failure_detail = str(error)
            payload = {
                "code": response_code,
                "message": str(error),
                "molecular_model_id": model_id,
                "molecular_workflow_id": workflow_id,
                "workflow_status": workflow.workflow_status,
                "confirmation_status": "confirmed",
                "retry_allowed": False,
                "failure_stage": error.stage,
                "correlation_id": self._id("corr"),
            }
            idem = session.query(MolecularIdempotencyRecord).filter_by(
                owner_user_id=owner_user_id,
                route_scope=route_scope,
                idempotency_key_hash=key_hash,
            ).one()
            idem.response_resource_type = "molecular_workflow"
            idem.response_resource_id = workflow_id
            idem.response_status_code = status_code
            idem.response_payload = payload
            idem.terminal = 1
            idem.completed_at = datetime.utcnow()
            session.commit()
            return MolecularMutationResult(status_code, payload)
        finally:
            session.close()

    def _terminal_idempotency_result(
        self,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
    ) -> MolecularMutationResult | None:
        session = SessionLocal()
        try:
            return self._terminal_idempotency_result_in_session(
                session,
                owner_user_id,
                route_scope,
                key_hash,
            )
        finally:
            session.close()

    @staticmethod
    def _terminal_idempotency_result_in_session(
        session: Session,
        owner_user_id: int,
        route_scope: str,
        key_hash: str,
    ) -> MolecularMutationResult | None:
        idempotency = (
            session.query(MolecularIdempotencyRecord)
            .filter_by(
                owner_user_id=owner_user_id,
                route_scope=route_scope,
                idempotency_key_hash=key_hash,
            )
            .one_or_none()
        )
        if idempotency is None or not idempotency.terminal:
            return None
        return MolecularMutationResult(
            idempotency.response_status_code or 500,
            dict(idempotency.response_payload or {}),
        )

    @staticmethod
    def _serialize_model(model: MolecularModelRecord) -> dict[str, Any]:
        if (
            model.canonical_geometry_artifact_path
            and model.input_manifest_artifact_path
        ):
            input_publication_status = "published"
        elif model.confirmation_status == "confirmed":
            input_publication_status = "incomplete"
        else:
            input_publication_status = "not_started"
        return {
            "molecular_model_id": model.molecular_model_id,
            "owner_user_id": model.owner_user_id,
            "structure_id": model.structure_id,
            "source_file_id": model.source_file_id,
            "model_version": model.model_version,
            "supersedes_molecular_model_id": model.supersedes_molecular_model_id,
            "source_format": model.source_format,
            "source_file_sha256": model.source_file_sha256,
            "canonical_geometry_sha256": model.canonical_geometry_sha256,
            "canonical_geometry_artifact_path": model.canonical_geometry_artifact_path,
            "input_manifest_artifact_path": model.input_manifest_artifact_path,
            "coordinate_unit": model.coordinate_unit,
            "total_charge": model.total_charge,
            "spin_multiplicity": model.spin_multiplicity,
            "atom_count": model.atom_count,
            "estimated_sto3g_spatial_ao": estimate_sto3g_spatial_ao(
                model.canonical_geometry_payload["atoms"]
            ),
            "electron_count": model.electron_count,
            "formula": model.formula,
            "confirmation_status": model.confirmation_status,
            "confirmed_at": model.confirmed_at.isoformat() if model.confirmed_at else None,
            "frozen_input_sha256": model.frozen_input_sha256,
            "input_publication_status": input_publication_status,
            "molecular_workflow_id": None,
            "quantum_region_id": None,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        }

    @staticmethod
    def _serialize_workflow(workflow: MolecularWorkflowRecord) -> dict[str, Any]:
        return {
            "molecular_workflow_id": workflow.molecular_workflow_id,
            "molecular_model_id": workflow.molecular_model_id,
            "quantum_region_id": workflow.quantum_region_id,
            "protocol_id": workflow.protocol_id,
            "protocol_version": workflow.protocol_version,
            "current_stage": workflow.current_stage,
            "workflow_status": workflow.workflow_status,
            "qualification_status": workflow.qualification_status,
            "qualification_granted": bool(workflow.qualification_granted),
            "partial": bool(workflow.partial),
            "terminal_failure_code": workflow.terminal_failure_code,
        }

    @staticmethod
    def _serialize_publication(
        record: MolecularArtifactPublicationRecord,
    ) -> dict[str, Any]:
        return {
            "publication_id": record.publication_id,
            "artifact_role": record.artifact_role,
            "filename": record.filename,
            "target_relative_path": record.target_relative_path,
            "expected_file_sha256": record.expected_file_sha256,
            "actual_file_sha256": record.actual_file_sha256,
            "status": record.status,
            "failure_stage": record.failure_stage,
            "failure_code": record.failure_code,
        }
