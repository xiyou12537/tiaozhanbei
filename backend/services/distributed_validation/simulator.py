from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector

from .canonical import _full_pauli_label


class DistributedSimulationError(RuntimeError):
    """Raised when distributed statevector execution is unavailable or invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SimulationOutcome:
    """Legacy V1 result shape retained only for read compatibility."""

    metrics: dict[str, Any]
    acceptance_checks: dict[str, bool]
    qualification_status: str
    resource_telemetry: dict[str, Any]


def _build_distributed_circuit(executable: dict[str, Any]) -> QuantumCircuit:
    circuit = QuantumCircuit(int(executable["qubit_count"]))
    circuit.global_phase = float(executable["global_phase"])
    for operation in executable["operations"]:
        name = operation["name"]
        qubits = [int(qubit) for qubit in operation["qubits"]]
        if name == "u3":
            params = [float(value) for value in operation["params"]]
            if len(params) != 3 or len(qubits) != 1:
                raise DistributedSimulationError(
                    "distributed_executable_invalid",
                    "Malformed u3 operation in distributed executable.",
                )
            circuit.u(*params, qubits[0])
        elif name == "cx":
            if len(qubits) != 2:
                raise DistributedSimulationError(
                    "distributed_executable_invalid",
                    "Malformed cx operation in distributed executable.",
                )
            circuit.cx(qubits[0], qubits[1])
        else:
            raise DistributedSimulationError(
                "distributed_executable_invalid",
                f"Unsupported executable gate: {name}",
            )
    return circuit


def _observable_from_mapping(mapping: dict[str, Any]) -> SparsePauliOp:
    qubit_count = int(mapping["qubit_count"])
    terms = [
        (
            _full_pauli_label(str(term["pauli_string"]), qubit_count),
            complex(term["coefficient"]),
        )
        for term in mapping["pauli_terms"]
    ]
    # The identity term already contains the frozen energy offset.
    return SparsePauliOp.from_list(terms)


def _energy(state: Statevector, observable: SparsePauliOp) -> tuple[float, float]:
    value = complex(state.expectation_value(observable))
    return float(value.real), abs(float(value.imag))


def _sector_metrics(
    state: Statevector,
    spatial_orbitals: int,
) -> dict[str, float]:
    """Compute the historical difference-of-moments V1 diagnostic."""
    probabilities = np.abs(np.asarray(state.data, dtype=np.complex128)) ** 2
    indices = np.arange(probabilities.size, dtype=np.uint64)
    n_alpha = np.zeros(probabilities.size, dtype=np.float64)
    n_beta = np.zeros(probabilities.size, dtype=np.float64)
    for orbital in range(spatial_orbitals):
        n_alpha += ((indices >> np.uint64(2 * orbital)) & np.uint64(1)).astype(
            np.float64
        )
        n_beta += (
            (indices >> np.uint64(2 * orbital + 1)) & np.uint64(1)
        ).astype(np.float64)
    alpha_expectation = float(np.dot(probabilities, n_alpha))
    beta_expectation = float(np.dot(probabilities, n_beta))
    return {
        "n_alpha_expectation": alpha_expectation,
        "n_beta_expectation": beta_expectation,
        "n_alpha_variance": float(
            np.dot(probabilities, n_alpha * n_alpha) - alpha_expectation**2
        ),
        "n_beta_variance": float(
            np.dot(probabilities, n_beta * n_beta) - beta_expectation**2
        ),
    }


def _fixed_sector_exact_energy(
    observable: SparsePauliOp,
    spatial_orbitals: int,
    target_alpha: int,
    target_beta: int,
) -> float:
    qubit_count = spatial_orbitals * 2
    allowed_indices: list[int] = []
    for basis_index in range(2**qubit_count):
        alpha = sum(
            (basis_index >> (2 * orbital)) & 1
            for orbital in range(spatial_orbitals)
        )
        beta = sum(
            (basis_index >> (2 * orbital + 1)) & 1
            for orbital in range(spatial_orbitals)
        )
        if alpha == target_alpha and beta == target_beta:
            allowed_indices.append(basis_index)
    matrix = np.asarray(observable.to_matrix(), dtype=np.complex128)
    sector_matrix = matrix[np.ix_(allowed_indices, allowed_indices)]
    eigenvalues = np.linalg.eigvalsh(sector_matrix)
    return float(eigenvalues[0].real)


def simulate_statevector_v1(
    *,
    logical_circuit: QuantumCircuit,
    distributed_executable: dict[str, Any],
    pauli_mapping: dict[str, Any],
    e_classical_exact: float,
    e_exact_pauli: float,
    upstream_logical_energy: float,
    hf_energy: float,
    target_alpha: int,
    target_beta: int,
    thresholds: dict[str, float],
) -> SimulationOutcome:
    """Reject execution because V1 is permanently sealed historical evidence."""
    del (
        logical_circuit,
        distributed_executable,
        pauli_mapping,
        e_classical_exact,
        e_exact_pauli,
        upstream_logical_energy,
        hf_energy,
        target_alpha,
        target_beta,
        thresholds,
    )
    raise DistributedSimulationError(
        "v1_execution_sealed",
        "V1 is immutable historical evidence and cannot be executed again.",
    )
