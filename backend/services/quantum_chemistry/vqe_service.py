from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


class VqeSimulatorService:
    """Compile a hardware-efficient VQE ansatz and optimize real Pauli expectations on a statevector simulator."""

    def compile(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        parameter_count = qubit_count * request["ansatz_layers"]
        return {
            "parameter_count": parameter_count,
            "qasm_content": self._qasm(qubit_count, request["ansatz_layers"], np.zeros(parameter_count)),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, request["measurement_grouping"]),
        }

    def execute(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        history: list[dict] = []
        parameter_count = qubit_count * request["ansatz_layers"]

        def objective(parameters: np.ndarray) -> float:
            measurement = self._measure_pauli_terms(qubit_count, pauli_terms, parameters, request["ansatz_layers"])
            history.append(
                {
                    "iteration": len(history) + 1,
                    "parameters": parameters.tolist(),
                    "energy_hartree": measurement["energy_hartree"],
                    "energy_uncertainty_hartree": measurement["energy_uncertainty_hartree"],
                    "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
                    "shots": request["shots"],
                    "measurements": measurement["measurements"],
                }
            )
            return measurement["energy_hartree"]

        result = minimize(objective, np.zeros(parameter_count), method="COBYLA", options={"maxiter": request["max_iterations"], "tol": request["convergence_tolerance"]})
        return {
            "final_energy_hartree": float(result.fun),
            "energy_uncertainty_hartree": 0.0,
            "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
            "best_parameters": result.x.tolist(),
            "converged": bool(result.success),
            "history": history,
            "qasm_content": self._qasm(qubit_count, request["ansatz_layers"], result.x),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, "qubit_wise_commuting"),
        }

    def exact_diagonalize_pauli_hamiltonian(self, qubit_count: int, pauli_terms: list[dict]) -> dict:
        """Return the exact ground-state energy of the stored Pauli Hamiltonian.

        The implementation uses the same little-endian qubit convention as the
        statevector VQE evaluator, so a disagreement is a meaningful mapping or
        energy-offset failure rather than an indexing artefact.
        """
        if qubit_count < 1:
            raise ValueError("Pauli Hamiltonian must act on at least one qubit.")
        dimension = 1 << qubit_count
        matrix = np.zeros((dimension, dimension), dtype=complex)
        for term in pauli_terms:
            coefficient = float(term["coefficient"])
            for column_index in range(dimension):
                row_index, phase = self._apply_pauli_string_to_basis(
                    column_index,
                    term["pauli_string"],
                )
                matrix[row_index, column_index] += coefficient * phase
        if not np.allclose(matrix, matrix.conj().T, atol=1e-12):
            raise ValueError("Pauli Hamiltonian is not Hermitian.")
        eigenvalues = np.linalg.eigvalsh(matrix)
        return {
            "method": "numpy_eigvalsh_dense_exact",
            "matrix_dimension": dimension,
            "ground_state_energy_hartree": float(eigenvalues[0].real),
            "lowest_eigenvalues_hartree": [float(value.real) for value in eigenvalues[: min(8, dimension)]],
        }

    def exact_diagonalize_pauli_hamiltonian_in_uhf_sector(
        self,
        qubit_count: int,
        pauli_terms: list[dict],
        alpha_electrons: int,
        beta_electrons: int,
    ) -> dict:
        """Exactly diagonalize a Jordan-Wigner Hamiltonian in one fixed UHF particle-number sector."""
        if qubit_count < 2 or qubit_count % 2:
            raise ValueError("UHF sector diagonalization requires an even positive spin-orbital count.")
        spatial_orbitals = qubit_count // 2
        if not 0 <= alpha_electrons <= spatial_orbitals or not 0 <= beta_electrons <= spatial_orbitals:
            raise ValueError("Requested UHF electron sector exceeds the active spin-orbital capacity.")
        basis_states = [
            state
            for state in range(1 << qubit_count)
            if sum((state >> (2 * orbital)) & 1 for orbital in range(spatial_orbitals)) == alpha_electrons
            and sum((state >> (2 * orbital + 1)) & 1 for orbital in range(spatial_orbitals)) == beta_electrons
        ]
        state_positions = {state: position for position, state in enumerate(basis_states)}
        matrix = np.zeros((len(basis_states), len(basis_states)), dtype=complex)
        leakage = np.zeros((1 << qubit_count, len(basis_states)), dtype=complex)
        for term in pauli_terms:
            coefficient = float(term["coefficient"])
            for column_position, state in enumerate(basis_states):
                target_state, phase = self._apply_pauli_string_to_basis(state, term["pauli_string"])
                target_position = state_positions.get(target_state)
                if target_position is not None:
                    matrix[target_position, column_position] += coefficient * phase
                else:
                    leakage[target_state, column_position] += coefficient * phase
        if not np.allclose(leakage, 0.0, atol=1e-10):
            raise ValueError("Pauli Hamiltonian leaks from the declared UHF electron sector after term recomposition.")
        if not np.allclose(matrix, matrix.conj().T, atol=1e-12):
            raise ValueError("Sector-projected Pauli Hamiltonian is not Hermitian.")
        eigenvalues = np.linalg.eigvalsh(matrix)
        return {
            "method": "numpy_eigvalsh_exact_jordan_wigner_uhf_sector",
            "matrix_dimension": len(basis_states),
            "electron_sector": {"alpha_electrons": alpha_electrons, "beta_electrons": beta_electrons},
            "ground_state_energy_hartree": float(eigenvalues[0].real),
            "lowest_eigenvalues_hartree": [float(value.real) for value in eigenvalues[: min(8, len(eigenvalues))]],
        }

    def _measure_pauli_terms(self, qubit_count: int, terms: list[dict], parameters: np.ndarray, layers: int) -> dict:
        """Evaluate each Pauli term and explicitly recompose the energy on an exact simulator."""
        state = self._statevector(qubit_count, layers, parameters)
        energy = 0.0
        measurements: list[dict] = []
        for term in terms:
            label = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split():
                    label[qubit_count - 1 - int(token[1:])] = token[0]
            expectation = self._pauli_expectation(state, label)
            contribution = term["coefficient"] * expectation
            energy += contribution
            measurements.append(
                {
                    "pauli_string": term["pauli_string"],
                    "expectation_value": expectation,
                    "coefficient": term["coefficient"],
                    "energy_contribution_hartree": contribution,
                }
            )
        return {"energy_hartree": float(energy), "energy_uncertainty_hartree": 0.0, "measurements": measurements}

    @staticmethod
    def _measurement_plan(qubit_count: int, pauli_terms: list[dict], grouping: str) -> dict:
        """Build deterministic qubit-wise commuting measurement groups for the stored Pauli artifact."""
        groups: list[dict] = []
        for term in pauli_terms:
            basis = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split():
                    basis[int(token[1:])] = token[0]
            for group in groups:
                if all(existing == "I" or current == "I" or existing == current for existing, current in zip(group["basis_by_qubit"], basis)):
                    group["terms"].append(term["pauli_string"])
                    group["basis_by_qubit"] = [current if existing == "I" else existing for existing, current in zip(group["basis_by_qubit"], basis)]
                    break
            else:
                groups.append({"group_index": len(groups), "basis_by_qubit": basis, "terms": [term["pauli_string"]]})
        return {"grouping": grouping, "group_count": len(groups), "groups": groups}

    def _statevector(self, qubit_count: int, layers: int, parameters: np.ndarray) -> np.ndarray:
        """Apply the emitted Ry-CX ansatz directly, keeping qubit zero as the least-significant bit."""
        state = np.zeros(1 << qubit_count, dtype=complex)
        state[0] = 1.0
        for layer in range(layers):
            for qubit in range(qubit_count):
                self._apply_ry(state, qubit, float(parameters[layer * qubit_count + qubit]))
            for qubit in range(qubit_count - 1):
                self._apply_cx(state, qubit, qubit + 1)
        return state

    @staticmethod
    def _apply_ry(state: np.ndarray, qubit: int, angle: float) -> None:
        cosine = np.cos(angle / 2.0)
        sine = np.sin(angle / 2.0)
        mask = 1 << qubit
        for index in range(len(state)):
            if index & mask:
                continue
            paired_index = index | mask
            amplitude_zero = state[index]
            amplitude_one = state[paired_index]
            state[index] = cosine * amplitude_zero - sine * amplitude_one
            state[paired_index] = sine * amplitude_zero + cosine * amplitude_one

    @staticmethod
    def _apply_cx(state: np.ndarray, control: int, target: int) -> None:
        control_mask = 1 << control
        target_mask = 1 << target
        for index in range(len(state)):
            if index & control_mask and not index & target_mask:
                paired_index = index | target_mask
                state[index], state[paired_index] = state[paired_index], state[index]

    @staticmethod
    def _pauli_expectation(state: np.ndarray, label: list[str]) -> float:
        transformed = np.zeros_like(state)
        for index, amplitude in enumerate(state):
            target_index = index
            phase = 1.0 + 0.0j
            for qubit, gate in enumerate(reversed(label)):
                mask = 1 << qubit
                has_one = bool(index & mask)
                if gate == "X":
                    target_index ^= mask
                elif gate == "Y":
                    target_index ^= mask
                    phase *= -1.0j if has_one else 1.0j
                elif gate == "Z" and has_one:
                    phase *= -1.0
            transformed[target_index] += phase * amplitude
        return float(np.vdot(state, transformed).real)

    @staticmethod
    def _apply_pauli_string_to_basis(basis_index: int, pauli_string: str) -> tuple[int, complex]:
        """Apply an OpenFermion-style Pauli label to one computational basis vector."""
        target_index = basis_index
        phase = 1.0 + 0.0j
        if pauli_string == "I":
            return target_index, phase
        for token in pauli_string.split():
            operator = token[0]
            qubit = int(token[1:])
            mask = 1 << qubit
            has_one = bool(basis_index & mask)
            if operator == "X":
                target_index ^= mask
            elif operator == "Y":
                target_index ^= mask
                phase *= -1.0j if has_one else 1.0j
            elif operator == "Z" and has_one:
                phase *= -1.0
            elif operator not in {"I", "Z"}:
                raise ValueError(f"Unsupported Pauli operator: {operator}")
        return target_index, phase

    def _qasm(self, qubit_count: int, layers: int, parameters: np.ndarray) -> str:
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{qubit_count}];"]
        for layer in range(layers):
            for qubit in range(qubit_count): lines.append(f"ry({parameters[layer * qubit_count + qubit]:.12f}) q[{qubit}];")
            for qubit in range(qubit_count - 1): lines.append(f"cx q[{qubit}],q[{qubit + 1}];")
        return "\n".join(lines) + "\n"
