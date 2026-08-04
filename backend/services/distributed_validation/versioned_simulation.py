from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
import psutil
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from .remediation_protocol import RemediationProtocol
from .simulator import (
    _build_distributed_circuit,
    _energy,
    _fixed_sector_exact_energy,
    _observable_from_mapping,
)

FaultInjector = Callable[[str], None]

EXPECTED_METRICS = (
    "e_classical_exact",
    "e_exact_pauli",
    "e_exact_pauli_runtime_regression",
    "e_logical_vqe",
    "e_distributed",
    "error_fci_vs_pauli",
    "error_runtime_exact_regression",
    "error_logical_vs_upstream",
    "error_logical_vs_pauli",
    "error_distributed_vs_logical",
    "error_distributed_vs_pauli",
    "statevector_fidelity",
    "statevector_infidelity",
    "logical_norm_error",
    "distributed_norm_error",
    "logical_energy_imaginary_absolute",
    "distributed_energy_imaginary_absolute",
    "correlation_recovery_ratio",
    "logical_sector",
    "distributed_sector",
)


@dataclass(frozen=True)
class MissingMetric:
    name: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "reason": self.reason}


@dataclass(frozen=True)
class SimulationObservations:
    """All observations completed before either validation or infrastructure failure."""

    metrics: dict[str, Any]
    resource_telemetry: dict[str, Any]
    stage_timings_seconds: dict[str, float]
    execution_milestones: dict[str, dict[str, Any]]
    partial: bool
    missing_metrics: tuple[MissingMetric, ...]
    infrastructure_error: dict[str, str] | None

    @property
    def distributed_semantics_simulated(self) -> bool:
        milestone = self.execution_milestones.get(
            "distributed_statevector_completed",
            {},
        )
        return bool(milestone.get("completed", False))

    def as_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "resource_telemetry": self.resource_telemetry,
            "stage_timings_seconds": self.stage_timings_seconds,
            "execution_milestones": self.execution_milestones,
            "partial": self.partial,
            "missing_metrics": [item.as_dict() for item in self.missing_metrics],
            "infrastructure_error": self.infrastructure_error,
            "distributed_semantics_simulated": self.distributed_semantics_simulated,
        }


@dataclass(frozen=True)
class SimulationAssessment:
    """A protocol-derived conclusion that never discards completed observations."""

    terminal_status: str
    qualification_status: str
    acceptance_checks: dict[str, bool]
    failure_code: str | None
    failure_stage: str | None
    failure_detail: str | None
    partial_observations_may_grant_qualification: bool

    @property
    def accepted(self) -> bool:
        return (
            self.qualification_status
            == "distributed_closure_validated_synthetic"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "terminal_status": self.terminal_status,
            "qualification_status": self.qualification_status,
            "acceptance_checks": self.acceptance_checks,
            "failure_code": self.failure_code,
            "failure_stage": self.failure_stage,
            "failure_detail": self.failure_detail,
            "accepted": self.accepted,
            "partial_observations_may_grant_qualification": (
                self.partial_observations_may_grant_qualification
            ),
        }


@dataclass(frozen=True)
class StructuredSimulationResult:
    observations: SimulationObservations
    assessment: SimulationAssessment

    def as_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations.as_dict(),
            "assessment": self.assessment.as_dict(),
        }


@dataclass
class _ObservationBuilder:
    protocol: RemediationProtocol
    started_perf: float = field(default_factory=time.perf_counter)
    metrics: dict[str, Any] = field(default_factory=dict)
    stage_timings_seconds: dict[str, float] = field(default_factory=dict)
    milestones: dict[str, dict[str, Any]] = field(default_factory=dict)
    rss_samples: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.milestones = {
            name: {"completed": False, "completed_at": None}
            for name in self.protocol.execution_milestones.ordered_names
        }
        self.sample_rss("builder_created")

    def mark(self, name: str) -> None:
        if name not in self.milestones:
            raise ValueError(f"Milestone is not declared by the protocol: {name}")
        if self.milestones[name]["completed"]:
            return
        self.milestones[name] = {
            "completed": True,
            "completed_at": _utc_now(),
        }

    def sample_rss(self, stage: str) -> None:
        self.rss_samples.append(
            {
                "stage": stage,
                "elapsed_seconds": time.perf_counter() - self.started_perf,
                "rss_bytes": psutil.Process().memory_info().rss,
                "sampled_at": _utc_now(),
            }
        )

    def stage(self, name: str, started: float) -> None:
        self.stage_timings_seconds[name] = time.perf_counter() - started
        self.sample_rss(name)

    def observations(
        self,
        *,
        failure_reason: str | None,
        infrastructure_error: dict[str, str] | None,
    ) -> SimulationObservations:
        missing = tuple(
            MissingMetric(
                name=name,
                reason=failure_reason or "metric_not_completed",
            )
            for name in EXPECTED_METRICS
            if name not in self.metrics
        )
        telemetry = {
            "simulation_elapsed_seconds": time.perf_counter() - self.started_perf,
            "process_rss_start_bytes": self.rss_samples[0]["rss_bytes"],
            "process_rss_peak_sampled_bytes": max(
                sample["rss_bytes"] for sample in self.rss_samples
            ),
            "rss_samples": list(self.rss_samples),
            "backend": self.protocol.execution_semantics.backend,
            "dtype": self.protocol.execution_semantics.statevector_dtype,
            "shots": self.protocol.execution_semantics.shots,
        }
        return SimulationObservations(
            metrics=dict(self.metrics),
            resource_telemetry=telemetry,
            stage_timings_seconds=dict(self.stage_timings_seconds),
            execution_milestones={
                name: dict(value) for name, value in self.milestones.items()
            },
            partial=bool(missing),
            missing_metrics=missing,
            infrastructure_error=infrastructure_error,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _inject(fault_injector: FaultInjector | None, stage: str) -> None:
    if fault_injector is not None:
        fault_injector(stage)


def _enforce_runtime_guardrails(builder: _ObservationBuilder) -> None:
    builder.sample_rss("resource_guardrail")
    guardrails = builder.protocol.resource_guardrails
    if builder.rss_samples[-1]["rss_bytes"] > guardrails.rss_limit_bytes:
        raise MemoryError("Synthetic RSS exceeded the fixture guardrail.")
    if (
        time.perf_counter() - builder.started_perf
        > guardrails.simulation_wall_seconds
    ):
        raise TimeoutError(
            "Synthetic simulation exceeded the fixture wall-time guardrail."
        )


def _centered_sector_metrics(
    state: Statevector,
    spatial_orbitals: int,
) -> dict[str, float]:
    probabilities = np.abs(np.asarray(state.data, dtype=np.complex128)) ** 2
    indices = np.arange(probabilities.size, dtype=np.uint64)
    n_alpha = np.zeros(probabilities.size, dtype=np.float64)
    n_beta = np.zeros(probabilities.size, dtype=np.float64)
    for orbital in range(spatial_orbitals):
        n_alpha += ((indices >> np.uint64(2 * orbital)) & np.uint64(1)).astype(
            np.float64
        )
        n_beta += ((indices >> np.uint64(2 * orbital + 1)) & np.uint64(1)).astype(
            np.float64
        )
    alpha_expectation = float(np.dot(probabilities, n_alpha))
    beta_expectation = float(np.dot(probabilities, n_beta))
    alpha_raw_variance = float(
        np.dot(probabilities, n_alpha * n_alpha) - alpha_expectation**2
    )
    beta_raw_variance = float(
        np.dot(probabilities, n_beta * n_beta) - beta_expectation**2
    )
    alpha_centered_variance = float(
        np.dot(probabilities, (n_alpha - alpha_expectation) ** 2)
    )
    beta_centered_variance = float(
        np.dot(probabilities, (n_beta - beta_expectation) ** 2)
    )
    return {
        "n_alpha_expectation": alpha_expectation,
        "n_beta_expectation": beta_expectation,
        "n_alpha_variance_raw_difference": alpha_raw_variance,
        "n_beta_variance_raw_difference": beta_raw_variance,
        "n_alpha_variance": alpha_centered_variance,
        "n_beta_variance": beta_centered_variance,
    }


def _assessment_from_observations(
    observations: SimulationObservations,
    protocol: RemediationProtocol,
    *,
    target_alpha: int,
    target_beta: int,
) -> SimulationAssessment:
    if observations.infrastructure_error is not None:
        error = observations.infrastructure_error
        return SimulationAssessment(
            terminal_status="synthetic_simulation_failed",
            qualification_status="not_validated",
            acceptance_checks={"infrastructure_completed": False},
            failure_code=error["code"],
            failure_stage=error["stage"],
            failure_detail=error["detail"],
            partial_observations_may_grant_qualification=False,
        )

    metrics = observations.metrics
    numerical = protocol.numerical_algorithms
    logical_sector = metrics["logical_sector"]
    distributed_sector = metrics["distributed_sector"]
    sector_expectation_error = max(
        abs(distributed_sector["n_alpha_expectation"] - target_alpha),
        abs(distributed_sector["n_beta_expectation"] - target_beta),
    )
    sector_variance = max(
        distributed_sector["n_alpha_variance"],
        distributed_sector["n_beta_variance"],
    )
    raw_negative_variance = min(
        logical_sector["n_alpha_variance_raw_difference"],
        logical_sector["n_beta_variance_raw_difference"],
        distributed_sector["n_alpha_variance_raw_difference"],
        distributed_sector["n_beta_variance_raw_difference"],
    )
    correlation = metrics["correlation_recovery_ratio"]
    finite_values = _metrics_are_finite(metrics)
    checks = {
        "finite_observations": finite_values,
        "raw_variance_roundoff_consistent": raw_negative_variance
        >= -numerical.particle_variance_negative_roundoff_tolerance,
        "mapping_consistency": metrics["error_fci_vs_pauli"]
        <= numerical.fci_vs_exact_pauli_hartree,
        "constant_offset_not_double_counted": metrics[
            "error_runtime_exact_regression"
        ]
        <= numerical.fci_vs_exact_pauli_hartree,
        "runtime_logical_reproduced": metrics["error_logical_vs_upstream"]
        <= numerical.runtime_logical_vs_upstream_hartree,
        "variational_condition": metrics["e_logical_vqe"]
        >= metrics["e_exact_pauli"] - numerical.variational_lower_bound_hartree,
        "logical_target_error": metrics["error_logical_vs_pauli"]
        <= numerical.logical_vs_exact_pauli_hartree,
        "distributed_target_error": metrics["error_distributed_vs_pauli"]
        <= numerical.distributed_vs_exact_pauli_hartree,
        "distributed_energy_equivalence": metrics[
            "error_distributed_vs_logical"
        ]
        <= numerical.distributed_vs_logical_hartree,
        "statevector_equivalence": metrics["statevector_infidelity"]
        <= numerical.statevector_infidelity,
        "logical_normalized": metrics["logical_norm_error"]
        <= numerical.statevector_normalization_error,
        "distributed_normalized": metrics["distributed_norm_error"]
        <= numerical.statevector_normalization_error,
        "energy_is_real": max(
            metrics["logical_energy_imaginary_absolute"],
            metrics["distributed_energy_imaginary_absolute"],
        )
        <= numerical.energy_imaginary_absolute_hartree,
        "particle_sector_expectation": sector_expectation_error
        <= numerical.particle_sector_expectation_error,
        "particle_sector_variance": sector_variance
        <= numerical.particle_sector_variance,
        "meaningful_correlation_recovery": correlation is not None
        and math.isfinite(correlation)
        and correlation >= numerical.correlation_recovery_ratio_minimum,
    }
    if all(checks.values()) and not observations.partial:
        return SimulationAssessment(
            terminal_status="synthetic_completed",
            qualification_status="distributed_closure_validated_synthetic",
            acceptance_checks=checks,
            failure_code=None,
            failure_stage=None,
            failure_detail=None,
            partial_observations_may_grant_qualification=False,
        )
    if not checks["finite_observations"] or not checks[
        "raw_variance_roundoff_consistent"
    ]:
        failure_code = "synthetic_numerical_validation_failed"
    elif not checks["statevector_equivalence"]:
        failure_code = "synthetic_distributed_state_mismatch"
    elif not checks["particle_sector_expectation"] or not checks[
        "particle_sector_variance"
    ]:
        failure_code = "synthetic_particle_sector_validation_failed"
    else:
        failure_code = "synthetic_energy_validation_failed"
    return SimulationAssessment(
        terminal_status="synthetic_acceptance_not_met",
        qualification_status="not_validated",
        acceptance_checks=checks,
        failure_code=failure_code,
        failure_stage="assessment",
        failure_detail="One or more fixture-derived acceptance checks failed.",
        partial_observations_may_grant_qualification=False,
    )


def _metrics_are_finite(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool | str):
        return True
    if isinstance(value, int | float | np.floating):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_metrics_are_finite(item) for item in value.values())
    if isinstance(value, list | tuple):
        return all(_metrics_are_finite(item) for item in value)
    return False


def simulate_statevector_versioned_v2(
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
    protocol: RemediationProtocol,
    fault_injector: FaultInjector | None = None,
) -> StructuredSimulationResult:
    """Execute V2 semantics while preserving all completed observations."""
    builder = _ObservationBuilder(protocol=protocol)
    builder.metrics.update(
        {
            "e_classical_exact": float(e_classical_exact),
            "e_exact_pauli": float(e_exact_pauli),
        }
    )
    builder.mark("simulation_started")
    current_stage = "simulation_started"
    try:
        current_stage = "logical_statevector"
        builder.mark("logical_statevector_started")
        stage_started = time.perf_counter()
        _inject(fault_injector, "before_logical_statevector")
        logical_state = Statevector.from_instruction(logical_circuit)
        builder.stage(current_stage, stage_started)
        builder.mark("logical_statevector_completed")
        _enforce_runtime_guardrails(builder)
        _inject(fault_injector, "after_logical_statevector")

        current_stage = "distributed_statevector"
        builder.mark("distributed_statevector_started")
        stage_started = time.perf_counter()
        distributed_circuit = _build_distributed_circuit(distributed_executable)
        distributed_state = Statevector.from_instruction(distributed_circuit)
        builder.stage(current_stage, stage_started)
        builder.mark("distributed_statevector_completed")
        _enforce_runtime_guardrails(builder)
        _inject(fault_injector, "after_distributed_statevector")

        current_stage = "observable_evaluation"
        stage_started = time.perf_counter()
        logical_norm_error = abs(
            float(np.vdot(logical_state.data, logical_state.data).real) - 1.0
        )
        distributed_norm_error = abs(
            float(np.vdot(distributed_state.data, distributed_state.data).real)
            - 1.0
        )
        overlap = complex(np.vdot(logical_state.data, distributed_state.data))
        fidelity = min(1.0, max(0.0, abs(overlap) ** 2))
        infidelity = max(0.0, 1.0 - fidelity)
        observable = _observable_from_mapping(pauli_mapping)
        logical_energy, logical_imaginary = _energy(logical_state, observable)
        distributed_energy, distributed_imaginary = _energy(
            distributed_state,
            observable,
        )
        builder.metrics.update(
            {
                "e_logical_vqe": logical_energy,
                "e_distributed": distributed_energy,
                "statevector_fidelity": fidelity,
                "statevector_infidelity": infidelity,
                "logical_norm_error": logical_norm_error,
                "distributed_norm_error": distributed_norm_error,
                "logical_energy_imaginary_absolute": logical_imaginary,
                "distributed_energy_imaginary_absolute": distributed_imaginary,
            }
        )
        builder.stage(current_stage, stage_started)
        builder.mark("observable_evaluation_completed")
        _enforce_runtime_guardrails(builder)
        _inject(fault_injector, "after_observable_evaluation")

        current_stage = "sector_observation"
        stage_started = time.perf_counter()
        spatial_orbitals = int(pauli_mapping["qubit_count"]) // 2
        logical_sector = _centered_sector_metrics(
            logical_state,
            spatial_orbitals,
        )
        distributed_sector = _centered_sector_metrics(
            distributed_state,
            spatial_orbitals,
        )
        regression_exact = _fixed_sector_exact_energy(
            observable,
            spatial_orbitals,
            target_alpha,
            target_beta,
        )
        error_fci_vs_pauli = abs(e_classical_exact - e_exact_pauli)
        error_runtime_exact_regression = abs(regression_exact - e_exact_pauli)
        error_logical_vs_upstream = abs(logical_energy - upstream_logical_energy)
        error_logical_vs_pauli = abs(logical_energy - e_exact_pauli)
        error_distributed_vs_logical = abs(distributed_energy - logical_energy)
        error_distributed_vs_pauli = abs(distributed_energy - e_exact_pauli)
        correlation_denominator = hf_energy - e_classical_exact
        correlation_recovery = (
            (hf_energy - logical_energy) / correlation_denominator
            if correlation_denominator != 0.0
            else None
        )
        builder.metrics.update(
            {
                "e_exact_pauli_runtime_regression": regression_exact,
                "error_fci_vs_pauli": error_fci_vs_pauli,
                "error_runtime_exact_regression": error_runtime_exact_regression,
                "error_logical_vs_upstream": error_logical_vs_upstream,
                "error_logical_vs_pauli": error_logical_vs_pauli,
                "error_distributed_vs_logical": error_distributed_vs_logical,
                "error_distributed_vs_pauli": error_distributed_vs_pauli,
                "correlation_recovery_ratio": correlation_recovery,
                "logical_sector": logical_sector,
                "distributed_sector": distributed_sector,
            }
        )
        builder.stage(current_stage, stage_started)
        builder.mark("sector_observation_completed")
        _enforce_runtime_guardrails(builder)
        _inject(fault_injector, "after_sector_observation")
    except Exception as exc:
        infrastructure_error = {
            "code": "synthetic_infrastructure_failure",
            "stage": current_stage,
            "detail": str(exc),
            "exception_type": type(exc).__name__,
        }
        builder.mark("assessment_completed")
        observations = builder.observations(
            failure_reason=f"infrastructure failure at {current_stage}",
            infrastructure_error=infrastructure_error,
        )
        assessment = _assessment_from_observations(
            observations,
            protocol,
            target_alpha=target_alpha,
            target_beta=target_beta,
        )
        return StructuredSimulationResult(observations, assessment)

    observations = builder.observations(
        failure_reason=None,
        infrastructure_error=None,
    )
    assessment = _assessment_from_observations(
        observations,
        protocol,
        target_alpha=target_alpha,
        target_beta=target_beta,
    )
    builder.mark("assessment_completed")
    observations = builder.observations(
        failure_reason=None,
        infrastructure_error=None,
    )
    return StructuredSimulationResult(observations, assessment)


def simulate_statevector_remediation(
    **kwargs: Any,
) -> StructuredSimulationResult:
    """Compatibility alias for callers migrating to the versioned V2 core."""
    return simulate_statevector_versioned_v2(**kwargs)
