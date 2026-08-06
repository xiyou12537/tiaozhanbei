from __future__ import annotations

import json
from types import SimpleNamespace

from backend.services.structure_modeling import service as structure_modeling_module
from backend.services.structure_modeling.service import StructureModelingService
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService
from backend.services.runtime_status import load_circuit_runtime


def test_vqe_simulator_generates_parseable_qasm_and_iteration_history():
    service = VqeSimulatorService()
    terms = [{"pauli_string": "I", "coefficient": -0.5}, {"pauli_string": "Z0", "coefficient": 0.5}]
    request = {"ansatz_layers": 1, "measurement_grouping": "qubit_wise_commuting", "max_iterations": 20, "convergence_tolerance": 0.001, "shots": 64}
    compiled = service.compile(1, terms, request)
    load_qasm_string, _, _ = load_circuit_runtime()
    assert load_qasm_string(compiled["qasm_content"])[0] == 1
    execution = service.execute(1, terms, request)
    assert execution["history"]
    assert execution["final_energy_hartree"] < -0.9
    assert execution["energy_uncertainty_method"] == "statevector_exact_no_shot_sampling"
    assert execution["history"][0]["measurements"]
    assert compiled["measurement_plan"]["groups"][0]["terms"]


def test_vqe_execution_persists_measurements_provenance_and_partition_evidence(tmp_path, monkeypatch):
    class Repository:
        def __init__(self):
            self.execution_values = None

        def get_vqe_circuit(self, *_):
            return SimpleNamespace(vqe_circuit_id="vqe_test", qubit_hamiltonian_id="qh_test", ansatz_layers=1, max_iterations=12, convergence_tolerance=0.001, shots=64)

        def get_qubit_hamiltonian(self, *_):
            return SimpleNamespace(qubit_hamiltonian_id="qh_test", fermionic_hamiltonian_id="fh_test", qubit_count=2, pauli_artifact_path=str(pauli_path))

        @staticmethod
        def get_fermionic_hamiltonian(*_):
            return SimpleNamespace(active_space_id="aspace_test", method_name="RHF/STO-3G")

        @staticmethod
        def get_active_space(*_):
            return SimpleNamespace(quantum_region_id="region_test")

        @staticmethod
        def get_quantum_region(*_):
            return SimpleNamespace(adsorption_model_id="adsorption_test", geometry_source_type="geometry_only")

        @staticmethod
        def get_adsorption_model(*_):
            return SimpleNamespace(active_site_id="site_test", adsorption_model_id="adsorption_test")

        @staticmethod
        def get_active_site(*_):
            return SimpleNamespace(active_site_id="site_test", structure_id="structure_test")

        def create_vqe_execution(self, values):
            self.execution_values = values
            return SimpleNamespace(**values)

    pauli_path = tmp_path / "pauli.json"
    pauli_path.write_text(json.dumps({"pauli_terms": [{"pauli_string": "I", "coefficient": -0.5}, {"pauli_string": "Z0", "coefficient": 0.5}]}), encoding="utf-8")
    repository = Repository()
    monkeypatch.setattr(structure_modeling_module, "STRUCTURE_ARTIFACT_ROOT", tmp_path)
    service = StructureModelingService(repository=repository)

    response = service.execute_vqe_circuit("vqe_test", owner_user_id=1)

    artifact = json.loads((tmp_path / f"{response['iteration_artifact_id']}.json").read_text(encoding="utf-8"))
    assert repository.execution_values["execution_backend_type"] == "simulator"
    assert response["energy_uncertainty_method"] == "statevector_exact_no_shot_sampling"
    assert response["history"][0]["iteration"] == 1
    assert response["history"][0]["shots"] == 64
    assert response["distributed_execution"]["partition_method"] == "existing_partitioning_pipeline"
    assert response["distributed_execution"]["capability_level"] == "partition_planning_validation"
    assert response["distributed_execution"]["actual_distributed_execution"] is False
    assert response["distributed_execution"]["measurement_recomposition_performed"] is False
    assert artifact["history"][0]["measurements"]
    assert artifact["distributed_execution"]["partition_method"] == "existing_partitioning_pipeline"
    assert artifact["provenance"]["input_structure_id"] == "structure_test"
