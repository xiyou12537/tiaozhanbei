from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize


class VqeSimulatorService:
    """Exact statevector VQE using a number-conserving UCC excitation ansatz.

    The default ansatz applies spin-conserving single excitations and a paired
    double excitation.  Each excitation is emitted as commuting Jordan--Wigner
    Pauli rotations, decomposed only into H/S/SDG/RZ/CX.  Consequently theta=0
    is exactly the supplied Hartree--Fock determinant and the overall unitary
    preserves electron number.
    """

    ANSATZ_NAME = "uccsd_particle_conserving_pauli"
    ANSATZ_VERSION = "1.0"
    SIMULATOR_VERSION = "statevector_pauli_rotation_v2"

    def compile(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        legacy_free_rotation = "initial_occupied_qubits" not in request
        parameter_count = qubit_count * request["ansatz_layers"] if legacy_free_rotation else self.parameter_count(qubit_count, request.get("initial_occupied_qubits", []), request["ansatz_layers"])
        return {
            "parameter_count": parameter_count,
            "qasm_content": self._qasm(qubit_count, request["ansatz_layers"], np.zeros(parameter_count), request.get("initial_occupied_qubits", []), legacy_free_rotation=legacy_free_rotation),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, request["measurement_grouping"]),
        }

    @staticmethod
    def parameter_count(qubit_count: int, occupied: list[int], layers: int) -> int:
        virtual = [qubit for qubit in range(qubit_count) if qubit not in occupied]
        # spin-preserving singles plus paired doubles between occupied/virtual pairs
        singles = sum(1 for source in occupied for target in virtual if source % 2 == target % 2)
        doubles = min(len([q for q in occupied if q % 2 == 0]), len([q for q in occupied if q % 2 == 1]), len([q for q in virtual if q % 2 == 0]), len([q for q in virtual if q % 2 == 1]))
        return max(1, (singles + doubles) * layers)

    def execute(self, qubit_count: int, pauli_terms: list[dict], request: dict) -> dict:
        history: list[dict] = []
        occupied = request.get("initial_occupied_qubits", [])
        legacy_free_rotation = "initial_occupied_qubits" not in request
        parameter_count = qubit_count * request["ansatz_layers"] if legacy_free_rotation else self.parameter_count(qubit_count, occupied, request["ansatz_layers"])
        optimizer = "Powell"

        def objective(parameters: np.ndarray) -> float:
            measurement = self._measure_pauli_terms(qubit_count, pauli_terms, parameters, request["ansatz_layers"], occupied, legacy_free_rotation=legacy_free_rotation)
            history.append({
                "iteration": len(history) + 1,
                "parameters": parameters.tolist(),
                "energy_hartree": measurement["energy_hartree"],
                "energy_uncertainty_hartree": 0.0,
                "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
                "shots": request["shots"],
                "measurements": measurement["measurements"],
            })
            return measurement["energy_hartree"]

        result = minimize(objective, np.zeros(parameter_count), method=optimizer, options={"maxiter": request["max_iterations"], "xtol": request["convergence_tolerance"], "ftol": request["convergence_tolerance"]})
        best_measurement = self._measure_pauli_terms(qubit_count, pauli_terms, result.x, request["ansatz_layers"], occupied, legacy_free_rotation=legacy_free_rotation)
        zero_measurement = self._measure_pauli_terms(qubit_count, pauli_terms, np.zeros(parameter_count), request["ansatz_layers"], occupied, legacy_free_rotation=legacy_free_rotation)
        return {
            "final_energy_hartree": float(result.fun), "energy_uncertainty_hartree": 0.0,
            "energy_uncertainty_method": "statevector_exact_no_shot_sampling", "best_parameters": result.x.tolist(),
            "optimizer": optimizer, "converged": bool(result.success),
            "optimizer_diagnostics": self._optimizer_diagnostics(result, history, optimizer), "history": history,
            "qasm_content": self._qasm(qubit_count, request["ansatz_layers"], result.x, occupied, legacy_free_rotation=legacy_free_rotation),
            "measurement_plan": self._measurement_plan(qubit_count, pauli_terms, "qubit_wise_commuting"),
            "ansatz_name": "hardware_efficient_ry_cx" if legacy_free_rotation else self.ANSATZ_NAME, "ansatz_version": "legacy" if legacy_free_rotation else self.ANSATZ_VERSION,
            "simulator_version": self.SIMULATOR_VERSION,
            "zero_parameter_energy_hartree": zero_measurement["energy_hartree"],
            "first_objective_energy_hartree": history[0]["energy_hartree"],
            "particle_number_expectation": best_measurement["particle_number_expectation"],
            "particle_number_variance": best_measurement["particle_number_variance"],
        }

    @staticmethod
    def _optimizer_diagnostics(result: Any, history: list[dict], optimizer: str) -> dict:
        message, status = str(result.message), int(result.status)
        termination_reason = "maximum_function_evaluations" if status == 3 and "MAXFUN" in message else ("optimizer_reported_success" if bool(result.success) else f"scipy_status_{status}")
        best_index, _ = min(enumerate(history, start=1), key=lambda item: item[1]["energy_hartree"])
        recent = [item["energy_hartree"] for item in history[-6:]]
        return {"scipy_success": bool(result.success), "scipy_status": status, "scipy_message": message, "nfev": int(getattr(result, "nfev", len(history))), "termination_reason": termination_reason, "best_iteration": best_index, "initial_energy_hartree": float(history[0]["energy_hartree"]), "final_energy_hartree": float(result.fun), "recent_energy_changes_hartree": [float(current - previous) for previous, current in zip(recent, recent[1:])]}

    def _measure_pauli_terms(self, qubit_count: int, terms: list[dict], parameters: np.ndarray, layers: int, initial_occupied_qubits: list[int], legacy_free_rotation: bool = False, **_: Any) -> dict:
        state = self._statevector(qubit_count, layers, parameters, initial_occupied_qubits, legacy_free_rotation=legacy_free_rotation)
        energy, measurements = 0.0, []
        for term in terms:
            label = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split(): label[qubit_count - 1 - int(token[1:])] = token[0]
            expectation = self._pauli_expectation(state, label)
            contribution = term["coefficient"] * expectation
            energy += contribution
            measurements.append({"pauli_string": term["pauli_string"], "expectation_value": expectation, "coefficient": term["coefficient"], "energy_contribution_hartree": contribution})
        return {"energy_hartree": float(energy), "energy_uncertainty_hartree": 0.0, "measurements": measurements, "particle_number_expectation": self.particle_number_expectation(state), "particle_number_variance": self.particle_number_variance(state)}

    @staticmethod
    def _measurement_plan(qubit_count: int, pauli_terms: list[dict], grouping: str) -> dict:
        groups: list[dict] = []
        for term in pauli_terms:
            basis = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split(): basis[int(token[1:])] = token[0]
            for group in groups:
                if all(a == "I" or b == "I" or a == b for a, b in zip(group["basis_by_qubit"], basis)):
                    group["terms"].append(term["pauli_string"]); group["basis_by_qubit"] = [b if a == "I" else a for a, b in zip(group["basis_by_qubit"], basis)]; break
            else: groups.append({"group_index": len(groups), "basis_by_qubit": basis, "terms": [term["pauli_string"]]})
        return {"grouping": grouping, "group_count": len(groups), "groups": groups}

    def _statevector(self, qubit_count: int, layers: int, parameters: np.ndarray, initial_occupied_qubits: list[int] | None = None, legacy_free_rotation: bool = False, **_: Any) -> np.ndarray:
        state = np.zeros(1 << qubit_count, dtype=complex)
        state[sum(1 << qubit for qubit in (initial_occupied_qubits or []))] = 1.0
        operations = self._legacy_operations(qubit_count, layers, parameters) if legacy_free_rotation else self._ansatz_operations(qubit_count, layers, parameters, initial_occupied_qubits or [])
        for op in operations: self._apply_operation(state, op)
        return state

    @staticmethod
    def _legacy_operations(qubit_count: int, layers: int, parameters: np.ndarray) -> list[dict]:
        operations: list[dict] = []
        for layer in range(layers):
            operations.extend({"gate": "ry", "qubits": [qubit], "angle": float(parameters[layer * qubit_count + qubit])} for qubit in range(qubit_count))
            operations.extend({"gate": "cx", "qubits": [qubit, qubit + 1]} for qubit in range(qubit_count - 1))
        return operations

    def _ansatz_operations(self, qubit_count: int, layers: int, parameters: np.ndarray, occupied: list[int]) -> list[dict]:
        virtual = [q for q in range(qubit_count) if q not in occupied]
        single_pairs = [(source, target) for source in occupied for target in virtual if source % 2 == target % 2]
        double_pairs = list(zip([q for q in occupied if q % 2 == 0], [q for q in occupied if q % 2 == 1], [q for q in virtual if q % 2 == 0], [q for q in virtual if q % 2 == 1]))
        operations: list[dict] = []; parameter_index = 0
        for _layer in range(layers):
            for source, target in single_pairs:
                operations.extend(self._pauli_rotation_operations([(source, "X"), (target, "Y")], float(parameters[parameter_index]) / 2.0))
                operations.extend(self._pauli_rotation_operations([(source, "Y"), (target, "X")], -float(parameters[parameter_index]) / 2.0))
                parameter_index += 1
            for source_alpha, source_beta, target_alpha, target_beta in double_pairs:
                theta = float(parameters[parameter_index])
                # exp(theta/2 * (a†_ta a†_tb a_sb a_sa - h.c.)); all eight JW Pauli strings commute.
                terms = [("XXXY", -1), ("XXYX", -1), ("XYXX", 1), ("XYYY", -1), ("YXXX", 1), ("YXYY", -1), ("YYXY", 1), ("YYYX", 1)]
                qubits = [source_alpha, source_beta, target_alpha, target_beta]
                for word, sign in terms: operations.extend(self._pauli_rotation_operations(list(zip(qubits, word)), sign * theta / 8.0))
                parameter_index += 1
        return operations

    @staticmethod
    def _pauli_rotation_operations(paulis: list[tuple[int, str]], angle: float) -> list[dict]:
        # R_P(angle)=exp(-i angle P/2), compiled by basis change, parity ladder and RZ.
        operations: list[dict] = []
        for qubit, pauli in paulis:
            if pauli == "X": operations.append({"gate": "h", "qubits": [qubit]})
            elif pauli == "Y": operations.extend(({"gate": "sdg", "qubits": [qubit]}, {"gate": "h", "qubits": [qubit]}))
        ordered = [qubit for qubit, _ in paulis]
        for control, target in zip(ordered[:-1], ordered[1:]): operations.append({"gate": "cx", "qubits": [control, target]})
        operations.append({"gate": "rz", "qubits": [ordered[-1]], "angle": angle})
        for control, target in reversed(list(zip(ordered[:-1], ordered[1:]))): operations.append({"gate": "cx", "qubits": [control, target]})
        for qubit, pauli in reversed(paulis):
            if pauli == "X": operations.append({"gate": "h", "qubits": [qubit]})
            elif pauli == "Y": operations.extend(({"gate": "h", "qubits": [qubit]}, {"gate": "s", "qubits": [qubit]}))
        return operations

    def _apply_operation(self, state: np.ndarray, operation: dict) -> None:
        gate, qubits = operation["gate"], operation["qubits"]
        if gate == "x": self._apply_matrix(state, np.asarray([[0, 1], [1, 0]], complex), qubits[0])
        elif gate == "h": self._apply_matrix(state, np.asarray([[1, 1], [1, -1]], complex) / math.sqrt(2), qubits[0])
        elif gate == "s": self._apply_matrix(state, np.asarray([[1, 0], [0, 1j]], complex), qubits[0])
        elif gate == "sdg": self._apply_matrix(state, np.asarray([[1, 0], [0, -1j]], complex), qubits[0])
        elif gate in {"ry", "rz"}:
            angle = float(operation["angle"])
            matrix = np.asarray([[math.cos(angle / 2), -math.sin(angle / 2)], [math.sin(angle / 2), math.cos(angle / 2)]], complex) if gate == "ry" else np.asarray([[np.exp(-0.5j * angle), 0], [0, np.exp(0.5j * angle)]], complex)
            self._apply_matrix(state, matrix, qubits[0])
        elif gate == "cx": self._apply_cx(state, qubits[0], qubits[1])
        else: raise ValueError(f"unsupported_ansatz_gate:{gate}")

    @staticmethod
    def _apply_matrix(state: np.ndarray, matrix: np.ndarray, qubit: int) -> None:
        mask = 1 << qubit
        for index in range(len(state)):
            if index & mask: continue
            paired = index | mask; a, b = state[index], state[paired]
            state[index], state[paired] = matrix[0, 0] * a + matrix[0, 1] * b, matrix[1, 0] * a + matrix[1, 1] * b

    @staticmethod
    def _apply_cx(state: np.ndarray, control: int, target: int) -> None:
        cm, tm = 1 << control, 1 << target
        for index in range(len(state)):
            if index & cm and not index & tm:
                paired = index | tm; state[index], state[paired] = state[paired], state[index]

    @staticmethod
    def _pauli_expectation(state: np.ndarray, label: list[str]) -> float:
        transformed = np.zeros_like(state)
        for index, amplitude in enumerate(state):
            target, phase = index, 1.0 + 0.0j
            for qubit, gate in enumerate(reversed(label)):
                mask, one = 1 << qubit, bool(index & (1 << qubit))
                if gate == "X": target ^= mask
                elif gate == "Y": target ^= mask; phase *= -1.0j if one else 1.0j
                elif gate == "Z" and one: phase *= -1.0
            transformed[target] += phase * amplitude
        return float(np.vdot(state, transformed).real)

    @staticmethod
    def particle_number_expectation(state: np.ndarray) -> float:
        return float(sum(index.bit_count() * abs(amplitude) ** 2 for index, amplitude in enumerate(state)))

    def particle_number_variance(self, state: np.ndarray) -> float:
        expected = self.particle_number_expectation(state)
        second = sum(index.bit_count() ** 2 * abs(amplitude) ** 2 for index, amplitude in enumerate(state))
        return float(second - expected ** 2)

    def exact_ground_energy(self, qubit_count: int, pauli_terms: list[dict]) -> float:
        if qubit_count > 10: raise ValueError("exact_diagonalization_qubit_limit_exceeded")
        dimension = 1 << qubit_count; matrix = np.zeros((dimension, dimension), dtype=complex)
        for term in pauli_terms:
            label = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split(): label[qubit_count - 1 - int(token[1:])] = token[0]
            for column in range(dimension):
                target, phase = column, 1.0 + 0j
                for qubit, gate in enumerate(reversed(label)):
                    mask, one = 1 << qubit, bool(column & (1 << qubit))
                    if gate == "X": target ^= mask
                    elif gate == "Y": target ^= mask; phase *= -1j if one else 1j
                    elif gate == "Z" and one: phase *= -1
                matrix[target, column] += term["coefficient"] * phase
        return float(np.linalg.eigvalsh(matrix).min().real)

    def _qasm(self, qubit_count: int, layers: int, parameters: np.ndarray, occupied: list[int], legacy_free_rotation: bool = False) -> str:
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{qubit_count}];"]
        lines.extend(f"x q[{qubit}];" for qubit in occupied)
        operations = self._legacy_operations(qubit_count, layers, parameters) if legacy_free_rotation else self._ansatz_operations(qubit_count, layers, parameters, occupied)
        for op in operations:
            if op["gate"] in {"ry", "rz"}: lines.append(f"{op['gate']}({op['angle']:.12f}) q[{op['qubits'][0]}];")
            elif len(op["qubits"]) == 1: lines.append(f"{op['gate']} q[{op['qubits'][0]}];")
            else: lines.append(f"{op['gate']} q[{op['qubits'][0]}],q[{op['qubits'][1]}];")
        return "\n".join(lines) + "\n"
