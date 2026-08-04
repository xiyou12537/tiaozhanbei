"""Fixed-particle-sector UCCSD validation for frozen Jordan-Wigner CAS artifacts.

This module deliberately does not reuse the generic hardware-efficient VQE
service.  It is an auditable statevector-only acceptance path for one frozen
active-space Hamiltonian at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
import math
import time

import numpy as np
from scipy.optimize import minimize


HF_REFERENCE_ENERGY_HARTREE = -1604.65289794351
HF_REFERENCE_TOLERANCE_HARTREE = 1e-10
SECTOR_TOLERANCE = 1e-10
VARIATIONAL_TOLERANCE_HARTREE = 1e-8
VQE_TARGET_TOLERANCE_HARTREE = 0.0016
CORRELATION_RECOVERY_THRESHOLD = 0.90
FIXED_SECTOR_VQE_PROTOCOL_VERSION = "fixed_sector_vqe_acceptance_protocol_v2"
QASM_REPLAY_TOLERANCE_HARTREE = 1e-9
STATEVECTOR_INFIDELITY_TOLERANCE = 1e-12
SOURCE_ENERGY_TOLERANCE_HARTREE = 1e-12
DEFAULT_RANDOM_SEED = 20260727
DEFAULT_MAX_ITERATIONS = 200
DEFAULT_MAX_WALL_TIME_SECONDS = 900


class FixedSectorVqeError(RuntimeError):
    """Raised when a frozen-sector VQE prerequisite or conservation check fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FixedSectorVqeConfiguration:
    """All numerical decisions frozen before a statevector optimization begins."""

    random_seed: int = DEFAULT_RANDOM_SEED
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    optimizer: str = "SLSQP"
    trotter_repetitions: int = 1
    shots: int = 0
    max_wall_time_seconds: int = DEFAULT_MAX_WALL_TIME_SECONDS


class FixedSectorUccsdVqeService:
    """Run UCCSD from an interleaved Jordan-Wigner HF determinant with sector audits."""

    def verify_hf_bitstring(
        self,
        pauli_terms: list[dict],
        qubit_count: int,
        alpha_electrons: int,
        beta_electrons: int,
    ) -> dict:
        """Verify the frozen interleaved JW Hartree-Fock determinant before optimization."""
        sparse_operator, statevector_class = self._qiskit_runtime(pauli_terms, qubit_count)
        hf_state = self._hf_statevector(qubit_count, alpha_electrons, beta_electrons, statevector_class)
        energy = float(np.real(hf_state.expectation_value(sparse_operator)))
        error = abs(energy - HF_REFERENCE_ENERGY_HARTREE)
        if error > HF_REFERENCE_TOLERANCE_HARTREE:
            raise FixedSectorVqeError(
                "qubit_order_mismatch",
                "Frozen Hartree-Fock bitstring energy does not match the audited interleaved Jordan-Wigner reference.",
            )
        return {
            "status": "passed",
            "hartree_fock_bitstring": self._hf_bitstring(qubit_count, alpha_electrons, beta_electrons),
            "hartree_fock_energy_hartree": energy,
            "reference_energy_hartree": HF_REFERENCE_ENERGY_HARTREE,
            "absolute_error_hartree": error,
        }

    def run_fixed_sector_acceptance(
        self,
        pauli_terms: list[dict],
        exact_pauli_energy_hartree: float,
        fci_energy_hartree: float,
        qubit_count: int,
        alpha_electrons: int,
        beta_electrons: int,
        role: str,
        configuration: FixedSectorVqeConfiguration = FixedSectorVqeConfiguration(),
    ) -> dict:
        """Optimize a fixed-sector UCCSD ansatz and perform QASM replay validation."""
        self._validate_configuration(configuration, qubit_count, alpha_electrons, beta_electrons)
        hf_check = self.verify_hf_bitstring(pauli_terms, qubit_count, alpha_electrons, beta_electrons)
        sparse_operator, statevector_class = self._qiskit_runtime(pauli_terms, qubit_count)
        ansatz, excitation_list = self._build_uccsd_ansatz(qubit_count, alpha_electrons, beta_electrons, configuration)
        number_operators = self._number_operators(qubit_count)
        initial_parameters = np.zeros(ansatz.num_parameters, dtype=float)
        history: list[dict] = []
        started_at = time.monotonic()

        def evaluate(parameters: np.ndarray, iteration: int) -> tuple[float, dict]:
            circuit = ansatz.assign_parameters(parameters, inplace=False)
            state = statevector_class.from_instruction(circuit)
            energy = float(np.real(state.expectation_value(sparse_operator)))
            sector = self._sector_measurement(state, number_operators, alpha_electrons, beta_electrons)
            if not sector["conserved"]:
                raise FixedSectorVqeError("sector_leakage", "UCCSD state left the frozen particle-number or spin-projection sector.")
            entry = {"iteration": iteration, "parameters": parameters.tolist(), "energy_hartree": energy, **sector}
            return energy, entry

        def objective(parameters: np.ndarray) -> float:
            if time.monotonic() - started_at > configuration.max_wall_time_seconds:
                raise FixedSectorVqeError("vqe_timeout", "Fixed-sector VQE exceeded its frozen wall-time limit.")
            energy, entry = evaluate(np.asarray(parameters, dtype=float), len(history) + 1)
            history.append(entry)
            return energy

        # The fixed seed is retained even though SLSQP is deterministic, so an
        # accidental optimizer replacement cannot silently introduce randomness.
        np.random.seed(configuration.random_seed)
        result = minimize(
            objective,
            initial_parameters,
            method=configuration.optimizer,
            options={"maxiter": configuration.max_iterations, "ftol": 1e-12},
        )
        final_energy, final_measurement = evaluate(np.asarray(result.x, dtype=float), len(history) + 1)
        final_circuit = ansatz.assign_parameters(result.x, inplace=False)
        native_state = statevector_class.from_instruction(final_circuit)
        qasm_content, replay_energy, replay_state = self._qasm_replay_energy(
            final_circuit,
            sparse_operator,
            statevector_class,
        )
        qasm_error = abs(replay_energy - final_energy)
        fidelity = float(abs(np.vdot(native_state.data, replay_state.data)) ** 2)
        infidelity = max(0.0, 1.0 - fidelity)
        correlation_denominator = hf_check["hartree_fock_energy_hartree"] - fci_energy_hartree
        if correlation_denominator <= 0:
            raise FixedSectorVqeError("invalid_correlation_reference", "HF energy must be above the frozen FCI reference to assess correlation recovery.")
        recovery = (hf_check["hartree_fock_energy_hartree"] - final_energy) / correlation_denominator
        checks = {
            "optimizer_converged": bool(result.success),
            "variational_condition": final_energy >= exact_pauli_energy_hartree - VARIATIONAL_TOLERANCE_HARTREE,
            "target_error": abs(final_energy - exact_pauli_energy_hartree) <= VQE_TARGET_TOLERANCE_HARTREE,
            "meaningful_correlation_recovery": recovery >= CORRELATION_RECOVERY_THRESHOLD,
            "qasm_replay": qasm_error <= QASM_REPLAY_TOLERANCE_HARTREE,
            "statevector_fidelity": infidelity <= STATEVECTOR_INFIDELITY_TOLERANCE,
            "sector_conserved": final_measurement["conserved"],
        }
        status = self._classify_acceptance(role, checks)
        return {
            "status": status,
            "implementation": "fixed_sector_qiskit_nature_uccsd",
            "configuration": {
                "acceptance_protocol": FIXED_SECTOR_VQE_PROTOCOL_VERSION,
                "shots": configuration.shots,
                "statevector": True,
                "optimizer": configuration.optimizer,
                "max_iterations": configuration.max_iterations,
                "random_seed": configuration.random_seed,
                "trotter_repetitions": configuration.trotter_repetitions,
                "max_wall_time_seconds": configuration.max_wall_time_seconds,
                "initial_parameters": initial_parameters.tolist(),
                "excitation_list": self._serialize_excitations(excitation_list),
                "alpha_beta_qubit_order": "2p=alpha,2p+1=beta",
                "hamiltonian_penalty_terms_added": False,
                "software_versions": self._software_versions(),
            },
            "hf_bitstring_check": hf_check,
            "optimizer": {"success": bool(result.success), "message": str(result.message), "iterations": int(result.nit)},
            "history": history,
            "final_measurement": final_measurement,
            "final_energy_hartree": final_energy,
            "exact_pauli_energy_hartree": exact_pauli_energy_hartree,
            "fci_energy_hartree": fci_energy_hartree,
            "absolute_error_hartree": abs(final_energy - exact_pauli_energy_hartree),
            "correlation_recovery_ratio": recovery,
            "qasm_content": qasm_content,
            "qasm_replay_energy_hartree": replay_energy,
            "qasm_replay_absolute_error_hartree": qasm_error,
            "native_replay_statevector_fidelity": fidelity,
            "native_replay_statevector_infidelity": infidelity,
            "acceptance_checks": checks,
            "scientific_adsorption_validation": False,
            "ground_state_assessed": False,
        }

    def run_minimum_cas_acceptance(
        self,
        pauli_terms: list[dict],
        exact_pauli_energy_hartree: float,
        fci_energy_hartree: float,
        qubit_count: int,
        alpha_electrons: int,
        beta_electrons: int,
        configuration: FixedSectorVqeConfiguration = FixedSectorVqeConfiguration(),
    ) -> dict:
        """Retain the explicit minimum-CAS entry point while routing through the common fixed-sector logic."""
        return self.run_fixed_sector_acceptance(
            pauli_terms,
            exact_pauli_energy_hartree,
            fci_energy_hartree,
            qubit_count,
            alpha_electrons,
            beta_electrons,
            role="minimum",
            configuration=configuration,
        )

    def remediate_qasm_replay(
        self,
        pauli_terms: list[dict],
        qubit_count: int,
        alpha_electrons: int,
        beta_electrons: int,
        frozen_parameters: list[float],
        expected_source_energy_hartree: float,
        configuration: FixedSectorVqeConfiguration = FixedSectorVqeConfiguration(),
    ) -> dict:
        """Replay one frozen UCCSD parameter vector through a precision-preserving QASM2 serializer.

        This intentionally constructs no optimizer and accepts no alternate initial state.  It is
        limited to an already-audited parameter vector so remediation cannot become an implicit VQE retry.
        """
        self._validate_configuration(configuration, qubit_count, alpha_electrons, beta_electrons)
        sparse_operator, statevector_class = self._qiskit_runtime(pauli_terms, qubit_count)
        ansatz, _ = self._build_uccsd_ansatz(qubit_count, alpha_electrons, beta_electrons, configuration)
        parameters = np.asarray(frozen_parameters, dtype=np.float64)
        if parameters.shape != (ansatz.num_parameters,) or not np.all(np.isfinite(parameters)):
            raise FixedSectorVqeError("frozen_parameter_vector_invalid", "Frozen UCCSD parameter count or values do not match the audited ansatz.")

        circuit = ansatz.assign_parameters(parameters, inplace=False)
        native_state = statevector_class.from_instruction(circuit)
        pre_serialization_energy = float(np.real(native_state.expectation_value(sparse_operator)))
        source_energy_error = abs(pre_serialization_energy - expected_source_energy_hartree)
        if source_energy_error > SOURCE_ENERGY_TOLERANCE_HARTREE:
            raise FixedSectorVqeError(
                "frozen_parameter_energy_mismatch",
                "Rebuilt frozen UCCSD circuit does not reproduce the source energy before QASM serialization.",
            )

        from qiskit import qasm2, transpile

        transpiled = transpile(circuit, basis_gates=["u3", "cx"], optimization_level=0)
        qasm_content = self.serialize_transpiled_qasm2_high_precision(transpiled)
        reloaded = qasm2.loads(qasm_content)
        replay_state = statevector_class.from_instruction(reloaded)
        replay_energy = float(np.real(replay_state.expectation_value(sparse_operator)))
        replay_measurement = self._sector_measurement(
            replay_state,
            self._number_operators(qubit_count),
            alpha_electrons,
            beta_electrons,
        )
        fidelity = float(abs(np.vdot(native_state.data, replay_state.data)) ** 2)
        infidelity = max(0.0, 1.0 - fidelity)
        replay_error = abs(replay_energy - pre_serialization_energy)
        checks = {
            "source_energy_reproduced": source_energy_error <= SOURCE_ENERGY_TOLERANCE_HARTREE,
            "qasm_replay": replay_error <= QASM_REPLAY_TOLERANCE_HARTREE,
            "statevector_fidelity": infidelity <= STATEVECTOR_INFIDELITY_TOLERANCE,
            "sector_conserved": replay_measurement["conserved"],
        }
        return {
            "status": "primary_qasm_replay_remediated" if all(checks.values()) else "qasm_mismatch",
            "parameter_count": int(parameters.size),
            "parameter_vector_sha256": hashlib.sha256(parameters.astype("<f8", copy=False).tobytes()).hexdigest(),
            "parameter_vector_encoding": "IEEE-754 binary64 little-endian",
            "circuit_depth": int(transpiled.depth()),
            "operation_counts": {name: int(count) for name, count in transpiled.count_ops().items()},
            "qasm_content": qasm_content,
            "qasm_sha256": hashlib.sha256(qasm_content.encode("utf-8")).hexdigest(),
            "pre_serialization_energy_hartree": pre_serialization_energy,
            "expected_source_energy_hartree": expected_source_energy_hartree,
            "source_energy_absolute_error_hartree": source_energy_error,
            "qasm_replay_energy_hartree": replay_energy,
            "qasm_replay_absolute_error_hartree": replay_error,
            "qasm_replay_measurement": replay_measurement,
            "native_replay_statevector_fidelity": fidelity,
            "native_replay_statevector_infidelity": infidelity,
            "acceptance_checks": checks,
        }

    def backfill_frozen_qasm_telemetry(
        self,
        pauli_terms: list[dict],
        qubit_count: int,
        alpha_electrons: int,
        beta_electrons: int,
        frozen_parameters: list[float],
        frozen_qasm_content: str,
        expected_parameter_sha256: str,
        expected_qasm_sha256: str,
        expected_native_energy_hartree: float,
        expected_qasm_replay_energy_hartree: float,
        configuration: FixedSectorVqeConfiguration = FixedSectorVqeConfiguration(),
    ) -> dict:
        """Backfill statevector telemetry from frozen parameters and existing QASM text only.

        This path does not invoke an optimizer, transpiler, or serializer.  Input hashes make
        the supplied parameter vector and QASM text immutable replay inputs.
        """
        self._validate_configuration(configuration, qubit_count, alpha_electrons, beta_electrons)
        parameters = np.asarray(frozen_parameters, dtype=np.float64)
        parameter_sha256 = self._parameter_vector_sha256(parameters)
        qasm_sha256 = hashlib.sha256(frozen_qasm_content.encode("utf-8")).hexdigest()
        if parameter_sha256 != expected_parameter_sha256:
            raise FixedSectorVqeError("backfill_parameter_hash_mismatch", "Frozen parameter vector SHA-256 does not match the approved input.")
        if qasm_sha256 != expected_qasm_sha256:
            raise FixedSectorVqeError("backfill_qasm_hash_mismatch", "Frozen QASM SHA-256 does not match the approved input.")

        sparse_operator, statevector_class = self._qiskit_runtime(pauli_terms, qubit_count)
        ansatz, _ = self._build_uccsd_ansatz(qubit_count, alpha_electrons, beta_electrons, configuration)
        if parameters.shape != (ansatz.num_parameters,) or not np.all(np.isfinite(parameters)):
            raise FixedSectorVqeError("frozen_parameter_vector_invalid", "Frozen UCCSD parameter count or values do not match the audited ansatz.")
        native_state = statevector_class.from_instruction(ansatz.assign_parameters(parameters, inplace=False))
        native_energy = float(np.real(native_state.expectation_value(sparse_operator)))
        native_energy_error = abs(native_energy - expected_native_energy_hartree)
        if native_energy_error > SOURCE_ENERGY_TOLERANCE_HARTREE:
            raise FixedSectorVqeError("backfill_native_energy_mismatch", "Native frozen-parameter energy does not reproduce the source Artifact.")

        from qiskit import qasm2

        replay_state = statevector_class.from_instruction(qasm2.loads(frozen_qasm_content))
        replay_energy = float(np.real(replay_state.expectation_value(sparse_operator)))
        replay_source_energy_error = abs(replay_energy - expected_qasm_replay_energy_hartree)
        if replay_source_energy_error > SOURCE_ENERGY_TOLERANCE_HARTREE:
            raise FixedSectorVqeError("backfill_qasm_energy_mismatch", "Existing QASM replay energy does not reproduce the source Artifact.")
        replay_measurement = self._sector_measurement(
            replay_state,
            self._number_operators(qubit_count),
            alpha_electrons,
            beta_electrons,
        )
        fidelity = float(abs(np.vdot(native_state.data, replay_state.data)) ** 2)
        infidelity = max(0.0, 1.0 - fidelity)
        return {
            "parameter_vector_sha256": parameter_sha256,
            "qasm_sha256": qasm_sha256,
            "native_energy_hartree": native_energy,
            "native_energy_absolute_error_hartree": native_energy_error,
            "qasm_replay_energy_hartree": replay_energy,
            "qasm_replay_source_energy_absolute_error_hartree": replay_source_energy_error,
            "qasm_replay_absolute_error_hartree": abs(replay_energy - native_energy),
            "native_replay_statevector_fidelity": fidelity,
            "native_replay_statevector_infidelity": infidelity,
            "qasm_replay_measurement": replay_measurement,
            "acceptance_checks": {
                "qasm_replay": abs(replay_energy - native_energy) <= QASM_REPLAY_TOLERANCE_HARTREE,
                "statevector_fidelity": infidelity <= STATEVECTOR_INFIDELITY_TOLERANCE,
                "sector_conserved": replay_measurement["conserved"],
            },
            "optimizer_executed": False,
            "qasm_retranspiled": False,
            "qasm_reserialized": False,
            "optimization_history_created": False,
        }

    @staticmethod
    def _classify_acceptance(role: str, checks: dict[str, bool]) -> str:
        """Classify only from frozen validation checks, never from comparative CAS performance."""
        accepted_statuses = {
            "minimum": "minimum_fixed_sector_vqe_accepted",
            "primary": "primary_fixed_sector_vqe_accepted",
            "sensitivity": "sensitivity_fixed_sector_vqe_accepted",
        }
        if role not in accepted_statuses:
            raise FixedSectorVqeError("fixed_sector_role_invalid", "Fixed-sector VQE role is not recognized.")
        if not checks["optimizer_converged"]:
            return "vqe_not_converged"
        if not checks["sector_conserved"]:
            return "sector_leakage"
        if not checks["variational_condition"]:
            return "non_variational_result"
        if not checks["qasm_replay"] or not checks.get("statevector_fidelity", True):
            return "qasm_mismatch"
        if not checks["meaningful_correlation_recovery"]:
            return "vqe_no_meaningful_correlation_recovery"
        if all(checks.values()):
            return accepted_statuses[role]
        return "vqe_acceptance_not_met"

    @staticmethod
    def _validate_configuration(configuration, qubit_count, alpha_electrons, beta_electrons) -> None:
        if (
            configuration.shots != 0
            or configuration.optimizer != "SLSQP"
            or configuration.trotter_repetitions != 1
            or configuration.max_wall_time_seconds != DEFAULT_MAX_WALL_TIME_SECONDS
        ):
            raise FixedSectorVqeError("fixed_sector_configuration_invalid", "Only the frozen shots=0, SLSQP, first-order single-Trotter configuration is allowed.")
        if qubit_count != 2 * (alpha_electrons + beta_electrons):
            raise FixedSectorVqeError("fixed_sector_configuration_invalid", "Minimal CAS acceptance expects two spin orbitals per active spatial orbital.")

    @staticmethod
    def _hf_bitstring(qubit_count: int, alpha_electrons: int, beta_electrons: int) -> str:
        occupied = {2 * index for index in range(alpha_electrons)} | {2 * index + 1 for index in range(beta_electrons)}
        return "".join("1" if index in occupied else "0" for index in reversed(range(qubit_count)))

    def _hf_statevector(self, qubit_count, alpha_electrons, beta_electrons, statevector_class):
        basis_index = int(self._hf_bitstring(qubit_count, alpha_electrons, beta_electrons), 2)
        return statevector_class.from_int(basis_index, 2**qubit_count)

    @staticmethod
    def _qiskit_runtime(pauli_terms: list[dict], qubit_count: int):
        try:
            from qiskit.quantum_info import SparsePauliOp, Statevector
        except ImportError as exc:  # pragma: no cover - dependency contract test covers this separately.
            raise FixedSectorVqeError("fixed_sector_dependencies_unavailable", "Pinned Qiskit and Qiskit Nature dependencies are unavailable.") from exc
        labels = []
        for term in pauli_terms:
            label = ["I"] * qubit_count
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split():
                    label[int(token[1:])] = token[0]
            labels.append(("".join(reversed(label)), float(term["coefficient"])))
        return SparsePauliOp.from_list(labels), Statevector

    @staticmethod
    def _build_uccsd_ansatz(qubit_count, alpha_electrons, beta_electrons, configuration):
        from qiskit_nature.second_q.circuit.library import HartreeFock, UCCSD
        from qiskit_nature.second_q.mappers import InterleavedQubitMapper, JordanWignerMapper

        spatial_orbitals = qubit_count // 2
        mapper = InterleavedQubitMapper(JordanWignerMapper())
        hf_state = HartreeFock(spatial_orbitals, (alpha_electrons, beta_electrons), mapper)
        ansatz = UCCSD(
            spatial_orbitals,
            (alpha_electrons, beta_electrons),
            mapper,
            reps=configuration.trotter_repetitions,
            initial_state=hf_state,
            preserve_spin=True,
        )
        return ansatz, ansatz.excitation_list

    @staticmethod
    def _number_operators(qubit_count):
        from qiskit.quantum_info import SparsePauliOp

        def occupation(qubit: int):
            label = ["I"] * qubit_count
            label[qubit] = "Z"
            return SparsePauliOp.from_list([("I" * qubit_count, 0.5), ("".join(reversed(label)), -0.5)])

        alpha = sum((occupation(index) for index in range(0, qubit_count, 2)), start=SparsePauliOp.from_list([("I" * qubit_count, 0.0)]))
        beta = sum((occupation(index) for index in range(1, qubit_count, 2)), start=SparsePauliOp.from_list([("I" * qubit_count, 0.0)]))
        return alpha, beta

    @staticmethod
    def _sector_measurement(state, number_operators, expected_alpha, expected_beta) -> dict:
        alpha_operator, beta_operator = number_operators
        alpha_mean = float(np.real(state.expectation_value(alpha_operator)))
        beta_mean = float(np.real(state.expectation_value(beta_operator)))
        alpha_variance = float(np.real(state.expectation_value(alpha_operator @ alpha_operator))) - alpha_mean**2
        beta_variance = float(np.real(state.expectation_value(beta_operator @ beta_operator))) - beta_mean**2
        alpha_error = abs(alpha_mean - expected_alpha)
        beta_error = abs(beta_mean - expected_beta)
        conserved = max(alpha_error, beta_error, abs(alpha_variance), abs(beta_variance)) <= SECTOR_TOLERANCE
        return {"alpha_electrons_expectation": alpha_mean, "beta_electrons_expectation": beta_mean, "alpha_number_variance": alpha_variance, "beta_number_variance": beta_variance, "alpha_expectation_error": alpha_error, "beta_expectation_error": beta_error, "conserved": conserved}

    @staticmethod
    def _qasm_replay_energy(circuit, sparse_operator, statevector_class):
        from qiskit import qasm2, transpile

        decomposed = transpile(circuit, basis_gates=["u3", "cx"], optimization_level=0)
        qasm_content = qasm2.dumps(decomposed)
        reloaded = qasm2.loads(qasm_content)
        state = statevector_class.from_instruction(reloaded)
        return qasm_content, float(np.real(state.expectation_value(sparse_operator))), state

    @staticmethod
    def serialize_transpiled_qasm2_high_precision(circuit) -> str:
        """Serialize a fully numeric u3/cx circuit with binary64 round-trip decimal literals.

        Qiskit's QASM2 exporter exposes no numerical-precision control.  The explicit formatter
        prevents parameter truncation while preserving the transpiler's existing gate order exactly.
        """
        lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{circuit.num_qubits}];"]
        for instruction, qubits, clbits in circuit.data:
            if clbits:
                raise FixedSectorVqeError("qasm_serialization_unsupported_instruction", "Frozen UCCSD QASM may not contain classical bits.")
            qubit_indices = [circuit.find_bit(qubit).index for qubit in qubits]
            if instruction.name == "cx" and len(qubit_indices) == 2:
                lines.append(f"cx q[{qubit_indices[0]}],q[{qubit_indices[1]}];")
                continue
            if instruction.name == "u3" and len(qubit_indices) == 1 and len(instruction.params) == 3:
                parameters = [FixedSectorUccsdVqeService._format_qasm_float(parameter) for parameter in instruction.params]
                lines.append(f"u3({','.join(parameters)}) q[{qubit_indices[0]}];")
                continue
            raise FixedSectorVqeError(
                "qasm_serialization_unsupported_instruction",
                f"Frozen transpiled circuit contains unsupported instruction: {instruction.name}.",
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_qasm_float(value) -> str:
        """Return a finite binary64 decimal literal with at least 17 significant digits."""
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise FixedSectorVqeError("qasm_serialization_nonfinite_parameter", "QASM2 cannot encode a non-finite gate parameter.")
        return format(numeric_value, ".17g")

    @staticmethod
    def _parameter_vector_sha256(parameters: np.ndarray) -> str:
        """Hash a parameter vector using the documented little-endian binary64 representation."""
        return hashlib.sha256(np.asarray(parameters, dtype="<f8").tobytes()).hexdigest()

    @staticmethod
    def _serialize_excitations(excitations) -> list[dict]:
        return [{"occupied": list(occupied), "unoccupied": list(unoccupied)} for occupied, unoccupied in excitations]

    @staticmethod
    def _software_versions() -> dict:
        return {name: metadata.version(name) for name in ("qiskit", "qiskit-terra", "qiskit-algorithms", "qiskit-nature", "numpy")}
