from __future__ import annotations

from backend.quantum_chemistry_adapter.guardrails import (
    has_rapid_residual_amplification,
    has_sustained_gradient_oscillation,
)


def test_oscillation_guard_requires_twelve_completed_cycles():
    gradients = [0.002, 0.004, 0.0025, 0.0045, 0.003, 0.005]

    assert not has_sustained_gradient_oscillation(
        gradients,
        minimum_completed_cycles=12,
        window_size=6,
        minimum_direction_reversals=3,
        minimum_gradient=1e-3,
    )


def test_oscillation_guard_applies_all_confirmed_window_conditions():
    gradients = [0.01] * 6 + [0.002, 0.004, 0.0025, 0.0045, 0.003, 0.005]

    assert has_sustained_gradient_oscillation(
        gradients,
        minimum_completed_cycles=12,
        window_size=6,
        minimum_direction_reversals=3,
        minimum_gradient=1e-3,
    )
    gradients[-1] = 0.001
    assert not has_sustained_gradient_oscillation(
        gradients,
        minimum_completed_cycles=12,
        window_size=6,
        minimum_direction_reversals=3,
        minimum_gradient=1e-3,
    )


def test_rapid_residual_amplification_uses_single_cycle_tenfold_threshold():
    assert has_rapid_residual_amplification(0.02, 0.2, 10.0)
    assert not has_rapid_residual_amplification(0.02, 0.199, 10.0)
    assert not has_rapid_residual_amplification(0.0, 1.0, 10.0)
