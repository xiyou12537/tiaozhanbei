"""Deterministic, non-computational Stage M-B resource admission checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

STO3G_SPATIAL_AO_LIMIT = 64
STO3G_SPATIAL_AO_BY_ELEMENT = {
    "H": 1,
    "He": 1,
    "Li": 5,
    "Be": 5,
    "B": 5,
    "C": 5,
    "N": 5,
    "O": 5,
    "F": 5,
    "Ne": 5,
}


def estimate_sto3g_spatial_ao(atoms: Iterable[Mapping[str, Any]]) -> int:
    """Return the frozen H–Ne/STO-3G spatial AO lookup sum.

    This is a table lookup only. It does not initialize PySCF, build a basis,
    or perform any scientific calculation.
    """

    total = 0
    for atom in atoms:
        element = atom.get("element")
        try:
            total += STO3G_SPATIAL_AO_BY_ELEMENT[element]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"STO-3G AO lookup does not support element {element!r}.") from exc
    return total
