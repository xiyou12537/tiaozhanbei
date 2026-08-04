from __future__ import annotations

import math


def has_sustained_gradient_oscillation(
    gradients: list[float],
    *,
    minimum_completed_cycles: int,
    window_size: int,
    minimum_direction_reversals: int,
    minimum_gradient: float,
) -> bool:
    """Return whether the confirmed UKS oscillation stop rule is satisfied."""
    if len(gradients) < minimum_completed_cycles or len(gradients) < window_size:
        return False
    window = gradients[-window_size:]
    if not all(math.isfinite(value) and value > 0 for value in window):
        return False
    directions = [
        1 if current > previous else -1 if current < previous else 0
        for previous, current in zip(window, window[1:])
    ]
    nonzero_directions = [direction for direction in directions if direction]
    reversals = sum(
        current != previous
        for previous, current in zip(nonzero_directions, nonzero_directions[1:])
    )
    return (
        reversals >= minimum_direction_reversals
        and window[-1] >= window[0]
        and min(window) > minimum_gradient
    )


def has_rapid_residual_amplification(previous: float | None, current: float | None, multiplier: float) -> bool:
    """Detect one-cycle finite positive residual growth at or above the approved multiplier."""
    if previous is None or current is None:
        return False
    if not (math.isfinite(previous) and math.isfinite(current) and previous > 0 and current > 0):
        return False
    return current >= multiplier * previous
