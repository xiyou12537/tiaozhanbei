from __future__ import annotations

import shutil
import subprocess
import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.api.routers.molecule_workflow import get_molecule_workflow_service
from backend.database import SessionLocal, get_db, init_db
from backend.main import app
from backend.models_db import MoleculeWorkflowRecord, User
from backend.services.electronic_structure.docker_adapter import ElectronicStructureRuntimeError
from backend.services.molecule_workflow import MoleculeWorkflowService
from backend.services.molecule_workflow.distributed_simulator import (
    DistributedSimulationError,
    LogicalVirtualQPUSimulator,
)
from backend.services.molecule_workflow.chip_routing import ChipRoutingError, route_partition_circuits
from backend.services.molecule_workflow.repository import MoleculeWorkflowRepository
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService


ATOMIC_NUMBERS = {"H": 1, "Li": 3, "O": 8}
MOLECULE_CASES = {
    "H2": [
        {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.0]},
        {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.735]},
    ],
    "LiH": [
        {"element": "Li", "coordinates_angstrom": [0.0, 0.0, 0.0]},
        {"element": "H", "coordinates_angstrom": [0.0, 0.0, 1.595]},
    ],
    "H2O": [
        {"element": "O", "coordinates_angstrom": [0.0, 0.0, 0.0]},
        {"element": "H", "coordinates_angstrom": [0.7586, 0.0, 0.5043]},
        {"element": "H", "coordinates_angstrom": [-0.7586, 0.0, 0.5043]},
    ],
}


class DerivedElectronicStructureAdapter:
    """Deterministic test double whose coefficients are derived from each request."""

    def generate_active_space_candidates(self, request: dict) -> dict:
        nuclear_charge = sum(ATOMIC_NUMBERS[site["element"]] for site in request["atomic_sites"])
        coordinate_scale = sum(
            abs(coordinate)
            for site in request["atomic_sites"]
            for coordinate in site["position_angstrom"]
        )
        hf_energy = -(nuclear_charge + 1.0 / (1.0 + coordinate_scale)) / 2.0
        return {
            "method_name": f"RHF/{request['basis_set']}",
            "hf_total_energy_hartree": hf_energy,
            "active_space_candidates": [
                {
                    "active_electrons": 2,
                    "active_orbitals": 2,
                    "orbital_indices": [0, 1],
                    "orbital_energies_hartree": [hf_energy / 2.0, abs(hf_energy) / 3.0],
                }
            ],
        }

    def build_hamiltonian(self, request: dict) -> dict:
        nuclear_charge = sum(ATOMIC_NUMBERS[site["element"]] for site in request["atomic_sites"])
        orbital_count = len(request["orbital_indices"])
        one_body = [
            [
                -(nuclear_charge / (row + 2.0)) if row == column else 0.0
                for column in range(orbital_count)
            ]
            for row in range(orbital_count)
        ]
        two_body = [
            [
                [
                    [0.0 for _ in range(orbital_count)]
                    for _ in range(orbital_count)
                ]
                for _ in range(orbital_count)
            ]
            for _ in range(orbital_count)
        ]
        return {
            "core_energy_hartree": nuclear_charge / 10.0,
            "one_body_integrals": one_body,
            "two_body_integrals": two_body,
        }

    def map_hamiltonian(self, request: dict) -> dict:
        orbital_count = len(request["one_body_integrals"])
        qubit_count = orbital_count * 2
        diagonal_sum = sum(
            request["one_body_integrals"][index][index]
            for index in range(orbital_count)
        )
        scale = abs(diagonal_sum) / (qubit_count + 1.0)
        pauli_terms = [
            {"pauli_string": "I", "coefficient": request["core_energy_hartree"] + diagonal_sum},
            *[
                {"pauli_string": f"Z{qubit}", "coefficient": scale / (qubit + 1.0)}
                for qubit in range(qubit_count)
            ],
            {"pauli_string": "X0 X1", "coefficient": scale / 2.0},
        ]
        return {
            "mapping_method": request["mapping_method"],
            "fallback_reason": None,
            "qubit_count": qubit_count,
            "qubit_count_before_tapering": qubit_count,
            "pauli_terms": pauli_terms,
            "truncation_error_estimate": 0.0,
            "z2_tapering_applied": False,
            "tapered_symmetries": [],
            "available_z2_symmetries": [],
            "tapering_reason": "测试适配器未请求裁剪。",
        }


class UnavailableElectronicStructureAdapter:
    def generate_active_space_candidates(self, _request: dict) -> dict:
        raise ElectronicStructureRuntimeError("test runtime unavailable")


class QualityControlledVqeService(VqeSimulatorService):
    """Use the real statevector path while deterministically exercising quality branches."""

    def __init__(self, converged: bool) -> None:
        self.converged = converged

    def execute(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        result = super().execute(qubit_count, pauli_terms, request)
        result["converged"] = self.converged
        result["optimizer_diagnostics"] = {
            "scipy_success": self.converged,
            "scipy_status": 0 if self.converged else 3,
            "scipy_message": "test convergence status",
            "nfev": len(result["history"]),
            "termination_reason": "trust_region_radius_lower_bound" if self.converged else "maximum_function_evaluations",
            "best_iteration": min(
                result["history"], key=lambda item: item["energy_hartree"]
            )["iteration"],
            "initial_energy_hartree": result["history"][0]["energy_hartree"],
            "final_energy_hartree": result["final_energy_hartree"],
            "recent_energy_changes_hartree": [],
        }
        return result


def _workflow_payload(molecule_name: str) -> dict:
    return {
        "molecule_name": molecule_name,
        "geometry": MOLECULE_CASES[molecule_name],
        "charge": 0,
        "spin_multiplicity": 1,
        "basis_set": "sto-3g",
        "mapping_method": "jordan_wigner",
        "active_space_orbitals": 2,
        "vqe": {
            "ansatz_layers": 1,
            "max_iterations": 8,
            "convergence_tolerance": 0.001,
            "shots": 64,
        },
        "partition": {
            "partition_count": 2,
            "topology_edges": [{"source": 0, "target": 1}],
        },
        "execution_mode": "logical_virtual_qpu",
    }


@pytest.fixture
def authenticated_client():
    init_db()
    client = TestClient(app)
    username = f"molecule_e2e_{uuid.uuid4().hex}"
    registration = client.post(
        "/api/auth/register",
        json={"username": username, "password": "secret123"},
    )
    assert registration.status_code == 200
    user_id = registration.json()["user_id"]
    headers = {"Authorization": f"Bearer {registration.json()['token']}"}
    yield client, headers, user_id

    app.dependency_overrides.pop(get_molecule_workflow_service, None)
    database = SessionLocal()
    database.query(MoleculeWorkflowRecord).filter(MoleculeWorkflowRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    database.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    database.commit()
    database.close()


def _override_service(adapter, vqe_service=None):
    def dependency(db: Session = Depends(get_db)) -> MoleculeWorkflowService:
        return MoleculeWorkflowService(
            MoleculeWorkflowRepository(db),
            electronic_structure_adapter=adapter,
            vqe_service=vqe_service,
        )

    app.dependency_overrides[get_molecule_workflow_service] = dependency


def _submit_workflow(client, headers: dict[str, str], molecule_name: str, *, converged: bool, key: str) -> dict:
    _override_service(
        DerivedElectronicStructureAdapter(),
        QualityControlledVqeService(converged=converged),
    )
    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload(molecule_name),
        headers={**headers, "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_authenticated_history_lists_persisted_workflows_with_pagination_and_filters(authenticated_client):
    client, headers, user_id = authenticated_client
    _submit_workflow(client, headers, "H2", converged=True, key="history-h2")
    _submit_workflow(client, headers, "LiH", converged=False, key="history-lih")
    _submit_workflow(client, headers, "H2O", converged=True, key="history-h2o")

    database = SessionLocal()
    assert database.query(MoleculeWorkflowRecord).filter(MoleculeWorkflowRecord.user_id == user_id).count() == 3
    database.close()

    first_page = client.get("/api/molecule-workflows?page=1&page_size=2", headers=headers)
    assert first_page.status_code == 200, first_page.text
    page = first_page.json()
    assert page["page"] == 1
    assert page["page_size"] == 2
    assert page["total"] == 3
    assert page["total_pages"] == 2
    assert len(page["items"]) == 2
    for item in page["items"]:
        assert item["workflow_id"]
        assert item["molecule_name"]
        assert item["created_at"]
        assert item["completed_at"]
        assert item["duration_ms"] is not None
        assert item["status"] == "completed"
        assert item["optimizer_name"] == "Powell"
        assert item["qubit_count"] is not None
        assert item["pauli_term_count"] is not None
        assert item["vqe_energy_hartree"] is not None
        assert item["distributed_energy_hartree"] is not None
        assert item["absolute_error_hartree"] is not None

    second_page = client.get("/api/molecule-workflows?page=2&page_size=2", headers=headers)
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert client.get("/api/molecule-workflows?page=3&page_size=2", headers=headers).json()["items"] == []

    assert client.get("/api/molecule-workflows?molecule_name=H2", headers=headers).json()["total"] == 1
    assert client.get("/api/molecule-workflows?status=completed", headers=headers).json()["total"] == 3
    assert client.get("/api/molecule-workflows?validation_status=passed", headers=headers).json()["total"] == 2
    needs_review = client.get("/api/molecule-workflows?validation_status=needs_review", headers=headers)
    assert needs_review.json()["total"] == 1
    assert needs_review.json()["items"][0]["molecule_name"] == "LiH"

    assert client.get("/api/molecule-workflows?page=0", headers=headers).status_code == 422
    assert client.get("/api/molecule-workflows?page_size=0", headers=headers).status_code == 422
    assert client.get("/api/molecule-workflows?page_size=101", headers=headers).status_code == 422


def test_workflow_history_is_authenticated_and_user_isolated(authenticated_client):
    client, headers, _ = authenticated_client
    own = _submit_workflow(client, headers, "H2", converged=True, key="history-owner")
    registration = client.post(
        "/api/auth/register",
        json={"username": f"history_other_{uuid.uuid4().hex}", "password": "secret123"},
    )
    assert registration.status_code == 200
    other_user_id = registration.json()["user_id"]
    other_headers = {"Authorization": f"Bearer {registration.json()['token']}"}
    try:
        other = _submit_workflow(client, other_headers, "LiH", converged=False, key="history-other")
        own_list = client.get("/api/molecule-workflows", headers=headers)
        other_list = client.get("/api/molecule-workflows", headers=other_headers)

        assert own_list.status_code == 200
        assert other_list.status_code == 200
        assert [item["workflow_id"] for item in own_list.json()["items"]] == [own["workflow_id"]]
        assert [item["workflow_id"] for item in other_list.json()["items"]] == [other["workflow_id"]]
        assert client.get("/api/molecule-workflows").status_code == 401
    finally:
        database = SessionLocal()
        database.query(MoleculeWorkflowRecord).filter(MoleculeWorkflowRecord.user_id == other_user_id).delete(
            synchronize_session=False
        )
        database.query(User).filter(User.id == other_user_id).delete(synchronize_session=False)
        database.commit()
        database.close()


def test_completed_nonconverged_workflow_needs_review_and_preserves_evidence(authenticated_client):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=False))
    idempotency_headers = {**headers, "Idempotency-Key": "lih-nonconverged-quality-test"}

    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload("LiH"),
        headers=idempotency_headers,
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["validation_status"] == "needs_review"
    assert result["validation_issues"] == [
        {
            "code": "vqe_not_converged",
            "stage": "vqe_optimization",
            "iteration_count": result["vqe"]["iteration_count"],
            "message": "VQE optimizer did not converge within the configured iteration budget.",
        }
    ]
    assert result["vqe"]["iteration_history"]
    assert result["distribution"]["actual_partition_consumption"] is True
    assert result["distribution"]["communication_events"]

    restored = client.get(f"/api/molecule-workflows/{result['workflow_id']}", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["validation_status"] == "needs_review"
    assert restored.json()["validation_issues"] == result["validation_issues"]

    retry = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload("LiH"),
        headers=idempotency_headers,
    )
    assert retry.status_code == 201
    assert retry.json()["workflow_id"] == result["workflow_id"]
    assert retry.json()["validation_status"] == "needs_review"


@pytest.mark.parametrize("molecule_name", ["H2", "H2O"])
def test_completed_converged_workflow_passes_scientific_validation(authenticated_client, molecule_name):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter(), QualityControlledVqeService(converged=True))

    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload(molecule_name),
        headers=headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["validation_status"] == "passed"
    assert response.json()["validation_issues"] == []


def test_vqe_result_includes_scipy_diagnostics_from_the_actual_optimizer():
    result = VqeSimulatorService().execute(
        2,
        [
            {"pauli_string": "I", "coefficient": -1.0},
            {"pauli_string": "Z0", "coefficient": 0.2},
        ],
        {
            "ansatz_layers": 1,
            "max_iterations": 3,
            "convergence_tolerance": 0.0001,
            "shots": 64,
            "initial_occupied_qubits": [0],
        },
    )

    diagnostics = result["optimizer_diagnostics"]
    assert diagnostics["scipy_success"] == result["converged"]
    assert isinstance(diagnostics["scipy_status"], int)
    assert diagnostics["scipy_message"]
    assert diagnostics["nfev"] == len(result["history"])
    assert diagnostics["best_iteration"] >= 1
    assert diagnostics["initial_energy_hartree"] == result["history"][0]["energy_hartree"]
    assert diagnostics["final_energy_hartree"] == result["final_energy_hartree"]
    assert isinstance(diagnostics["recent_energy_changes_hartree"], list)


def test_default_vqe_strategy_uses_powell_without_overriding_scipy_convergence():
    result = VqeSimulatorService().execute(
        2,
        [
            {"pauli_string": "I", "coefficient": -1.0},
            {"pauli_string": "Z0", "coefficient": 0.2},
        ],
        {
            "ansatz_layers": 1,
            "max_iterations": 80,
            "convergence_tolerance": 0.0001,
            "shots": 64,
            "initial_occupied_qubits": [0],
        },
    )

    assert result["optimizer"] == "Powell"
    assert result["optimizer_diagnostics"]["scipy_success"] is result["converged"]
    assert result["optimizer_diagnostics"]["termination_reason"] == "optimizer_reported_success"


@pytest.mark.parametrize("molecule_name", ["H2", "LiH", "H2O"])
def test_unified_api_closes_and_persists_all_three_molecule_workflows(authenticated_client, molecule_name):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter())

    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload(molecule_name),
        headers={**headers, "Idempotency-Key": f"{molecule_name}-contract-test"},
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["molecule"]["molecule_name"] == molecule_name
    assert result["molecule"]["geometry_optimization_performed"] is False
    assert [stage["stage"] for stage in result["stages"]] == [
        "input_validation",
        "electronic_structure",
        "active_space_selection",
        "fermionic_hamiltonian",
        "qubit_mapping",
        "vqe_optimization",
        "circuit_partitioning",
        "virtual_node_mapping",
        "chip_topology_routing",
        "logical_distributed_simulation",
    ]
    assert result["hamiltonian"]["pauli_terms"]
    assert result["hamiltonian"]["qubit_count"] <= 12
    assert result["vqe"]["qasm"].startswith("OPENQASM 2.0;")
    assert result["vqe"]["iteration_history"]
    assert result["distribution"]["capability_level"] == "logical_virtual_qpu"
    assert result["distribution"]["is_real_qpu"] is False
    assert result["distribution"]["actual_partition_consumption"] is True
    assert result["contract_version"] == "2.0"
    assert result["distribution"]["inter_qpu_topology"] == [{"source": 0, "target": 1}]
    assert result["distribution"]["partition_chip_routing"]
    assert result["distribution"]["intra_chip_routing_cost"]["abstract_swap_count"] == 0
    assert result["distribution"]["actual_routed_plan_consumption"] is True
    assert result["distribution"]["cross_partition_communication_count"] == len(
        result["distribution"]["communication_events"]
    )
    assert result["distribution"]["cross_partition_communication_count"] > 0
    assert result["energies"]["absolute_error_hartree"] == pytest.approx(
        abs(
            result["energies"]["distributed_simulation_energy_hartree"]
            - result["energies"]["unpartitioned_benchmark_energy_hartree"]
        ),
        abs=1e-12,
    )
    assert result["energies"]["absolute_error_hartree"] < 1e-9

    persisted = client.get(f"/api/molecule-workflows/{result['workflow_id']}", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json() == result

    idempotent_retry = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload(molecule_name),
        headers={**headers, "Idempotency-Key": f"{molecule_name}-contract-test"},
    )
    assert idempotent_retry.status_code == 201
    assert idempotent_retry.json()["workflow_id"] == result["workflow_id"]


def test_runtime_failure_is_persisted_and_returned_as_503(authenticated_client):
    client, headers, _ = authenticated_client
    _override_service(UnavailableElectronicStructureAdapter())

    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload("H2"),
        headers=headers,
    )

    assert response.status_code == 503
    error = response.json()["detail"]
    assert error["code"] == "electronic_structure_runtime_unavailable"
    assert error["stage"] == "electronic_structure"
    assert error["workflow_id"].startswith("molwf_")

    database = SessionLocal()
    record = database.query(MoleculeWorkflowRecord).filter(
        MoleculeWorkflowRecord.workflow_id == error["workflow_id"]
    ).one()
    assert record.status == "failed"
    assert record.current_stage == "electronic_structure"
    assert record.error_json["code"] == error["code"]
    database.close()


def test_idempotency_key_cannot_be_reused_for_a_different_geometry(authenticated_client):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter())
    idempotency_headers = {**headers, "Idempotency-Key": "same-key-different-request"}
    first = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload("H2"),
        headers=idempotency_headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload("LiH"),
        headers=idempotency_headers,
    )

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "idempotency_key_reused"


def test_logical_simulator_uses_mapping_for_axis_order_and_communication_provenance():
    simulator = LogicalVirtualQPUSimulator()
    qasm = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[4];
ry(0.31) q[0];
ry(-0.22) q[1];
ry(0.14) q[2];
ry(0.08) q[3];
cx q[0],q[1];
cx q[1],q[2];
cx q[2],q[3];
"""
    pauli_terms = [
        {"pauli_string": "I", "coefficient": -0.4},
        {"pauli_string": "Z0", "coefficient": 0.2},
        {"pauli_string": "X1 X2", "coefficient": -0.1},
    ]
    partitions = [[0, 1], [2, 3]]
    first_mapping = [
        {"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]},
        {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]},
    ]
    swapped_mapping = [
        {"virtual_node_id": "T1", "partition_id": "P2", "qubits": [2, 3]},
        {"virtual_node_id": "T2", "partition_id": "P1", "qubits": [0, 1]},
    ]

    first = simulator.execute(
        qasm_content=qasm,
        qubit_count=4,
        pauli_terms=pauli_terms,
        partitions=partitions,
        virtual_node_mapping=first_mapping,
    )
    swapped = simulator.execute(
        qasm_content=qasm,
        qubit_count=4,
        pauli_terms=pauli_terms,
        partitions=partitions,
        virtual_node_mapping=swapped_mapping,
    )

    assert first["axis_order_by_virtual_node"] == [0, 1, 2, 3]
    assert swapped["axis_order_by_virtual_node"] == [2, 3, 0, 1]
    assert first["energy_hartree"] == pytest.approx(swapped["energy_hartree"], abs=1e-12)
    assert first["communication_events"][0]["source_virtual_node_id"] == "T1"
    assert swapped["communication_events"][0]["source_virtual_node_id"] == "T2"
    with pytest.raises(DistributedSimulationError):
        simulator.execute(
            qasm_content=qasm,
            qubit_count=4,
            pauli_terms=pauli_terms,
            partitions=partitions,
            virtual_node_mapping=first_mapping[:1],
        )


def test_physical_chip_routing_records_direct_and_swap_evidence_separately_from_communication():
    direct = route_partition_circuits(
        qasm_content='''OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[4];\ncx q[0],q[1];\ncx q[1],q[2];\ncx q[2],q[3];\n''',
        partitions=[[0, 1], [2, 3]],
        virtual_node_mapping=[
            {"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]},
            {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]},
        ],
        chips=[
            {"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
            {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
        ],
        initial_layout_method="identity",
        routing_method="shortest_path_swap",
    )

    assert direct["intra_chip_routing_cost"]["abstract_swap_count"] == 0
    assert direct["original_two_qubit_operation_count"] == 2
    assert direct["cross_partition_gate_count"] == 1
    assert all(item["routing_status"] == "direct" for item in direct["two_qubit_routing_evidence"])

    swapped = route_partition_circuits(
        qasm_content='''OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[4];\ncx q[0],q[1];\n''',
        partitions=[[0, 1], [2, 3]],
        virtual_node_mapping=[
            {"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]},
            {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]},
        ],
        chips=[
            {"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}, {"source": 2, "target": 1}]},
            {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
        ],
        initial_layout_method="identity",
        routing_method="shortest_path_swap",
    )
    assert swapped["intra_chip_routing_cost"]["abstract_swap_count"] == 1
    evidence = swapped["two_qubit_routing_evidence"][0]
    assert evidence["routing_status"] == "routed"
    assert evidence["path"] == [0, 2, 1]
    assert evidence["swap_positions"] == [0]


def test_physical_chip_routing_rejects_insufficient_or_disconnected_chips():
    kwargs = {
        "qasm_content": 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[4];\ncx q[0],q[1];\n',
        "partitions": [[0, 1], [2, 3]],
        "virtual_node_mapping": [
            {"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]},
            {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]},
        ],
        "initial_layout_method": "identity",
        "routing_method": "shortest_path_swap",
    }
    with pytest.raises(ChipRoutingError, match="physical_qubit_insufficient"):
        route_partition_circuits(
            **kwargs,
            chips=[
                {"virtual_qpu_id": "T1", "physical_qubit_count": 1, "physical_coupling_map": []},
                {"virtual_qpu_id": "T2", "physical_qubit_count": 4, "physical_coupling_map": [{"source": 2, "target": 3}]},
            ],
        )
    with pytest.raises(ChipRoutingError, match="physical_coupling_disconnected"):
        route_partition_circuits(
            **kwargs,
            chips=[
                {"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}]},
                {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
            ],
        )


def test_swap_routed_execution_plan_is_consumed_and_preserves_logical_energy():
    qasm = '''OPENQASM 2.0;
include "qelib1.inc";
qreg q[4];
ry(0.31) q[0];
ry(-0.22) q[1];
cx q[0],q[1];
cx q[1],q[2];
cx q[2],q[3];
'''
    partitions = [[0, 1], [2, 3]]
    mapping = [
        {"virtual_node_id": "T1", "partition_id": "P1", "qubits": [0, 1]},
        {"virtual_node_id": "T2", "partition_id": "P2", "qubits": [2, 3]},
    ]
    routing = route_partition_circuits(
        qasm_content=qasm,
        partitions=partitions,
        virtual_node_mapping=mapping,
        chips=[
            {"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}, {"source": 2, "target": 1}]},
            {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
        ],
        initial_layout_method="identity",
        routing_method="shortest_path_swap",
    )
    assert routing["intra_chip_routing_cost"]["abstract_swap_count"] > 0
    assert any(item["operation"] == "swap" for item in routing["routed_execution_plan"])
    assert all(
        item["operation"] != "cx" or item["scope"] == "inter_qpu" or item["physical_edge_is_valid"]
        for item in routing["routed_execution_plan"]
    )

    simulator = LogicalVirtualQPUSimulator()
    terms = [{"pauli_string": "I", "coefficient": -0.4}, {"pauli_string": "Z0", "coefficient": 0.2}]
    original = simulator.execute(
        qasm_content=qasm,
        qubit_count=4,
        pauli_terms=terms,
        partitions=partitions,
        virtual_node_mapping=mapping,
    )
    routed = simulator.execute(
        routed_execution_plan=routing["routed_execution_plan"],
        qubit_count=4,
        pauli_terms=terms,
        partitions=partitions,
        virtual_node_mapping=mapping,
    )
    assert routed["actual_routed_plan_consumption"] is True
    assert routed["energy_hartree"] == pytest.approx(original["energy_hartree"], abs=1e-12)
    assert routed["state_norm"] == pytest.approx(1.0, abs=1e-12)

    broken_plan = [item for item in routing["routed_execution_plan"] if item["operation"] != "swap"]
    with pytest.raises(DistributedSimulationError, match=r"routed_execution_plan_(execution_index|layout)_mismatch"):
        simulator.execute(
            routed_execution_plan=broken_plan,
            qubit_count=4,
            pauli_terms=terms,
            partitions=partitions,
            virtual_node_mapping=mapping,
        )


def test_request_rejects_more_than_ten_atoms_before_execution(authenticated_client):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter())
    payload = _workflow_payload("H2")
    payload["geometry"] = [
        {"element": "H", "coordinates_angstrom": [0.0, 0.0, float(index)]}
        for index in range(11)
    ]

    response = client.post("/api/molecule-workflows", json=payload, headers=headers)

    assert response.status_code == 422


def _real_qchem_runtime_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    completed = subprocess.run(
        [docker, "image", "inspect", "liangzhi-qchem:local"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


@pytest.mark.skipif(
    not _real_qchem_runtime_available(),
    reason="requires the liangzhi-qchem:local PySCF/OpenFermion Docker image",
)
@pytest.mark.parametrize("molecule_name", ["H2", "LiH", "H2O"])
def test_real_pyscf_openfermion_api_loop_for_supported_molecules(authenticated_client, molecule_name):
    client, headers, _ = authenticated_client
    app.dependency_overrides.pop(get_molecule_workflow_service, None)

    response = client.post(
        "/api/molecule-workflows",
        json=_workflow_payload(molecule_name),
        headers=headers,
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["molecule"]["molecule_name"] == molecule_name
    assert result["hf_energy_hartree"] is not None
    assert result["hamiltonian"]["pauli_terms"]
    assert result["distribution"]["actual_partition_consumption"] is True
    assert result["energies"]["absolute_error_hartree"] < 1e-9


@pytest.mark.skipif(
    not _real_qchem_runtime_available(),
    reason="requires the liangzhi-qchem:local PySCF/OpenFermion Docker image",
)
@pytest.mark.parametrize(
    ("molecule_name", "expected_validation_status"),
    [("H2", "passed"), ("LiH", "passed"), ("H2O", "passed")],
)
def test_real_runtime_quality_statuses_at_the_default_vqe_budget(
    authenticated_client,
    molecule_name,
    expected_validation_status,
):
    client, headers, _ = authenticated_client
    app.dependency_overrides.pop(get_molecule_workflow_service, None)
    payload = _workflow_payload(molecule_name)
    payload["vqe"].update({"max_iterations": 80, "convergence_tolerance": 0.0001, "shots": 1024})
    idempotency_headers = {**headers, "Idempotency-Key": f"real-{molecule_name}-quality-status"}

    response = client.post("/api/molecule-workflows", json=payload, headers=idempotency_headers)

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["validation_status"] == expected_validation_status
    assert result["validation_issues"] == []
    assert result["vqe"]["converged"] is True

    restored = client.get(f"/api/molecule-workflows/{result['workflow_id']}", headers=headers)
    assert restored.json()["validation_status"] == expected_validation_status
    retry = client.post("/api/molecule-workflows", json=payload, headers=idempotency_headers)
    assert retry.json()["workflow_id"] == result["workflow_id"]
    assert retry.json()["validation_status"] == expected_validation_status


def test_openapi_exposes_success_and_failure_contracts():
    operation = app.openapi()["paths"]["/api/molecule-workflows"]["post"]

    assert operation["responses"]["201"]["content"]["application/json"]["example"]["distribution"][
        "capability_level"
    ] == "logical_virtual_qpu"
    assert operation["responses"]["503"]["content"]["application/json"]["example"]["detail"][
        "code"
    ] == "electronic_structure_runtime_unavailable"

    history_operation = app.openapi()["paths"]["/api/molecule-workflows"]["get"]
    assert {parameter["name"] for parameter in history_operation["parameters"]} == {
        "page",
        "page_size",
        "molecule_name",
        "status",
        "validation_status",
    }
    assert history_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MoleculeWorkflowHistoryResponse"
    )

    capabilities = app.openapi()["paths"]["/api/molecule-workflows/capabilities"]["get"]
    assert capabilities["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MoleculeWorkflowCapabilitiesResponse"
    )


def test_capabilities_are_authenticated_and_expose_virtual_only_contract(authenticated_client):
    client, headers, _ = authenticated_client
    assert client.get("/api/molecule-workflows/capabilities").status_code == 401
    response = client.get("/api/molecule-workflows/capabilities", headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["contract_version"] == "2.0"
    assert result["is_real_qpu"] is False
    assert result["execution_modes"] == ["logical_virtual_qpu"]
    assert result["routing_methods"] == ["shortest_path_swap"]


def test_default_product_mode_does_not_publish_legacy_platform_routes():
    paths = app.openapi()["paths"]
    assert "/api/platform/workflows" not in paths
    assert "/api/molecule-workflows" in paths


def test_get_remains_compatible_with_persisted_pre_v2_workflow(authenticated_client):
    client, headers, user_id = authenticated_client
    created = _submit_workflow(client, headers, "H2", converged=True, key="legacy-v1-result")
    database = SessionLocal()
    record = database.query(MoleculeWorkflowRecord).filter(
        MoleculeWorkflowRecord.workflow_id == created["workflow_id"],
        MoleculeWorkflowRecord.user_id == user_id,
    ).one()
    legacy_result = dict(record.result_json)
    legacy_result.pop("contract_version")
    legacy_distribution = dict(legacy_result["distribution"])
    for key in (
            "inter_qpu_topology",
            "partition_chip_routing",
            "two_qubit_routing_evidence",
            "routed_execution_plan",
            "original_two_qubit_operation_count",
            "routed_two_qubit_operation_count",
            "intra_chip_routing_cost",
            "actual_routed_plan_consumption",
            "final_logical_to_physical_layout",
        ):
        legacy_distribution.pop(key)
    legacy_result["distribution"] = legacy_distribution
    record.result_json = legacy_result
    database.commit()
    database.close()

    restored = client.get(f"/api/molecule-workflows/{created['workflow_id']}", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["contract_version"] is None
    assert restored.json()["distribution"]["partition_chip_routing"] is None


@pytest.mark.parametrize(
    ("virtual_qpus", "expected_code"),
    [
        (
            [
                {"virtual_qpu_id": "T1", "physical_qubit_count": 1, "physical_coupling_map": []},
                {"virtual_qpu_id": "T2", "physical_qubit_count": 4, "physical_coupling_map": [{"source": 2, "target": 3}]},
            ],
            "physical_qubit_insufficient",
        ),
        (
            [
                {"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}]},
                {"virtual_qpu_id": "T2", "physical_qubit_count": 4, "physical_coupling_map": [{"source": 2, "target": 3}]},
            ],
            "physical_coupling_disconnected",
        ),
    ],
)
def test_workflow_returns_422_when_physical_chip_cannot_route(authenticated_client, virtual_qpus, expected_code):
    client, headers, _ = authenticated_client
    _override_service(DerivedElectronicStructureAdapter())
    payload = _workflow_payload("H2")
    payload["partition"].update(
        {
            "inter_qpu_topology": [{"source": 0, "target": 1}],
            "virtual_qpus": virtual_qpus,
            "initial_layout": "identity",
            "routing_method": "shortest_path_swap",
        }
    )
    response = client.post("/api/molecule-workflows", json=payload, headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["stage"] == "chip_topology_routing"
