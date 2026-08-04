from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import SessionLocal
from backend.main import app
from backend.services.molecular_workflow.artifact_publisher import (
    ArtifactPublicationError,
    NoClobberArtifactPublisher,
)
from backend.services.molecular_workflow.resource_limits import (
    STO3G_SPATIAL_AO_LIMIT,
    estimate_sto3g_spatial_ao,
)
from backend.services.molecular_workflow.runtime_gate import MolecularRuntimeGateError
from backend.services.molecular_workflow.service import (
    ConfirmationCrashInjected,
    MolecularWorkflowError,
    MolecularWorkflowService,
)
from backend.services.molecular_workflow.canonical import (
    StrictXyzError,
    canonical_decimal_coordinate,
    parse_strict_xyz_bytes,
    rfc8785_jcs_sha256_v1,
)

XYZ_VECTOR = (
    b"3\n"
    b"water example\n"
    b"O 0.000000 -0 +0.1173000E+00\n"
    b"H +0.000000 0.7571600 -0.469200\n"
    b"H .0 -7.571600e-1 -4.69200E-1\n"
)
EXPECTED_RAW_SHA256 = "8afce8170d7283e6328010dc19fe4c180c8602c83f2a89edd16ba987058e79e7"
EXPECTED_CANONICAL_SHA256 = "0fa29a62d80b23dd91e04be0b6bdf0b1511cb908ea97e33f11da88a52a0586e2"
EXPECTED_CANONICAL_PREIMAGE = (
    b'{"atom_count":3,"atoms":[{"element":"O","index":0,'
    b'"position_angstrom":["0","0","0.1173"]},{"element":"H","index":1,'
    b'"position_angstrom":["0","0.75716","-0.4692"]},{"element":"H",'
    b'"index":2,"position_angstrom":["0","-0.75716","-0.4692"]}],'
    b'"coordinate_unit":"angstrom","dimensionality":"non_periodic",'
    b'"schema_id":"canonical_molecular_geometry","schema_version":"1.0.0"}'
)


def _register(client: TestClient, prefix: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={
            "username": f"{prefix}_{uuid4().hex[:10]}",
            "password": "test-password",
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _upload_molecular_xyz(client: TestClient, headers: dict[str, str]) -> dict:
    upload = client.post(
        "/api/platform/structure-files",
        headers={**headers, "Idempotency-Key": f"upload-{uuid4().hex}"},
        data={
            "material_name": "water",
            "input_purpose": "molecular_logical_circuit",
        },
        files={"file": ("water.xyz", XYZ_VECTOR, "chemical/x-xyz")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["input_purpose"] == "molecular_logical_circuit"
    parsed = client.post(
        f"/api/platform/structure-files/{upload.json()['file_id']}/parse",
        headers=headers,
    )
    assert parsed.status_code == 200, parsed.text
    assert parsed.json()["workflow_id"] is None
    assert parsed.json()["molecular_model_creation_eligible"] is True
    return {**upload.json(), **parsed.json()}


def _upload_xyz_bytes(
    client: TestClient,
    headers: dict[str, str],
    raw_xyz: bytes,
    *,
    label: str,
) -> dict:
    upload = client.post(
        "/api/platform/structure-files",
        headers={**headers, "Idempotency-Key": f"upload-{label}-{uuid4().hex}"},
        data={
            "material_name": label,
            "input_purpose": "molecular_logical_circuit",
        },
        files={"file": (f"{label}.xyz", raw_xyz, "chemical/x-xyz")},
    )
    assert upload.status_code == 201, upload.text
    parsed = client.post(
        f"/api/platform/structure-files/{upload.json()['file_id']}/parse",
        headers=headers,
    )
    assert parsed.status_code == 200, parsed.text
    return {**upload.json(), **parsed.json()}


def _create_water_draft(
    client: TestClient,
    owner: dict[str, str],
    *,
    label: str,
) -> tuple[dict, dict]:
    parsed = _upload_molecular_xyz(client, owner)
    body = {
        "expected_source_file_id": parsed["file_id"],
        "expected_source_file_sha256": EXPECTED_RAW_SHA256,
        "expected_canonical_geometry_sha256": EXPECTED_CANONICAL_SHA256,
    }
    response = client.post(
        f"/api/platform/structures/{parsed['structure_id']}/molecular-models",
        headers={**owner, "Idempotency-Key": f"create-{label}"},
        json=body,
    )
    assert response.status_code == 201, response.text
    return response.json(), parsed


def _confirmation_request() -> dict:
    return {
        "schema_version": "molecular_model_confirm_v1",
        "coordinate_unit": "angstrom",
        "total_charge": 0,
        "spin_multiplicity": 1,
        "expected_source_file_sha256": EXPECTED_RAW_SHA256,
        "expected_canonical_geometry_sha256": EXPECTED_CANONICAL_SHA256,
        "confirmation": True,
        "confirmation_note": None,
    }


def test_frozen_xyz_and_jcs_vector() -> None:
    result = parse_strict_xyz_bytes(XYZ_VECTOR)
    assert result.source_sha256 == EXPECTED_RAW_SHA256
    assert result.canonical_bytes == EXPECTED_CANONICAL_PREIMAGE
    assert len(result.canonical_bytes) == 365
    assert result.canonical_sha256 == EXPECTED_CANONICAL_SHA256
    assert hashlib.sha256(result.canonical_bytes).hexdigest() == EXPECTED_CANONICAL_SHA256
    assert [
        canonical_decimal_coordinate(value)
        for value in ("0", "-0", "+0.000", "1e3", "1.2300", ".5", "-.5E+1")
    ] == ["0", "0", "0", "1000", "1.23", "0.5", "-5"]
    canonical_bytes, digest = rfc8785_jcs_sha256_v1(
        {"z": 1, "a": ["\U0001f600", None, True]}
    )
    assert digest == hashlib.sha256(canonical_bytes).hexdigest()
    with pytest.raises(TypeError):
        rfc8785_jcs_sha256_v1({"float": 1.0})
    with pytest.raises(ValueError):
        rfc8785_jcs_sha256_v1({"surrogate": "\ud800"})
    with pytest.raises(StrictXyzError):
        parse_strict_xyz_bytes(XYZ_VECTOR + b"extra\n")
    with pytest.raises(StrictXyzError):
        parse_strict_xyz_bytes(XYZ_VECTOR.replace(b"O ", b"Na ", 1))


def test_node_reference_matches_python_vector(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime is unavailable.")
    vector_path = tmp_path / "water.xyz"
    vector_path.write_bytes(XYZ_VECTOR)
    script = Path(__file__).resolve().parents[2] / "scripts" / "molecular-canonical-reference.mjs"
    completed = subprocess.run(
        [node, str(script), str(vector_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    result = json.loads(completed.stdout)
    assert result["source_sha256"] == EXPECTED_RAW_SHA256
    assert result["canonical_preimage_utf8"].encode("utf-8") == EXPECTED_CANONICAL_PREIMAGE
    assert result["canonical_size_bytes"] == 365
    assert result["canonical_geometry_sha256"] == EXPECTED_CANONICAL_SHA256


def test_no_clobber_conflict_crash_and_reconciliation(tmp_path: Path) -> None:
    publisher = NoClobberArtifactPublisher(tmp_path)
    relative = "molecular/mm_fixture/canonical_molecular_geometry.json"
    payload = EXPECTED_CANONICAL_PREIMAGE
    published = publisher.publish(relative, payload)
    assert published.sha256 == EXPECTED_CANONICAL_SHA256
    with pytest.raises(ArtifactPublicationError) as conflict:
        publisher.publish(relative, b"different")
    assert conflict.value.code == "artifact_target_exists"
    reconciled = publisher.reconcile_existing(relative, EXPECTED_CANONICAL_SHA256)
    assert reconciled.sha256 == EXPECTED_CANONICAL_SHA256
    with pytest.raises(ArtifactPublicationError) as mismatch:
        publisher.reconcile_existing(relative, "0" * 64)
    assert mismatch.value.code == "artifact_sha256_mismatch"
    missing = "molecular/mm_missing/molecular_input_manifest.json"
    with pytest.raises(ArtifactPublicationError) as missing_error:
        publisher.reconcile_existing(missing, "0" * 64)
    assert missing_error.value.code == "artifact_missing"

    crash_path = "molecular/mm_crash/molecular_input_manifest.json"
    with pytest.raises(ArtifactPublicationError) as crash:
        publisher.publish(crash_path, b"{}", crash_after="temp_fsync")
    assert crash.value.code == "crash_injected"
    assert not (tmp_path / crash_path).exists()

    promoted_path = "molecular/mm_promoted/molecular_input_manifest.json"
    with pytest.raises(ArtifactPublicationError):
        publisher.publish(promoted_path, b"{}", crash_after="promote")
    promoted = tmp_path / promoted_path
    assert promoted.read_bytes() == b"{}"
    assert publisher.reconcile_existing(
        promoted_path,
        hashlib.sha256(b"{}").hexdigest(),
    ).size_bytes == 2


def test_molecular_api_owner_idempotency_immutability_and_m_c_seal() -> None:
    with TestClient(app) as client:
        owner = _register(client, "molecular_owner")
        other = _register(client, "molecular_other")
        parsed = _upload_molecular_xyz(client, owner)

        with SessionLocal() as session:
            screening_count = session.execute(
                text(
                    "SELECT count(*) FROM structure_screening_workflows "
                    "WHERE structure_id=:structure_id"
                ),
                {"structure_id": parsed["structure_id"]},
            ).scalar_one()
            assert screening_count == 0

        create_body = {
            "expected_source_file_id": parsed["file_id"],
            "expected_source_file_sha256": EXPECTED_RAW_SHA256,
            "expected_canonical_geometry_sha256": EXPECTED_CANONICAL_SHA256,
        }
        create_headers = {**owner, "Idempotency-Key": "create-water-v1"}
        created = client.post(
            f"/api/platform/structures/{parsed['structure_id']}/molecular-models",
            headers=create_headers,
            json=create_body,
        )
        assert created.status_code == 201, created.text
        model = created.json()
        assert model["confirmation_status"] == "pending_confirmation"
        assert model["canonical_geometry_artifact_path"] is None
        replay = client.post(
            f"/api/platform/structures/{parsed['structure_id']}/molecular-models",
            headers=create_headers,
            json=create_body,
        )
        assert replay.status_code == 201
        assert replay.content == created.content
        conflict = client.post(
            f"/api/platform/structures/{parsed['structure_id']}/molecular-models",
            headers=create_headers,
            json={**create_body, "expected_canonical_geometry_sha256": "0" * 64},
        )
        assert conflict.status_code == 409
        assert client.get(
            f"/api/platform/molecular-models/{model['molecular_model_id']}",
            headers=other,
        ).status_code == 404

        confirm_body = {
            "coordinate_unit": "angstrom",
            "total_charge": 0,
            "spin_multiplicity": 1,
            "expected_source_file_sha256": EXPECTED_RAW_SHA256,
            "expected_canonical_geometry_sha256": EXPECTED_CANONICAL_SHA256,
            "confirmation": True,
        }
        confirm_headers = {**owner, "Idempotency-Key": "confirm-water-v1"}
        confirmed = client.post(
            f"/api/platform/molecular-models/{model['molecular_model_id']}/confirm",
            headers=confirm_headers,
            json=confirm_body,
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["molecular_model"]["electron_count"] == 10
        assert confirmed.json()["molecular_model"]["estimated_sto3g_spatial_ao"] == 7
        geometry_path = (
            Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
            / confirmed.json()["molecular_model"][
                "canonical_geometry_artifact_path"
            ]
        )
        assert geometry_path.read_bytes() == EXPECTED_CANONICAL_PREIMAGE
        assert hashlib.sha256(geometry_path.read_bytes()).hexdigest() == (
            EXPECTED_CANONICAL_SHA256
        )
        confirm_replay = client.post(
            f"/api/platform/molecular-models/{model['molecular_model_id']}/confirm",
            headers=confirm_headers,
            json=confirm_body,
        )
        assert confirm_replay.status_code == 200
        assert confirm_replay.content == confirmed.content
        changed_charge = client.post(
            f"/api/platform/molecular-models/{model['molecular_model_id']}/confirm",
            headers={**owner, "Idempotency-Key": "confirm-water-changed"},
            json={**confirm_body, "total_charge": 2},
        )
        assert changed_charge.status_code == 409

        workflow = client.get(
            f"/api/platform/molecular-models/{model['molecular_model_id']}/logical-circuit-workflow",
            headers=owner,
        )
        assert workflow.status_code == 200
        assert workflow.json()["workflow"]["workflow_status"] == "molecular_input_frozen"
        publications = workflow.json()["artifact_publications"]
        assert [item["artifact_role"] for item in publications] == [
            "canonical_geometry",
            "input_manifest",
        ]
        assert all(item["status"] == "published" for item in publications)
        configured_lock_root = MolecularWorkflowService(
            Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
        ).lock_root
        assert configured_lock_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert configured_lock_root == (
            Path(os.environ["MOLECULAR_ARTIFACT_ROOT"]).parent / "locks"
        ).resolve()
        assert not (
            Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
            / ".confirmation-attempt-locks"
        ).exists()

        blocked = client.post(
            f"/api/platform/molecular-models/{model['molecular_model_id']}/electronic-structure-calculations",
            headers={**owner, "Idempotency-Key": "m-c-is-sealed"},
            json={},
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "stage_m_c_not_authorized"
        with SessionLocal() as session:
            assert session.execute(
                text("SELECT count(*) FROM molecular_electronic_structure_calculations")
            ).scalar_one() == 0
            assert session.execute(
                text("SELECT count(*) FROM molecular_stage_attempts")
            ).scalar_one() == 0


def test_structure_upload_idempotency_binds_input_purpose() -> None:
    with TestClient(app) as client:
        owner = _register(client, "upload_idempotency")
        headers = {**owner, "Idempotency-Key": "same-upload-key"}
        form = {
            "material_name": "water",
            "input_purpose": "molecular_logical_circuit",
        }
        first = client.post(
            "/api/platform/structure-files",
            headers=headers,
            data=form,
            files={"file": ("water.xyz", XYZ_VECTOR, "chemical/x-xyz")},
        )
        second = client.post(
            "/api/platform/structure-files",
            headers=headers,
            data=form,
            files={"file": ("water.xyz", XYZ_VECTOR, "chemical/x-xyz")},
        )
        assert first.status_code == second.status_code == 201
        assert first.content == second.content
        conflict = client.post(
            "/api/platform/structure-files",
            headers=headers,
            data={**form, "input_purpose": "legacy_screening"},
            files={"file": ("water.xyz", XYZ_VECTOR, "chemical/x-xyz")},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_default_runtime_gate_remains_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from backend.services.molecular_workflow.runtime_gate import (
        assert_molecular_write_runtime_allowed,
    )

    monkeypatch.delenv("M_B_ENGINEERING_TEST_MODE", raising=False)
    monkeypatch.delenv("M_B_RUNTIME_PROMOTION_AUTHORIZED", raising=False)
    with pytest.raises(MolecularRuntimeGateError):
        assert_molecular_write_runtime_allowed(tmp_path)


def test_confirmation_crash_reentry_derives_stable_terminal_state() -> None:
    failure_boundaries = {
        "after_confirmation_transaction_commit",
        "after_geometry_promote",
        "after_geometry_journal",
    }
    success_boundaries = {
        "after_manifest_promote",
        "before_confirmation_terminal_transaction_commit",
    }
    artifact_root = Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
    request = _confirmation_request()

    with TestClient(app) as client:
        owner = _register(client, "confirmation_recovery")
        for index, boundary in enumerate(
            sorted(failure_boundaries | success_boundaries)
        ):
            model, _ = _create_water_draft(
                client,
                owner,
                label=f"crash-{index}",
            )
            key = f"confirm-crash-{index}"

            def inject(current_boundary: str, target: str = boundary) -> None:
                if current_boundary == target:
                    raise ConfirmationCrashInjected(target)

            crashing_service = MolecularWorkflowService(
                artifact_root,
                confirmation_fault_injector=inject,
            )
            with pytest.raises(ConfirmationCrashInjected):
                crashing_service.confirm_model(
                    molecular_model_id=model["molecular_model_id"],
                    owner_user_id=model["owner_user_id"],
                    idempotency_key=key,
                    request=request,
                )

            recovery_service = MolecularWorkflowService(artifact_root)
            recovered = recovery_service.confirm_model(
                molecular_model_id=model["molecular_model_id"],
                owner_user_id=model["owner_user_id"],
                idempotency_key=key,
                request=request,
            )
            replay = recovery_service.confirm_model(
                molecular_model_id=model["molecular_model_id"],
                owner_user_id=model["owner_user_id"],
                idempotency_key=key,
                request=request,
            )
            assert replay.status_code == recovered.status_code
            assert replay.payload == recovered.payload
            assert recovered.payload.get("code") != "idempotency_request_in_progress"

            persisted = recovery_service.get_logical_workflow(
                model["molecular_model_id"],
                model["owner_user_id"],
            )
            if boundary in failure_boundaries:
                assert recovered.status_code == 500
                assert recovered.payload["code"] == (
                    "molecular_confirmation_recovery_evidence_invalid"
                )
                assert persisted["workflow"]["workflow_status"] == (
                    "stopped_publication_failed"
                )
                assert persisted["workflow"]["qualification_granted"] is False
                missing_publications = [
                    publication
                    for publication in persisted["artifact_publications"]
                    if not (
                        artifact_root
                        / publication["target_relative_path"]
                    ).is_file()
                ]
                assert missing_publications
                with pytest.raises(
                    MolecularWorkflowError,
                    match="Missing Artifact",
                ):
                    recovery_service.reconcile_publication_evidence(
                        model["molecular_model_id"],
                        model["owner_user_id"],
                    )
            else:
                assert recovered.status_code == 200
                assert persisted["workflow"]["workflow_status"] == (
                    "molecular_input_frozen"
                )
                assert all(
                    publication["status"] in {"published", "reconciled"}
                    for publication in persisted["artifact_publications"]
                )
                reconciliation = (
                    recovery_service.reconcile_publication_evidence(
                        model["molecular_model_id"],
                        model["owner_user_id"],
                    )
                )
                assert reconciliation["workflow_status_preserved"] == (
                    "molecular_input_frozen"
                )
                assert reconciliation["qualification_status_preserved"] == (
                    "not_assessed"
                )

            after_reconciliation = recovery_service.get_logical_workflow(
                model["molecular_model_id"],
                model["owner_user_id"],
            )
            assert (
                after_reconciliation["workflow"]["workflow_status"]
                == persisted["workflow"]["workflow_status"]
            )
            assert (
                after_reconciliation["workflow"]["qualification_status"]
                == persisted["workflow"]["qualification_status"]
            )

            with SessionLocal() as session:
                terminal = session.execute(
                    text(
                        "SELECT terminal FROM molecular_idempotency_records "
                        "WHERE route_scope=:scope"
                    ),
                    {
                        "scope": (
                            "confirm_molecular_model:"
                            f"{model['molecular_model_id']}"
                        )
                    },
                ).scalar_one()
                assert terminal == 1


def test_confirmation_recovery_rejects_existing_sha_mismatch() -> None:
    artifact_root = Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
    request = _confirmation_request()
    with TestClient(app) as client:
        owner = _register(client, "confirmation_sha_mismatch")
        model, _ = _create_water_draft(
            client,
            owner,
            label="sha-mismatch",
        )

        def inject(boundary: str) -> None:
            if boundary == "after_geometry_promote":
                raise ConfirmationCrashInjected(boundary)

        crashing_service = MolecularWorkflowService(
            artifact_root,
            confirmation_fault_injector=inject,
        )
        with pytest.raises(ConfirmationCrashInjected):
            crashing_service.confirm_model(
                molecular_model_id=model["molecular_model_id"],
                owner_user_id=model["owner_user_id"],
                idempotency_key="confirm-sha-mismatch",
                request=request,
            )
        workflow = crashing_service.get_logical_workflow(
            model["molecular_model_id"],
            model["owner_user_id"],
        )
        geometry = next(
            publication
            for publication in workflow["artifact_publications"]
            if publication["artifact_role"] == "canonical_geometry"
        )
        geometry_target = artifact_root / geometry["target_relative_path"]
        geometry_target.write_bytes(b"tampered fixture bytes")

        recovered = MolecularWorkflowService(artifact_root).confirm_model(
            molecular_model_id=model["molecular_model_id"],
            owner_user_id=model["owner_user_id"],
            idempotency_key="confirm-sha-mismatch",
            request=request,
        )
        assert recovered.status_code == 500
        assert recovered.payload["code"] == (
            "molecular_confirmation_recovery_evidence_invalid"
        )
        terminal = MolecularWorkflowService(artifact_root).get_logical_workflow(
            model["molecular_model_id"],
            model["owner_user_id"],
        )
        assert terminal["workflow"]["workflow_status"] == (
            "stopped_publication_failed"
        )
        assert next(
            publication
            for publication in terminal["artifact_publications"]
            if publication["artifact_role"] == "canonical_geometry"
        )["failure_code"] == "artifact_sha256_mismatch"


def test_sto3g_spatial_ao_64_allowed_and_65_rejected() -> None:
    elements_64 = ["Ne"] * 12 + ["H"] * 4
    elements_65 = ["Ne"] * 13
    assert estimate_sto3g_spatial_ao(
        {"element": element} for element in elements_64
    ) == STO3G_SPATIAL_AO_LIMIT
    assert estimate_sto3g_spatial_ao(
        {"element": element} for element in elements_65
    ) == STO3G_SPATIAL_AO_LIMIT + 1

    def xyz(elements: list[str]) -> bytes:
        lines = [str(len(elements)), "deterministic AO boundary fixture"]
        lines.extend(
            f"{element} {index}.0 0 0"
            for index, element in enumerate(elements)
        )
        return ("\n".join(lines) + "\n").encode("ascii")

    with TestClient(app) as client:
        owner = _register(client, "ao_boundary")
        allowed_raw = xyz(elements_64)
        allowed_strict = parse_strict_xyz_bytes(allowed_raw)
        allowed = _upload_xyz_bytes(
            client,
            owner,
            allowed_raw,
            label="ao-64",
        )
        allowed_create = client.post(
            f"/api/platform/structures/{allowed['structure_id']}/molecular-models",
            headers={**owner, "Idempotency-Key": "create-ao-64"},
            json={
                "expected_source_file_id": allowed["file_id"],
                "expected_source_file_sha256": allowed_strict.source_sha256,
                "expected_canonical_geometry_sha256": (
                    allowed_strict.canonical_sha256
                ),
            },
        )
        assert allowed_create.status_code == 201, allowed_create.text
        assert allowed_create.json()["estimated_sto3g_spatial_ao"] == 64
        allowed_confirm = client.post(
            (
                "/api/platform/molecular-models/"
                f"{allowed_create.json()['molecular_model_id']}/confirm"
            ),
            headers={**owner, "Idempotency-Key": "confirm-ao-64"},
            json={
                "coordinate_unit": "angstrom",
                "total_charge": 0,
                "spin_multiplicity": 1,
                "expected_source_file_sha256": allowed_strict.source_sha256,
                "expected_canonical_geometry_sha256": (
                    allowed_strict.canonical_sha256
                ),
                "confirmation": True,
            },
        )
        assert allowed_confirm.status_code == 200, allowed_confirm.text
        assert (
            allowed_confirm.json()["molecular_model"][
                "estimated_sto3g_spatial_ao"
            ]
            == 64
        )

        rejected_raw = xyz(elements_65)
        rejected_strict = parse_strict_xyz_bytes(rejected_raw)
        rejected = _upload_xyz_bytes(
            client,
            owner,
            rejected_raw,
            label="ao-65",
        )
        rejected_create = client.post(
            f"/api/platform/structures/{rejected['structure_id']}/molecular-models",
            headers={**owner, "Idempotency-Key": "create-ao-65"},
            json={
                "expected_source_file_id": rejected["file_id"],
                "expected_source_file_sha256": rejected_strict.source_sha256,
                "expected_canonical_geometry_sha256": (
                    rejected_strict.canonical_sha256
                ),
            },
        )
        assert rejected_create.status_code == 422
        assert rejected_create.json()["detail"]["code"] == (
            "estimated_sto3g_spatial_ao_resource_limit"
        )


def test_molecular_model_creation_preserves_minimum_distance_gate() -> None:
    raw_xyz = b"2\ntoo close\nH 0 0 0\nH 0.1 0 0\n"
    strict = parse_strict_xyz_bytes(raw_xyz)
    with TestClient(app) as client:
        owner = _register(client, "minimum_distance")
        parsed = _upload_xyz_bytes(
            client,
            owner,
            raw_xyz,
            label="too-close",
        )
        assert parsed["validation_status"] == "validation_failed"
        response = client.post(
            f"/api/platform/structures/{parsed['structure_id']}/molecular-models",
            headers={**owner, "Idempotency-Key": "create-too-close"},
            json={
                "expected_source_file_id": parsed["file_id"],
                "expected_source_file_sha256": strict.source_sha256,
                "expected_canonical_geometry_sha256": strict.canonical_sha256,
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == (
            "molecular_structure_validation_failed"
        )


def test_engineering_gate_requires_active_pytest_and_system_temp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from backend.services.molecular_workflow.runtime_gate import (
        assert_molecular_confirmation_lock_root_allowed,
        assert_molecular_write_runtime_allowed,
    )

    assert_molecular_write_runtime_allowed(tmp_path)
    assert_molecular_confirmation_lock_root_allowed(
        tmp_path / "locks",
        tmp_path / "artifacts",
    )
    with pytest.raises(MolecularRuntimeGateError, match="outside the Artifact"):
        assert_molecular_confirmation_lock_root_allowed(
            tmp_path / "artifacts" / "locks",
            tmp_path / "artifacts",
        )
    current_test = os.environ.pop("PYTEST_CURRENT_TEST")
    try:
        with pytest.raises(MolecularRuntimeGateError, match="active pytest"):
            assert_molecular_write_runtime_allowed(tmp_path)
    finally:
        os.environ["PYTEST_CURRENT_TEST"] = current_test
    with pytest.raises(MolecularRuntimeGateError, match="system temporary"):
        assert_molecular_write_runtime_allowed(Path.cwd() / "isolated-artifacts")
    monkeypatch.setenv("M_B_ENGINEERING_TEST_MODE", "false")
    monkeypatch.setenv("M_B_RUNTIME_PROMOTION_AUTHORIZED", "true")
    monkeypatch.setenv(
        "EXPECTED_RUNTIME_MIGRATION_ID",
        "20260730_01_molecular_m_b",
    )
    with pytest.raises(MolecularRuntimeGateError, match="database path"):
        assert_molecular_write_runtime_allowed(tmp_path)


def _confirmation_state_snapshot(molecular_model_id: str) -> tuple:
    with SessionLocal() as session:
        workflow = session.execute(
            text(
                "SELECT molecular_workflow_id,workflow_status,"
                "qualification_status,qualification_granted,"
                "terminal_failure_code FROM molecular_workflows "
                "WHERE molecular_model_id=:model_id"
            ),
            {"model_id": molecular_model_id},
        ).fetchall()
        journals = session.execute(
            text(
                "SELECT artifact_role,status,actual_file_sha256,"
                "failure_code FROM molecular_artifact_publication_journal "
                "WHERE molecular_model_id=:model_id ORDER BY artifact_role"
            ),
            {"model_id": molecular_model_id},
        ).fetchall()
        idempotency = session.execute(
            text(
                "SELECT idempotency_key_hash,terminal,response_status_code,"
                "response_payload FROM molecular_idempotency_records "
                "WHERE parent_resource_id=:model_id "
                "ORDER BY idempotency_key_hash"
            ),
            {"model_id": molecular_model_id},
        ).fetchall()
    return tuple(workflow), tuple(journals), tuple(idempotency)


def test_confirmation_same_key_concurrency_is_rejected_without_mutation() -> None:
    artifact_root = Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
    request = _confirmation_request()
    paused = threading.Event()
    release = threading.Event()

    def inject(boundary: str) -> None:
        if boundary == "after_confirmation_transaction_commit":
            paused.set()
            if not release.wait(timeout=10):
                raise RuntimeError("confirmation concurrency fixture timed out")

    with TestClient(app) as client:
        owner = _register(client, "same_key_concurrency")
        model, _ = _create_water_draft(
            client,
            owner,
            label="same-key-concurrency",
        )
        key = "confirm-same-key-concurrency"
        original_service = MolecularWorkflowService(
            artifact_root,
            confirmation_fault_injector=inject,
        )
        concurrent_service = MolecularWorkflowService(artifact_root)
        with ThreadPoolExecutor(max_workers=2) as executor:
            original = executor.submit(
                original_service.confirm_model,
                molecular_model_id=model["molecular_model_id"],
                owner_user_id=model["owner_user_id"],
                idempotency_key=key,
                request=request,
            )
            assert paused.wait(timeout=10)
            before = _confirmation_state_snapshot(model["molecular_model_id"])
            with pytest.raises(MolecularWorkflowError) as concurrent:
                concurrent_service.confirm_model(
                    molecular_model_id=model["molecular_model_id"],
                    owner_user_id=model["owner_user_id"],
                    idempotency_key=key,
                    request=request,
                )
            assert concurrent.value.status_code == 409
            assert concurrent.value.code == "idempotency_request_in_progress"
            after = _confirmation_state_snapshot(model["molecular_model_id"])
            assert after == before
            release.set()
            assert original.result(timeout=10).status_code == 200


def test_confirmation_crash_releases_lock_and_terminal_blocks_stale_writer() -> None:
    artifact_root = Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
    request = _confirmation_request()

    def inject(boundary: str) -> None:
        if boundary == "after_manifest_promote":
            raise ConfirmationCrashInjected(boundary)

    with TestClient(app) as client:
        owner = _register(client, "crash_lock_release")
        model, _ = _create_water_draft(
            client,
            owner,
            label="crash-lock-release",
        )
        key = "confirm-crash-lock-release"
        crashing_service = MolecularWorkflowService(
            artifact_root,
            confirmation_fault_injector=inject,
        )
        with pytest.raises(ConfirmationCrashInjected):
            crashing_service.confirm_model(
                molecular_model_id=model["molecular_model_id"],
                owner_user_id=model["owner_user_id"],
                idempotency_key=key,
                request=request,
            )

        recovery_service = MolecularWorkflowService(artifact_root)
        recovered = recovery_service.confirm_model(
            molecular_model_id=model["molecular_model_id"],
            owner_user_id=model["owner_user_id"],
            idempotency_key=key,
            request=request,
        )
        assert recovered.status_code == 200
        workflow = recovery_service.get_logical_workflow(
            model["molecular_model_id"],
            model["owner_user_id"],
        )["workflow"]
        before = _confirmation_state_snapshot(model["molecular_model_id"])
        stale_result = recovery_service._fail_confirmation_publication(
            model["molecular_model_id"],
            model["owner_user_id"],
            workflow["molecular_workflow_id"],
            f"confirm_molecular_model:{model['molecular_model_id']}",
            recovery_service._key_hash(key),
            ArtifactPublicationError(
                "stale_writer_fixture",
                "stale_writer",
                "A stale path must not overwrite a terminal response.",
            ),
            500,
            "stale_writer_fixture",
        )
        assert stale_result.status_code == 200
        assert stale_result.payload == recovered.payload
        assert _confirmation_state_snapshot(model["molecular_model_id"]) == before


def test_confirmation_different_keys_allow_only_one_transaction_success() -> None:
    artifact_root = Path(os.environ["MOLECULAR_ARTIFACT_ROOT"])
    request = _confirmation_request()
    state_write_barrier = threading.Barrier(2, timeout=10)

    def inject(boundary: str) -> None:
        if boundary == "before_confirmation_state_write":
            state_write_barrier.wait()

    with TestClient(app) as client:
        owner = _register(client, "different_key_concurrency")
        model, _ = _create_water_draft(
            client,
            owner,
            label="different-key-concurrency",
        )

        def run(key: str) -> tuple[str, int, str | None]:
            service = MolecularWorkflowService(
                artifact_root,
                confirmation_fault_injector=inject,
            )
            try:
                result = service.confirm_model(
                    molecular_model_id=model["molecular_model_id"],
                    owner_user_id=model["owner_user_id"],
                    idempotency_key=key,
                    request=request,
                )
                return "result", result.status_code, None
            except MolecularWorkflowError as exc:
                return "error", exc.status_code, exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(run, "confirm-different-key-a"),
                executor.submit(run, "confirm-different-key-b"),
            ]
            outcomes = [future.result(timeout=15) for future in futures]
        assert sorted(status for _, status, _ in outcomes) == [200, 409]
        assert sum(kind == "result" for kind, _, _ in outcomes) == 1
        with SessionLocal() as session:
            assert session.execute(
                text(
                    "SELECT count(*) FROM molecular_workflows "
                    "WHERE molecular_model_id=:model_id"
                ),
                {"model_id": model["molecular_model_id"]},
            ).scalar_one() == 1
