from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.dft_engine.adapter import Cp2kAdapter, DftEngineError, QuantumEspressoAdapter


ATOMIC_SITES = [
    {"index": 0, "element": "Fe", "position_angstrom": [0.0, 0.0, 0.0]},
    {"index": 1, "element": "N", "position_angstrom": [1.9, 0.0, 0.0]},
]


def _metadata() -> dict:
    return {
        "total_charge": -1,
        "spin_multiplicity": 3,
        "spin_polarization": True,
        "initial_magnetization_by_element": {"Fe": 0.5, "N": 0.0},
    }


def test_quantum_espresso_input_preserves_charge_and_element_magnetization(tmp_path: Path) -> None:
    (tmp_path / "Fe.upf").write_text("pseudo", encoding="utf-8")
    (tmp_path / "N.upf").write_text("pseudo", encoding="utf-8")
    adapter = QuantumEspressoAdapter("pw.x", str(tmp_path))
    specification = {
        "atomic_sites": ATOMIC_SITES,
        "calculation_type": "geometry_optimization",
        "calculation_metadata": _metadata(),
        "engine_settings": {
            "pseudopotentials": {"Fe": "Fe.upf", "N": "N.upf"},
            "cell_parameters_angstrom": [[10, 0, 0], [0, 10, 0], [0, 0, 18]],
            "k_points": [3, 3, 1],
        },
    }

    content = adapter.write_input(specification, tmp_path).read_text(encoding="utf-8")

    assert "calculation = 'relax'" in content
    assert "tot_charge = -1" in content
    assert "nspin = 2" in content
    assert "starting_magnetization(1) = 0.5" in content
    assert "starting_magnetization(2) = 0.0" in content
    assert "requested_spin_multiplicity = 3" in content


def test_quantum_espresso_rejects_incomplete_spin_input_and_neb(tmp_path: Path) -> None:
    adapter = QuantumEspressoAdapter("pw.x", str(tmp_path))
    base_specification = {
        "atomic_sites": ATOMIC_SITES,
        "calculation_type": "geometry_optimization",
        "calculation_metadata": {**_metadata(), "initial_magnetization_by_element": {"Fe": 0.5}},
        "engine_settings": {
            "pseudopotentials": {"Fe": "Fe.upf", "N": "N.upf"},
            "cell_parameters_angstrom": [[10, 0, 0], [0, 10, 0], [0, 0, 18]],
        },
    }
    with pytest.raises(DftEngineError, match="缺少元素初始磁化"):
        adapter.write_input(base_specification, tmp_path)

    neb_specification = {
        **base_specification,
        "calculation_type": "neb",
        "calculation_metadata": _metadata(),
    }
    with pytest.raises(DftEngineError, match="未实现 NEB"):
        adapter.write_input(neb_specification, tmp_path)


def test_cp2k_input_preserves_charge_multiplicity_and_uks(tmp_path: Path) -> None:
    adapter = Cp2kAdapter("cp2k")
    specification = {
        "atomic_sites": ATOMIC_SITES,
        "calculation_type": "single_point",
        "calculation_metadata": _metadata(),
        "engine_settings": {
            "basis_sets": {"Fe": "DZVP-MOLOPT-SR-GTH", "N": "DZVP-MOLOPT-GTH"},
            "potentials": {"Fe": "GTH-PBE-q16", "N": "GTH-PBE-q5"},
        },
    }

    content = adapter.write_input(specification, tmp_path).read_text(encoding="utf-8")

    assert "RUN_TYPE ENERGY" in content
    assert "CHARGE -1" in content
    assert "MULTIPLICITY 3" in content
    assert "UKS .TRUE." in content
    assert adapter.command(tmp_path / "cp2k.inp") == ["cp2k", "-i", str(tmp_path / "cp2k.inp")]
