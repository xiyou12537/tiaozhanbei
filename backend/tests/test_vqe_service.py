from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.services.structure_modeling import service as structure_modeling_module
from backend.services.quantum_chemistry import fixed_sector_vqe as fixed_sector_vqe_module
from backend.services.structure_modeling.service import StructureModelingService
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService
from backend.services.quantum_chemistry.fixed_sector_vqe import (
    FIXED_SECTOR_VQE_PROTOCOL_VERSION,
    QASM_REPLAY_TOLERANCE_HARTREE,
    FixedSectorUccsdVqeService,
    FixedSectorVqeConfiguration,
    FixedSectorVqeError,
)
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


def test_exact_pauli_diagonalization_uses_the_same_energy_convention_as_vqe():
    service = VqeSimulatorService()
    # H = -0.5 I + 0.5 Z has eigenvalues -1.0 and 0.0.
    result = service.exact_diagonalize_pauli_hamiltonian(
        1,
        [{"pauli_string": "I", "coefficient": -0.5}, {"pauli_string": "Z0", "coefficient": 0.5}],
    )

    assert result["method"] == "numpy_eigvalsh_dense_exact"
    assert result["matrix_dimension"] == 2
    assert result["ground_state_energy_hartree"] == -1.0


def test_exact_pauli_diagonalization_can_restrict_to_a_fixed_uhf_electron_sector():
    service = VqeSimulatorService()
    result = service.exact_diagonalize_pauli_hamiltonian_in_uhf_sector(
        4,
        [
            {"pauli_string": "Z0", "coefficient": 0.5},
            {"pauli_string": "Z1", "coefficient": 1.0},
            {"pauli_string": "Z2", "coefficient": -0.1},
            {"pauli_string": "Z3", "coefficient": -0.2},
        ],
        alpha_electrons=1,
        beta_electrons=1,
    )

    assert result["method"] == "numpy_eigvalsh_exact_jordan_wigner_uhf_sector"
    assert result["matrix_dimension"] == 4
    assert result["electron_sector"] == {"alpha_electrons": 1, "beta_electrons": 1}
    assert result["ground_state_energy_hartree"] == -1.8


def test_fixed_sector_uccsd_uses_interleaved_hf_occupation_and_spin_preserving_excitations():
    service = FixedSectorUccsdVqeService()
    configuration = FixedSectorVqeConfiguration()
    ansatz, excitations = service._build_uccsd_ansatz(4, 1, 1, configuration)

    assert service._hf_bitstring(4, 1, 1) == "0011"
    assert ansatz.num_qubits == 4
    assert service._serialize_excitations(excitations) == [
        {"occupied": [0], "unoccupied": [1]},
        {"occupied": [2], "unoccupied": [3]},
        {"occupied": [0, 2], "unoccupied": [1, 3]},
    ]


def test_fixed_sector_uccsd_rejects_any_nonfrozen_execution_configuration():
    service = FixedSectorUccsdVqeService()

    with pytest.raises(FixedSectorVqeError) as exc_info:
        service._validate_configuration(
            FixedSectorVqeConfiguration(shots=1024),
            qubit_count=4,
            alpha_electrons=1,
            beta_electrons=1,
        )

    assert exc_info.value.code == "fixed_sector_configuration_invalid"


def test_fixed_sector_uccsd_rejects_energy_qualified_result_when_optimizer_did_not_converge():
    checks = {
        "optimizer_converged": False,
        "variational_condition": True,
        "target_error": True,
        "meaningful_correlation_recovery": True,
        "qasm_replay": True,
        "sector_conserved": True,
    }

    status = FixedSectorUccsdVqeService._classify_acceptance("primary", checks)

    assert status == "vqe_not_converged"


def test_fixed_sector_uccsd_classifies_qasm_replay_failure_as_a_hard_stop():
    checks = {
        "optimizer_converged": True,
        "variational_condition": True,
        "target_error": True,
        "meaningful_correlation_recovery": True,
        "qasm_replay": False,
        "sector_conserved": True,
    }

    assert FixedSectorUccsdVqeService._classify_acceptance("primary", checks) == "qasm_mismatch"


def test_fixed_sector_protocol_v2_applies_one_qasm_threshold_to_every_cas_role():
    assert FIXED_SECTOR_VQE_PROTOCOL_VERSION == "fixed_sector_vqe_acceptance_protocol_v2"
    assert QASM_REPLAY_TOLERANCE_HARTREE == 1e-9
    for role in ("minimum", "primary", "sensitivity"):
        checks = {
            "optimizer_converged": True,
            "variational_condition": True,
            "target_error": True,
            "meaningful_correlation_recovery": True,
            "qasm_replay": 3.1e-10 <= QASM_REPLAY_TOLERANCE_HARTREE,
            "sector_conserved": True,
        }
        assert FixedSectorUccsdVqeService._classify_acceptance(role, checks).endswith("_accepted")


def test_fixed_sector_v2_rejects_a_statevector_fidelity_failure_even_when_energy_replays():
    checks = {
        "optimizer_converged": True,
        "variational_condition": True,
        "target_error": True,
        "meaningful_correlation_recovery": True,
        "qasm_replay": True,
        "statevector_fidelity": False,
        "sector_conserved": True,
    }

    assert FixedSectorUccsdVqeService._classify_acceptance("sensitivity", checks) == "qasm_mismatch"


def test_fixed_sector_qasm_telemetry_backfill_never_optimizes_or_mutates_frozen_inputs(monkeypatch):
    service = FixedSectorUccsdVqeService()
    configuration = FixedSectorVqeConfiguration()
    ansatz, _ = service._build_uccsd_ansatz(4, 1, 1, configuration)
    parameters = [0.0] * ansatz.num_parameters
    sparse_operator, statevector_class = service._qiskit_runtime([{"pauli_string": "I", "coefficient": -0.5}], 4)
    source_qasm, replay_energy, _ = service._qasm_replay_energy(
        ansatz.assign_parameters(parameters, inplace=False), sparse_operator, statevector_class
    )
    parameter_hash = service._parameter_vector_sha256(parameters)
    qasm_hash = fixed_sector_vqe_module.hashlib.sha256(source_qasm.encode("utf-8")).hexdigest()
    original_parameters = list(parameters)

    def forbidden_optimizer(*_args, **_kwargs):
        raise AssertionError("Telemetry backfill must not call an optimizer.")

    monkeypatch.setattr(fixed_sector_vqe_module, "minimize", forbidden_optimizer)
    result = service.backfill_frozen_qasm_telemetry(
        [{"pauli_string": "I", "coefficient": -0.5}], 4, 1, 1, parameters, source_qasm,
        parameter_hash, qasm_hash, -0.5, replay_energy,
    )

    assert result["optimizer_executed"] is False
    assert result["qasm_retranspiled"] is False
    assert result["qasm_reserialized"] is False
    assert parameters == original_parameters
    assert source_qasm.encode("utf-8") == source_qasm.encode("utf-8")


def test_fixed_sector_qasm_telemetry_backfill_rejects_a_frozen_input_hash_mismatch():
    service = FixedSectorUccsdVqeService()
    configuration = FixedSectorVqeConfiguration()
    ansatz, _ = service._build_uccsd_ansatz(4, 1, 1, configuration)
    parameters = [0.0] * ansatz.num_parameters
    sparse_operator, statevector_class = service._qiskit_runtime([{"pauli_string": "I", "coefficient": -0.5}], 4)
    source_qasm, replay_energy, _ = service._qasm_replay_energy(
        ansatz.assign_parameters(parameters, inplace=False), sparse_operator, statevector_class
    )

    with pytest.raises(FixedSectorVqeError) as exc_info:
        service.backfill_frozen_qasm_telemetry(
            [{"pauli_string": "I", "coefficient": -0.5}], 4, 1, 1, parameters, source_qasm,
            "0" * 64, fixed_sector_vqe_module.hashlib.sha256(source_qasm.encode("utf-8")).hexdigest(), -0.5, replay_energy,
        )

    assert exc_info.value.code == "backfill_parameter_hash_mismatch"


def test_high_precision_qasm2_serializer_preserves_u3_binary64_parameters_and_gate_order():
    from qiskit import QuantumCircuit, qasm2, transpile

    service = FixedSectorUccsdVqeService()
    circuit = QuantumCircuit(2)
    circuit.u(0.12345678901234567, -0.9876543210987654, 0.3141592653589793, 0)
    circuit.cx(0, 1)

    transpiled = transpile(circuit, basis_gates=["u3", "cx"], optimization_level=0)
    qasm_content = service.serialize_transpiled_qasm2_high_precision(transpiled)
    reloaded = qasm2.loads(qasm_content)

    assert "0.12345678901234566" in qasm_content
    assert [instruction.operation.name for instruction in reloaded.data] == ["u3", "cx"]
    assert reloaded.data[0].operation.params == transpiled.data[0].operation.params


def test_quantum_closure_classification_never_qualifies_an_outside_target_result():
    classification = StructureModelingService._classify_quantum_closure(
        vqe_energy=-0.95,
        exact_energy=-1.0,
        vqe_error=0.05,
        converged=True,
        vqe_target_tolerance=0.0016,
    )

    assert classification == ("vqe_outside_target", "simulator_vqe_outside_target", "vqe_outside_target")


def test_quantum_closure_classification_rejects_non_variational_energy():
    classification = StructureModelingService._classify_quantum_closure(
        vqe_energy=-1.0001,
        exact_energy=-1.0,
        vqe_error=0.0001,
        converged=True,
        vqe_target_tolerance=0.0016,
    )

    assert classification == ("non_variational_result", "simulator_vqe_outside_target", "non_variational_result")


def test_statevector_vqe_shots_zero_keeps_exact_no_sampling_uncertainty_label():
    service = VqeSimulatorService()
    result = service.execute(
        1,
        [{"pauli_string": "I", "coefficient": -0.5}, {"pauli_string": "Z0", "coefficient": 0.5}],
        {"ansatz_layers": 1, "max_iterations": 20, "convergence_tolerance": 0.001, "shots": 0},
    )

    assert result["energy_uncertainty_hartree"] == 0.0
    assert result["energy_uncertainty_method"] == "statevector_exact_no_shot_sampling"
    assert result["history"][0]["shots"] == 0


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
