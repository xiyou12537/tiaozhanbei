import uuid
import json
from pathlib import Path

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.api.schemas.molecule_workflow import MolecularStudyResponse
from backend.database import SessionLocal, get_db, init_db
from backend.main import app
from backend.models_db import DeploymentStudyRecord, MoleculeWorkflowRecord, MolecularProblemRecord, User
from backend.services.molecule_workflow import MoleculeWorkflowService
from backend.services.molecule_workflow.repository import MoleculeWorkflowRepository
from backend.tests.test_molecule_workflow_e2e import DerivedElectronicStructureAdapter, QualityControlledVqeService


def test_openapi_exposes_authenticated_async_molecular_study_contract():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/molecular-studies" in paths
    operation = paths["/api/molecular-studies"]["post"]
    assert "202" in operation["responses"]
    assert "/api/molecular-studies/{study_id}" in paths
    response_schema = schema["components"]["schemas"]["MolecularStudyResponse"]
    result_schema = response_schema["properties"]["result"]
    assert {"$ref": "#/components/schemas/MolecularStudyResult"} in result_schema["anyOf"]
    assert "MolecularProblemResult" in schema["components"]["schemas"]
    assert "DeploymentEvaluationResult" in schema["components"]["schemas"]


def test_h2_three_architecture_fixture_validates_against_the_study_response_contract():
    fixture_path = Path("docs/fixtures/molecular-study-h2-three-architecture-success.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = MolecularStudyResponse.model_validate(fixture)
    assert response.status == "completed"
    assert len(response.result.deployment_evaluations) == 3
    assert response.result.deployment_evaluations[1].metrics.abstract_swap_count == 1


class CountingVqeService(QualityControlledVqeService):
    def __init__(self):
        super().__init__(converged=True)
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return super().execute(*args, **kwargs)


def test_study_reuses_one_vqe_for_three_independent_deployment_evaluations():
    init_db()
    vqe = CountingVqeService()

    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(MoleculeWorkflowRepository(db), DerivedElectronicStructureAdapter(), vqe)

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    username = f"study_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            registration = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
            headers = {"Authorization": f"Bearer {registration.json()['token']}"}
            linear = {
                "partition_count": 2, "partition_strategy": "sequential_greedy",
                "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap",
                "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}, {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}],
            }
            forced = {**linear, "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}, {"source": 2, "target": 1}]}, linear["virtual_qpus"][1]]}
            payload = {
                "molecule_name": "H2", "geometry": [{"element": "H", "coordinates_angstrom": [0, 0, 0]}, {"element": "H", "coordinates_angstrom": [0, 0, 0.735]}],
                "active_space_orbitals": 2, "vqe": {"max_iterations": 4, "shots": 64, "convergence_tolerance": 0.001},
                "architectures": [{"architecture_id": "linear-a", "partition": linear}, {"architecture_id": "forced", "partition": forced}, {"architecture_id": "linear-b", "partition": linear}],
            }
            created = client.post("/api/molecular-studies", json=payload, headers=headers)
            assert created.status_code == 202, created.text
            result = client.get(f"/api/molecular-studies/{created.json()['study_id']}", headers=headers)
            assert result.status_code == 200
            study = result.json()
            assert study["status"] == "completed"
            assert study["molecular_problem_id"] == created.json()["molecular_problem_id"]
            assert study["problem_id"] == study["molecular_problem_id"]
            assert study["completed_evaluation_count"] == 3
            assert study["total_evaluation_count"] == 3
            assert vqe.calls == 1
            evaluations = study["result"]["deployment_evaluations"]
            assert len(evaluations) == 3
            assert evaluations[1]["metrics"]["abstract_swap_count"] > 0
            assert all(item["distribution"]["actual_routed_plan_consumption"] for item in evaluations)
            assert all(item["energy_validation"]["distributed_execution_error_hartree"] < 1e-9 for item in evaluations)
            assert study["result"]["molecular_problem"]["fci_reference"]["status"] == "not_configured"
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        database = SessionLocal()
        user = database.query(User).filter_by(username=username).one_or_none()
        if user:
            database.query(DeploymentStudyRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(MolecularProblemRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(MoleculeWorkflowRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(User).filter_by(id=user.id).delete(synchronize_session=False)
            database.commit()
        database.close()


def test_non_deployable_architecture_completes_without_failing_the_study():
    init_db()

    def workflow_dependency(db: Session = Depends(get_db)):
        return MoleculeWorkflowService(
            MoleculeWorkflowRepository(db), DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=True)
        )

    app.dependency_overrides[get_molecule_workflow_service] = workflow_dependency
    username = f"study_capacity_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            registration = client.post("/api/auth/register", json={"username": username, "password": "secret123"})
            headers = {"Authorization": f"Bearer {registration.json()['token']}"}
            deployable_partition = {
                "partition_count": 2, "partition_strategy": "sequential_greedy",
                "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap",
                "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}, {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}],
            }
            insufficient_partition = {
                **deployable_partition,
                "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 1, "physical_coupling_map": []}, deployable_partition["virtual_qpus"][1]],
            }
            created = client.post("/api/molecular-studies", json={
                "molecule_name": "H2",
                "geometry": [{"element": "H", "coordinates_angstrom": [0, 0, 0]}, {"element": "H", "coordinates_angstrom": [0, 0, 0.735]}],
                "active_space_orbitals": 2,
                "vqe": {"max_iterations": 4, "shots": 64, "convergence_tolerance": 0.001},
                "architectures": [
                    {"architecture_id": "deployable-a", "partition": deployable_partition},
                    {"architecture_id": "too-small", "architecture_name": "Insufficient capacity", "partition": insufficient_partition},
                    {"architecture_id": "deployable-b", "partition": deployable_partition},
                ],
            }, headers=headers)
            assert created.status_code == 202, created.text
            study = client.get(f"/api/molecular-studies/{created.json()['study_id']}", headers=headers).json()
            rejected = next(item for item in study["result"]["deployment_evaluations"] if item["architecture_id"] == "too-small")
            assert study["status"] == "completed"
            assert rejected["status"] == "completed"
            assert rejected["is_deployable"] is False
            assert rejected["failure_reason"]["code"] == "physical_qubit_insufficient"
    finally:
        app.dependency_overrides.pop(get_molecule_workflow_service, None)
        database = SessionLocal()
        user = database.query(User).filter_by(username=username).one_or_none()
        if user:
            database.query(DeploymentStudyRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(MolecularProblemRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(MoleculeWorkflowRecord).filter_by(user_id=user.id).delete(synchronize_session=False)
            database.query(User).filter_by(id=user.id).delete(synchronize_session=False)
            database.commit()
        database.close()
