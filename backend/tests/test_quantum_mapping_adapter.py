from __future__ import annotations

import shutil

import pytest

from backend.services.electronic_structure.docker_adapter import DockerPySCFAdapter, ElectronicStructureRuntimeError


@pytest.mark.skipif(shutil.which("docker") is None, reason="requires the pinned PySCF/OpenFermion Docker runtime")
def test_parity_mapping_tapers_only_a_user_confirmed_z2_sector():
    """The adapter must never infer a Z2 sector, but must apply a validated explicit sector."""
    adapter = DockerPySCFAdapter(timeout_seconds=30)
    try:
        result = adapter.map_hamiltonian(
            {
                "one_body_integrals": [[0.5]],
                "two_body_integrals": [[[[0.0]]]],
                "core_energy_hartree": -1.0,
                "mapping_method": "parity",
                "coefficient_cutoff": 1e-6,
                "enable_z2_tapering": True,
                "z2_tapering_sectors": {"0": -1},
            }
        )
    except ElectronicStructureRuntimeError as exc:
        pytest.skip(f"pinned PySCF/OpenFermion image is unavailable: {exc}")

    assert result["mapping_method"] == "parity"
    assert result["z2_tapering_applied"] is True
    assert result["qubit_count_before_tapering"] == 2
    assert result["qubit_count"] == 1
    assert result["tapered_symmetries"] == [{"pauli_string": "Z0", "sector": -1}]
    assert result["pauli_terms"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="requires the pinned PySCF/OpenFermion Docker runtime")
def test_open_shell_transition_metal_returns_auditable_active_space_candidates():
    """Open-shell UHF must preserve spin evidence and retain metal d-orbital candidates."""
    adapter = DockerPySCFAdapter(timeout_seconds=30)
    try:
        result = adapter.generate_active_space_candidates(
            {
                "atomic_sites": [{"element": "Fe", "position_angstrom": [0.0, 0.0, 0.0]}],
                "total_charge": 0,
                "spin_multiplicity": 5,
                "basis_set": "def2-svp",
            }
        )
    except ElectronicStructureRuntimeError as exc:
        pytest.skip(f"pinned PySCF/OpenFermion image is unavailable: {exc}")

    assert result["method_name"] == "UHF/def2-svp"
    assert result["expected_spin_square"] == 6.0
    assert result["active_space_candidates"][0]["active_orbitals"] >= 4
    assert any(
        orbital["orbital_type"] == "metal_d_orbital"
        for candidate in result["active_space_candidates"]
        for orbital in candidate["orbital_details"]
    )
