from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


class VqeSimulatorService:
    """Compile a hardware-efficient VQE ansatz and optimize real Pauli expectations on a statevector simulator."""

    def compile(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        parameter_count = qubit_count * request["ansatz_layers"]
        return {
            "parameter_count": parameter_count,
            "qasm_content": self._qasm(
                qubit_count,
                request["ansatz_layers"],
                np.zeros(parameter_count),
                request.get("initial_occupied_qubits", []),
            ),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, request["measurement_grouping"]),
        }

    def execute(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        history: list[dict] = []
        parameter_count = qubit_count * request["ansatz_layers"]
        optimizer = "Powell"

        def objective(parameters: np.ndarray) -> float:
            measurement = self._measure_pauli_terms(
                qubit_count,
                pauli_terms,
                parameters,
                request["ansatz_layers"],
                request.get("initial_occupied_qubits", []),
            )
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

        result = minimize(
            objective,
            np.zeros(parameter_count),
            method=optimizer,
            options={
                "maxiter": request["max_iterations"],
                "xtol": request["convergence_tolerance"],
                "ftol": request["convergence_tolerance"],
            },
        )
        return {
            "final_energy_hartree": float(result.fun),
            "energy_uncertainty_hartree": 0.0,
            "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
            "best_parameters": result.x.tolist(),
            "optimizer": optimizer,
            "converged": bool(result.success),
            "optimizer_diagnostics": self._optimizer_diagnostics(result, history, optimizer),
            "history": history,
            "qasm_content": self._qasm(
                qubit_count,
                request["ansatz_layers"],
                result.x,
                request.get("initial_occupied_qubits", []),
            ),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, "qubit_wise_commuting"),
        }

    @staticmethod
    def _optimizer_diagnostics(result, history: list[dict], optimizer: str) -> dict:
        """Expose SciPy's termination evidence without changing its convergence decision."""
        message = str(result.message)
        status = int(result.status)
        if status == 3 and "MAXFUN" in message:
            termination_reason = "maximum_function_evaluations"
        elif bool(result.success):
            termination_reason = "optimizer_reported_success"
        elif optimizer == "COBYLA" and status == 0:
            termination_reason = "trust_region_radius_lower_bound"
        else:
            termination_reason = f"scipy_status_{status}"

        best_index, best_record = min(
            enumerate(history, start=1),
            key=lambda item: item[1]["energy_hartree"],
        )
        recent_energies = [item["energy_hartree"] for item in history[-6:]]
        return {
            "scipy_success": bool(result.success),
            "scipy_status": status,
            "scipy_message": message,
            "nfev": int(getattr(result, "nfev", len(history))),
            "termination_reason": termination_reason,
            "best_iteration": best_index,
            "initial_energy_hartree": float(history[0]["energy_hartree"]),
            "final_energy_hartree": float(result.fun),
            "recent_energy_changes_hartree": [
                float(current - previous)
                for previous, current in zip(recent_energies, recent_energies[1:])
            ],
        }

    def _measure_pauli_terms(
        self,
        qubit_count: int,
        terms: list[dict],
        parameters: np.ndarray,
        layers: int,
        initial_occupied_qubits: list[int],
    ) -> dict:
        """Evaluate each Pauli term and explicitly recompose the energy on an exact simulator."""
        state = self._statevector(qubit_count, layers, parameters, initial_occupied_qubits)
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

    def _statevector(
        self,
        qubit_count: int,
        layers: int,
        parameters: np.ndarray,
        initial_occupied_qubits: list[int] | None = None,
    ) -> np.ndarray:
        """Apply the emitted Ry-CX ansatz directly, keeping qubit zero as the least-significant bit."""
        state = np.zeros(1 << qubit_count, dtype=complex)
        initial_index = sum(1 << qubit for qubit in (initial_occupied_qubits or []))
        state[initial_index] = 1.0
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

    def _qasm(
        self,
        qubit_count: int,
        layers: int,
        parameters: np.ndarray,
        initial_occupied_qubits: list[int] | None = None,
    ) -> str:
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{qubit_count}];"]
        for qubit in initial_occupied_qubits or []:
            lines.append(f"x q[{qubit}];")
        for layer in range(layers):
            for qubit in range(qubit_count): lines.append(f"ry({parameters[layer * qubit_count + qubit]:.12f}) q[{qubit}];")
            for qubit in range(qubit_count - 1): lines.append(f"cx q[{qubit}],q[{qubit + 1}];")
        return "\n".join(lines) + "\n"
