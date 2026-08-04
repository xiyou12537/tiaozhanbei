"""Compatibility exports for the shared versioned simulation core."""

from .versioned_simulation import (
    EXPECTED_METRICS,
    FaultInjector,
    MissingMetric,
    SimulationAssessment,
    SimulationObservations,
    StructuredSimulationResult,
    simulate_statevector_remediation,
    simulate_statevector_versioned_v2,
)

__all__ = [
    "EXPECTED_METRICS",
    "FaultInjector",
    "MissingMetric",
    "SimulationAssessment",
    "SimulationObservations",
    "StructuredSimulationResult",
    "simulate_statevector_remediation",
    "simulate_statevector_versioned_v2",
]
