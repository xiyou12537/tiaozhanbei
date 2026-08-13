import json
import uuid
from pathlib import Path

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.api.schemas.molecule_workflow import MolecularBondScanRequest, MolecularBondScanResponse
from backend.database import SessionLocal, get_db, init_db
from backend.main import app
from backend.models_db import MolecularBondScanPointRecord, MolecularBondScanRecord, MolecularProblemRecord, MoleculeWorkflowRecord, User
from backend.services.molecule_workflow import MoleculeWorkflowService
from backend.services.molecule_workflow.bond_scan_service import MolecularBondScanService
from backend.services.molecule_workflow.repository import MoleculeWorkflowRepository
from backend.services.molecule_workflow.service import MoleculeWorkflowError
from backend.tests.test_molecule_workflow_e2e import DerivedElectronicStructureAdapter, QualityControlledVqeService


def _architectures():
    linear = {
        "partition_count": 2, "partition_strategy": "sequential_greedy",
        "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap",
        "virtual_qpus": [
            {"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
            {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
        ],
    }
    forced = {**linear, "virtual_qpus": [
        {"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}, {"source": 2, "target": 1}]},
        linear["virtual_qpus"][1],
    ]}
    return [
        {"architecture_id": "linear-a", "partition": linear},
        {"architecture_id": "forced-swap", "partition": forced},
        {"architecture_id": "linear-b", "partition": linear},
    ]


def _capacity_limited_architecture():
    return {
        "architecture_id": "capacity-limited",
        "partition": {
            "partition_count": 2,
            "partition_strategy": "sequential_greedy",
            "inter_qpu_topology": [{"source": 0, "target": 1}],
            "initial_layout": "identity",
            "routing_method": "shortest_path_swap",
            "virtual_qpus": [
                {"virtual_qpu_id": "T1", "physical_qubit_count": 1, "physical_coupling_map": []},
                {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
            ],
        },
    }


def _payload(point_count=3):
    return {
        "molecule_type": "LiH",
        "scan": {"start_distance_angstrom": 1.0, "end_distance_angstrom": 1.2, "point_count": point_count},
        "chemistry": {"active_space_orbitals": 2, "vqe": {"max_iterations": 4, "shots": 64, "convergence_tolerance": 0.001}},
        "deployment_architectures": _architectures(),
    }


class FciElectronicStructureAdapter(DerivedElectronicStructureAdapter):
    def calculate_classical_reference(self, request):
        distance = request["atomic_sites"][1]["position_angstrom"][2]
        return {"status": "completed", "method": "PySCF-CASCI-FCI", "energy_hartree": -7.9 + distance / 100.0}


class OnePointFailureAdapter(DerivedElectronicStructureAdapter):
    def generate_active_space_candidates(self, request):
        if request["atomic_sites"][1]["position_angstrom"][2] == 1.1:
            raise MoleculeWorkflowError("electronic_structure_runtime_unavailable", "Simulated point runtime failure.", "electronic_structure", 503)
        return super().generate_active_space_candidates(request)


def test_bond_scan_openapi_uses_typed_result_and_authenticated_routes():
    schema = app.openapi()
    assert "/api/molecular-bond-scans" in schema["paths"]
    result = schema["components"]["schemas"]["MolecularBondScanResponse"]["properties"]["result"]
    assert {"$ref": "#/components/schemas/MolecularBondScanResult"} in result["anyOf"]
    assert "MolecularBondScanPoint" in schema["components"]["schemas"]
    assert "202" in schema["paths"]["/api/molecular-bond-scans"]["post"]["responses"]
    assert "MolecularBondScanErrorResponse" in schema["components"]["schemas"]
    assert schema["paths"]["/api/molecular-bond-scans/{scan_id}"]["get"]["responses"]["503"]
    with TestClient(app) as client:
        assert client.get("/api/molecular-bond-scans/capabilities").status_code == 401


def test_bond_scan_success_fixture_matches_the_typed_response_contract():
    fixture = Path("docs/fixtures/molecular-bond-scan-lih-success.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    result = MolecularBondScanResponse.model_validate(payload)
    assert result.result is not None
    assert result.result.deployment_result[1].metrics.abstract_swap_count > 0


def test_lih_scan_persists_deterministic_points_and_reuses_minimum_for_deployment():
    init_db()
    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(MoleculeWorkflowRepository(db), DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=True))

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    username = f"bond_scan_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
            headers = {"Authorization": f"Bearer {registered.json()['token']}", "Idempotency-Key": "scan-key-1"}
            accepted = client.post("/api/molecular-bond-scans", json=_payload(), headers=headers)
            assert accepted.status_code == 202, accepted.text
            scan_id = accepted.json()["scan_id"]
            result = client.get(f"/api/molecular-bond-scans/{scan_id}", headers=headers)
            assert result.status_code == 200
            payload = result.json()
            assert payload["status"] == "completed"
            assert [point["distance_angstrom"] for point in payload["result"]["points"]] == [1.0, 1.1, 1.2]
            assert payload["completed_point_count"] == 3
            assert all(point["molecular_problem_id"] for point in payload["result"]["points"])
            db = SessionLocal()
            assert (
                db.query(MolecularProblemRecord)
                .filter_by(user_id=registered.json()["user_id"])
                .filter(MolecularProblemRecord.problem_id.like("mprob_scan_%"))
                .count()
                == 3
            )
            db.close()
            assert payload["result"]["vqe_discrete_minimum"] is not None
            # The mock has optimizer convergence but no configured FCI
            # reference, so deployment is intentionally engineering-only.
            assert payload["result"]["scientific_vqe_discrete_minimum"] is None
            assert payload["result"]["engineering_only_deployment"] is True
            assert payload["result"]["deployment_reference_point_index"] is not None
            assert len(payload["result"]["deployment_result"]) == 3
            assert payload["result"]["deployment_result"][1]["metrics"]["abstract_swap_count"] > 0
            retry = client.post("/api/molecular-bond-scans", json=_payload(), headers=headers)
            assert retry.status_code == 202
            assert retry.json()["scan_id"] == scan_id
            assert client.get(f"/api/molecular-bond-scans/{scan_id}", headers=headers).json()["result"]["engineering_only_deployment"] is True
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        db = SessionLocal()
        user = db.query(User).filter_by(username=username).one_or_none()
        if user:
            scan_ids = [scan_id for (scan_id,) in db.query(MolecularBondScanRecord.scan_id).filter_by(user_id=user.id).all()]
            if scan_ids:
                db.query(MolecularBondScanPointRecord).filter(MolecularBondScanPointRecord.scan_id.in_(scan_ids)).delete(synchronize_session=False)
            db.query(MolecularBondScanRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            db.query(MolecularProblemRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            db.query(MoleculeWorkflowRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            db.query(User).filter_by(id=user.id).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_bond_scan_preserves_fci_and_needs_review_points_without_deployment():
    init_db()
    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(MoleculeWorkflowRepository(db), FciElectronicStructureAdapter(), QualityControlledVqeService(converged=False))

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    username = f"bond_scan_quality_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
            headers = {"Authorization": f"Bearer {registered.json()['token']}", "Idempotency-Key": "scan-quality"}
            accepted = client.post("/api/molecular-bond-scans", json=_payload(), headers=headers)
            assert accepted.status_code == 202
            scan = client.get(f"/api/molecular-bond-scans/{accepted.json()['scan_id']}", headers=headers).json()
            assert scan["status"] == "completed"
            assert scan["needs_review_point_count"] == 3
            assert scan["result"]["vqe_discrete_minimum"] is None
            assert scan["result"]["deployment_result"] is None
            assert any("No VQE point passed validation" in issue for issue in scan["result"]["summary"]["issues"])
            for point in scan["result"]["points"]:
                assert point["status"] == "completed"
                assert point["validation_status"] == "needs_review"
                assert point["fci_reference"]["status"] == "available"
                assert point["fci_reference"]["energy_hartree"] is not None
                assert point["vqe_fci_scientific_error_hartree"] is not None
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        _delete_test_user(username)


def test_bond_scan_keeps_partial_success_and_isolates_users():
    init_db()
    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(MoleculeWorkflowRepository(db), OnePointFailureAdapter(), QualityControlledVqeService(converged=True))

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    owner_name, other_name = f"bond_scan_owner_{uuid.uuid4().hex}", f"bond_scan_other_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            owner = client.post("/api/auth/register", json={"username": owner_name, "password": "secret123"}).json()
            headers = {"Authorization": f"Bearer {owner['token']}", "Idempotency-Key": "scan-partial"}
            accepted = client.post("/api/molecular-bond-scans", json=_payload(), headers=headers)
            assert accepted.status_code == 202
            scan_id = accepted.json()["scan_id"]
            result = client.get(f"/api/molecular-bond-scans/{scan_id}", headers=headers).json()
            assert result["status"] == "completed"
            assert result["completed_point_count"] == 2
            assert result["failed_point_count"] == 1
            failed = result["result"]["points"][1]
            assert failed["status"] == "failed"
            assert failed["error"]["point_index"] == 1
            other = client.post("/api/auth/register", json={"username": other_name, "password": "secret123"}).json()
            other_headers = {"Authorization": f"Bearer {other['token']}"}
            assert client.get(f"/api/molecular-bond-scans/{scan_id}", headers=other_headers).status_code == 404
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        _delete_test_user(owner_name)
        _delete_test_user(other_name)


def test_bond_scan_rejects_invalid_requests_and_idempotency_conflicts():
    username = f"scanval_{uuid.uuid4().hex[:20]}"
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"username": username, "password": "secret123"}).json()
            headers = {"Authorization": f"Bearer {registered['token']}", "Idempotency-Key": "scan-conflict"}
            invalid = _payload()
            invalid["scan"]["end_distance_angstrom"] = invalid["scan"]["start_distance_angstrom"]
            assert client.post("/api/molecular-bond-scans", json=invalid, headers=headers).status_code == 422
            app.dependency_overrides[get_molecule_workflow_service] = lambda db=Depends(get_db): MoleculeWorkflowService(MoleculeWorkflowRepository(db), DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=True))
            first = client.post("/api/molecular-bond-scans", json=_payload(), headers=headers)
            assert first.status_code == 202
            different = _payload(point_count=4)
            conflict = client.post("/api/molecular-bond-scans", json=different, headers=headers)
            assert conflict.status_code == 409
            assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        _delete_test_user(username)


def test_bond_scan_partial_result_and_non_deployable_architecture_are_retained():
    init_db()
    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(MoleculeWorkflowRepository(db), DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=True))

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    username = f"scanpartial_{uuid.uuid4().hex[:18]}"
    try:
        with TestClient(app) as client:
            registered = client.post("/api/auth/register", json={"username": username, "password": "secret123"}).json()
            headers = {"Authorization": f"Bearer {registered['token']}"}
            # Submit directly so this test can observe the durable partial shape before execution resumes.
            db = SessionLocal()
            service = MolecularBondScanService(db, workflow_dependency(db))
            request = _payload()
            request["deployment_architectures"][2] = _capacity_limited_architecture()
            request = MolecularBondScanRequest.model_validate(request).model_dump(mode="json")
            accepted = service.submit(request, registered["user_id"], "scan-partial-manual")
            partial = service.get(accepted["scan_id"], registered["user_id"])
            assert partial["status"] == "queued"
            assert partial["result"]["engineering_only_deployment"] is None
            assert len(partial["result"]["points"]) == 3
            assert partial["result"]["points"][0]["hf_energy_hartree"] is None
            service.execute(accepted["scan_id"], registered["user_id"])
            completed = client.get(f"/api/molecular-bond-scans/{accepted['scan_id']}", headers=headers).json()
            assert completed["status"] == "completed", completed.get("error")
            outcomes = {item["architecture_id"]: item for item in completed["result"]["deployment_result"]}
            assert outcomes["linear-a"]["is_deployable"] is True
            assert outcomes["capacity-limited"]["status"] == "completed"
            assert outcomes["capacity-limited"]["is_deployable"] is False
            assert outcomes["capacity-limited"]["failure_reason"]["code"] == "physical_qubit_insufficient"
            db.close()
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        _delete_test_user(username)


def _delete_test_user(username):
    db = SessionLocal()
    user = db.query(User).filter_by(username=username).one_or_none()
    if user:
        scan_ids = [scan_id for (scan_id,) in db.query(MolecularBondScanRecord.scan_id).filter_by(user_id=user.id).all()]
        if scan_ids:
            db.query(MolecularBondScanPointRecord).filter(MolecularBondScanPointRecord.scan_id.in_(scan_ids)).delete(synchronize_session=False)
        db.query(MolecularBondScanRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.query(MolecularProblemRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.query(MoleculeWorkflowRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.query(User).filter_by(id=user.id).delete(synchronize_session=False)
        db.commit()
    db.close()
