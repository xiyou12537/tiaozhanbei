import numpy as np

from backend.services.molecule_workflow.distributed_simulator import LogicalVirtualQPUSimulator
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService


def _cas22_terms():
    return [
        {"pauli_string": "I", "coefficient": -7.5},
        {"pauli_string": "Z0", "coefficient": 0.15}, {"pauli_string": "Z1", "coefficient": 0.15},
        {"pauli_string": "Z2", "coefficient": -0.02}, {"pauli_string": "Z3", "coefficient": -0.02},
        {"pauli_string": "X0 X2", "coefficient": 0.02}, {"pauli_string": "Y0 Y2", "coefficient": 0.02},
    ]


def test_zero_parameter_ucc_restores_hf_and_preserves_particle_number():
    simulator = VqeSimulatorService()
    state = simulator._statevector(4, 1, np.zeros(3), [0, 1])
    assert np.isclose(abs(state[3]) ** 2, 1.0)
    assert np.isclose(simulator.particle_number_expectation(state), 2.0)
    assert np.isclose(simulator.particle_number_variance(state), 0.0)


def test_ucc_double_excitation_preserves_particle_number_and_respects_variational_bound():
    simulator = VqeSimulatorService()
    terms = _cas22_terms()
    varied = simulator._measure_pauli_terms(4, terms, np.asarray([0.31, -0.17, 0.41]), 1, [0, 1])
    assert np.isclose(varied["particle_number_expectation"], 2.0)
    assert np.isclose(varied["particle_number_variance"], 0.0)
    assert varied["energy_hartree"] >= simulator.exact_ground_energy(4, terms) - 1e-12


def test_pauli_exact_diagonalization_matches_known_two_level_ground_state():
    simulator = VqeSimulatorService()
    terms = [{"pauli_string": "I", "coefficient": 1.0}, {"pauli_string": "Z0", "coefficient": 0.3}]
    assert np.isclose(simulator.exact_ground_energy(1, terms), 0.7)


def test_qasm_contains_only_supported_compiled_gates_and_round_trips_to_distributed_simulator():
    simulator = VqeSimulatorService()
    qasm = simulator._qasm(4, 1, np.asarray([0.1, -0.2, 0.3]), [0, 1])
    assert all(line.split(" ")[0].split("(")[0] in {"OPENQASM", "include", "qreg", "x", "h", "s", "sdg", "rz", "cx"} for line in qasm.splitlines())
    distributed = LogicalVirtualQPUSimulator().execute(
        qasm_content=qasm, qubit_count=4, pauli_terms=_cas22_terms(), partitions=[[0, 1], [2, 3]],
        virtual_node_mapping=[{"partition_id": "P1", "virtual_node_id": "T1", "qubits": [0, 1]}, {"partition_id": "P2", "virtual_node_id": "T2", "qubits": [2, 3]}],
    )
    unpartitioned = simulator._measure_pauli_terms(4, _cas22_terms(), np.asarray([0.1, -0.2, 0.3]), 1, [0, 1])
    assert abs(distributed["energy_hartree"] - unpartitioned["energy_hartree"]) < 1e-10
    assert abs(distributed["state_norm"] - 1.0) < 1e-10
