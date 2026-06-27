"""
Gate commutativity / swap-rule engine.

Determines whether two adjacent gates in a quantum circuit DAG can be
swapped without changing the circuit semantics.  Used by the gate-ordering
optimiser to reorder gates for better teleportation merging.
"""

from __future__ import annotations

from typing import List

from .config import (
    Gate,
    SINGLE_QUBIT_GATES,
    SINGLE_QUBIT_COMMUTING_WITH_CX_CONTROL,
    SINGLE_QUBIT_COMMUTING_WITH_CX_TARGET,
)


def can_swap(gate1: Gate, gate2: Gate) -> bool:
    """Return ``True`` if *gate1* and *gate2* can be safely swapped.

    This implements the commutativity rules used by the gate-ordering
    optimiser.  The rules cover:

    - Disjoint qubit sets (always swappable).
    - Single-qubit ↔ single-qubit (swappable if on different qubits).
    - CNOT ↔ CNOT (swappable under specific control/target patterns).
    - Single-qubit ↔ CNOT (depends on which qubit and gate type).
    - CZ ↔ CZ (same as CNOT rules since CZ is symmetric).
    - CZ ↔ single-qubit (same as CNOT since CZ is symmetric).

    Args:
        gate1: First gate as ``[name, qubit, ...]``.
        gate2: Second gate as ``[name, qubit, ...]``.

    Returns:
        ``True`` if the gates commute.
    """
    type1, *qubits1 = gate1
    type2, *qubits2 = gate2

    # Normalise to int for safety
    qubits1 = [int(q) for q in qubits1]
    qubits2 = [int(q) for q in qubits2]

    # Disjoint qubit sets → always commutative
    if not (set(qubits1) & set(qubits2)):
        return True

    # ── Two-qubit ↔ two-qubit (cx or cz) ──
    if _is_two_qubit(type1) and _is_two_qubit(type2):
        if len(qubits1) != 2 or len(qubits2) != 2:
            return False
        c1, t1 = qubits1
        c2, t2 = qubits2

        # Same control, different target → commutative
        if c1 == c2 and t1 != t2:
            return True
        # Same target, different control → commutative
        if t1 == t2 and c1 != c2:
            return True
        return False

    # ── Single-qubit ↔ two-qubit ──
    if type1 in SINGLE_QUBIT_GATES and _is_two_qubit(type2):
        q = qubits1[0]
        c, t = qubits2
        # Single on control: only certain gates commute
        if q == c and type1 in SINGLE_QUBIT_COMMUTING_WITH_CX_CONTROL:
            return True
        # Single on target: only certain gates commute
        if q == t and type1 in SINGLE_QUBIT_COMMUTING_WITH_CX_TARGET:
            return True
        return False

    if _is_two_qubit(type1) and type2 in SINGLE_QUBIT_GATES:
        return can_swap(gate2, gate1)

    # ── Single-qubit ↔ single-qubit (same qubit) ──
    # Generally non-commutative on the same qubit
    if type1 in SINGLE_QUBIT_GATES and type2 in SINGLE_QUBIT_GATES:
        return qubits1[0] != qubits2[0]

    # Default: assume not commutative
    return False


def _is_two_qubit(name: str) -> bool:
    """Check whether *name* is a recognised two-qubit gate type."""
    return name in ('cx', 'cz')
