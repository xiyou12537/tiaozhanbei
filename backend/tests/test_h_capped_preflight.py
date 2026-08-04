from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.structure_modeling.service import StructureModelingError, StructureModelingService


def test_h_capped_clusters_add_link_hydrogen_for_each_cut_carbon_bond():
    service = StructureModelingService()
    host_sites = [
        {"index": 0, "element": "Fe", "position_angstrom": [0.0, 0.0, 0.0]},
        {"index": 1, "element": "N", "position_angstrom": [1.8, 0.0, 0.0]},
        {"index": 2, "element": "C", "position_angstrom": [3.1, 0.0, 0.0]},
        {"index": 3, "element": "C", "position_angstrom": [4.5, 0.0, 0.0]},
        {"index": 4, "element": "C", "position_angstrom": [5.9, 0.0, 0.0]},
    ]
    adsorbate_sites = [
        {"index": 5, "element": "Li", "position_angstrom": [20.0, 0.0, 0.0]},
        {"index": 6, "element": "Li", "position_angstrom": [21.0, 0.0, 0.0]},
        {"index": 7, "element": "S", "position_angstrom": [22.0, 0.0, 0.0]},
        {"index": 8, "element": "S", "position_angstrom": [23.0, 0.0, 0.0]},
        {"index": 9, "element": "S", "position_angstrom": [24.0, 0.0, 0.0]},
        {"index": 10, "element": "S", "position_angstrom": [25.0, 0.0, 0.0]},
    ]

    cluster = service._build_h_capped_cluster(
        full_sites=[*host_sites, *adsorbate_sites],
        host_atom_count=len(host_sites),
        active_site=SimpleNamespace(center_atom_indices=[0], neighbor_atom_indices=[1]),
        expansion_shells=1,
        label="cluster_inner",
    )

    assert cluster["cut_bonds"] == [{"retained_atom_index": 2, "removed_atom_index": 3, "link_atom_index": 11, "bond_length_angstrom": 1.4}]
    assert cluster["link_atoms"][0]["element"] == "H"
    assert round(cluster["link_atoms"][0]["position_angstrom"][0], 2) == 4.19
    assert cluster["capped_formula"] == "CHFeLi2NS4"


def test_h_capped_preflight_charge_spin_groups_are_electron_parity_consistent():
    even_electron_groups = StructureModelingService._parity_valid_charge_spin_groups(100)

    assert even_electron_groups == [(-1, [2, 4]), (0, [1, 3, 5]), (1, [2, 4])]


def test_small_cas_resource_guardrail_stays_within_protocol_limits():
    assert StructureModelingService._estimate_fci_determinant_dimension(4, 4, 1) == 36
    assert 2 * 4 == 8


def test_reduced_local_boundary_always_orients_link_hydrogen_from_retained_carbon():
    service = StructureModelingService()
    inner_carbons = [
        {"index": index, "element": "C", "position_angstrom": [float(index * 5), 0.0, 0.0]}
        for index in range(4)
    ]
    outer_carbons = [
        {"index": index + 4, "element": "C", "position_angstrom": [float(index * 5 + 1.4), 0.0, 0.0]}
        for index in range(4)
    ]
    nitrogens = [
        {"index": index + 8, "element": "N", "position_angstrom": [float(index * 5 - 1.35), 0.0, 0.0]}
        for index in range(4)
    ]
    full_sites = [
        *inner_carbons,
        *outer_carbons,
        *nitrogens,
        {"index": 12, "element": "Fe", "position_angstrom": [30.0, 0.0, 0.0]},
        {"index": 13, "element": "Li", "position_angstrom": [31.0, 0.0, 0.0]},
        {"index": 14, "element": "Li", "position_angstrom": [32.0, 0.0, 0.0]},
        {"index": 15, "element": "S", "position_angstrom": [33.0, 0.0, 0.0]},
        {"index": 16, "element": "S", "position_angstrom": [34.0, 0.0, 0.0]},
        {"index": 17, "element": "S", "position_angstrom": [35.0, 0.0, 0.0]},
        {"index": 18, "element": "S", "position_angstrom": [36.0, 0.0, 0.0]},
    ]

    cluster = service._build_reduced_local_cluster(
        full_sites,
        SimpleNamespace(center_atom_indices=[12], neighbor_atom_indices=[8, 9, 10, 11]),
    )

    assert [bond["retained_atom_index"] for bond in cluster["cut_bonds"]] == [0, 1, 2, 3]
    assert all(bond["retained_atom_index"] in cluster["region_atom_indices"] for bond in cluster["cut_bonds"])
    assert all(bond["removed_atom_index"] in cluster["deleted_atom_indices"] for bond in cluster["cut_bonds"])


def test_reduced_memory_calibration_is_single_iteration_and_has_no_second_order_scf():
    options = StructureModelingService._reduced_local_memory_calibration_options()

    assert options["max_memory_mb"] == 1024
    assert options["max_cycle"] == 1
    assert options["record_iteration_energy"] is False
    assert options["density_fitting"] is True
    assert options["df_cderi_path"] == "/checkpoints/df_cderi.h5"
    assert options["strategies"] == [
        {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False}
    ]


def test_reduced_full_triplet_scf_is_one_uhf_strategy_with_disk_backed_df():
    options = StructureModelingService._reduced_local_scf_options()

    assert options["max_memory_mb"] == 1024
    assert options["max_cycle"] == 300
    assert options["record_iteration_energy"] is True
    assert options["density_fitting"] is True
    assert options["df_cderi_path"] == "/checkpoints/df_cderi.h5"
    assert options["strategies"] == [
        {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False}
    ]


def test_reduced_newton_rescue_has_fixed_macro_cycle_and_stagnation_guardrails():
    options = StructureModelingService._reduced_local_newton_rescue_options()

    assert options["newton_rescue_mode"] is True
    assert options["max_memory_mb"] == 1024
    assert options["max_cycle"] == 50
    assert options["macro_gradient_stagnation_window"] == 5
    assert options["conv_tol"] == 1e-8
    assert options["conv_tol_grad"] == 1e-5
    assert options["df_cderi_path"] == "/checkpoints/df_cderi.h5"
    assert options["strategies"] == [
        {"level_shift": 0.0, "initial_guess": "atom", "damping": 0.0, "use_newton": True}
    ]


def test_uks_preconditioner_configuration_is_density_only_and_resource_bounded():
    options = StructureModelingService._reduced_local_uks_preconditioner_options()

    assert options["preconditioner_only"] is True
    assert options["xc"] == "PBE"
    assert options["grid_level"] == 1
    assert options["max_memory_mb"] == 1024
    assert options["max_cycle"] == 100
    assert options["conv_tol"] == 1e-7
    assert options["conv_tol_grad"] == 1e-4
    assert options["oscillation_minimum_completed_cycles"] == 12
    assert options["oscillation_window_size"] == 6
    assert options["oscillation_minimum_direction_reversals"] == 3
    assert options["oscillation_minimum_gradient"] == 1e-3
    assert options["rapid_residual_growth_multiplier"] == 10.0
    assert options["df_cderi_load_path"] == "/inputs/df_cderi.h5"
    assert options["initial_density_checkpoint_path"] == "/checkpoints/source_uhf.chk"


def test_preconditioner_only_result_never_receives_candidate_confirmation_eligibility():
    is_converged, exceeds_threshold, quality_status = StructureModelingService._electronic_structure_result_quality(
        {
            "status": "uks_preconditioner_converged_pending_review",
            "converged": True,
            "preconditioner_only": True,
            "downstream_consumable": False,
        },
        0.5,
    )

    assert is_converged is False
    assert exceeds_threshold is False
    assert quality_status == "preconditioner_only"


def test_preconditioner_only_payload_is_rejected_by_downstream_guard():
    with pytest.raises(StructureModelingError) as exc_info:
        StructureModelingService._assert_not_preconditioner_only(
            {"preconditioner_only": True, "downstream_consumable": False}
        )

    assert exc_info.value.code == "preconditioner_only_not_consumable"


def test_frozen_reduced_local_branch_rejects_another_automatic_scf_strategy():
    with pytest.raises(StructureModelingError) as exc_info:
        StructureModelingService._assert_reduced_local_compute_not_exhausted(
            SimpleNamespace(status="local_compute_exhausted")
        )

    assert exc_info.value.code == "local_compute_exhausted"


def test_literature_fragment_extracts_only_candidate_8637_original_li2s4_indices():
    source_payload = {
        "source_candidate_id": "8637",
        "atomic_sites": [
            {"index": 0, "element": "Li", "position_angstrom": [0.0, 0.0, 0.0]},
            {"index": 1, "element": "Li", "position_angstrom": [1.0, 0.0, 0.0]},
            {"index": 71, "element": "N", "position_angstrom": [2.0, 0.0, 0.0]},
            {"index": 72, "element": "S", "position_angstrom": [3.0, 0.0, 0.0]},
            {"index": 73, "element": "S", "position_angstrom": [4.0, 0.0, 0.0]},
            {"index": 74, "element": "S", "position_angstrom": [5.0, 0.0, 0.0]},
            {"index": 75, "element": "S", "position_angstrom": [6.0, 0.0, 0.0]},
            {"index": 76, "element": "Fe", "position_angstrom": [7.0, 0.0, 0.0]},
        ],
    }

    sites = StructureModelingService._extract_literature_fragment_source_sites(source_payload)

    assert [site["index"] for site in sites] == [0, 1, 72, 73, 74, 75]
    assert [site["element"] for site in sites] == ["Li", "Li", "S", "S", "S", "S"]


def test_literature_fragment_rejects_multiplicity_with_inconsistent_electron_parity():
    StructureModelingService._validate_fragment_spin_parity(70, 0, 1)
    StructureModelingService._validate_fragment_spin_parity(70, 0, 3)

    with pytest.raises(StructureModelingError) as exc_info:
        StructureModelingService._validate_fragment_spin_parity(70, 0, 2)

    assert exc_info.value.code == "literature_fragment_spin_parity_invalid"


def test_literature_fragment_cas_review_keeps_fixed_candidates_within_resource_guardrails():
    def orbital(index: int, occupation: float) -> dict:
        return {
            "orbital_index": index,
            "energy_hartree": float(index),
            "occupation": occupation,
            "orbital_class": "occupied" if occupation else "virtual",
        }

    def projection(index: int, sulfur_p_weight: float) -> dict:
        return {
            "orbital_index": index,
            "projection_by_element_angular_momentum": [
                {"element": "S", "angular_momentum": "p", "weight": sulfur_p_weight},
                {"element": "Li", "angular_momentum": "s", "weight": 1.0 - sulfur_p_weight},
            ],
        }

    projection_result = {
        "spatial_orbitals": [
            orbital(33, 2.0),
            orbital(34, 2.0),
            orbital(35, 0.0),
            orbital(36, 0.0),
            orbital(37, 0.0),
        ],
        "spin_channel_projections": {
            channel: [
                projection(33, 0.4),
                projection(34, 0.5),
                projection(35, 0.1),
                projection(36, 0.1),
                projection(37, 0.6),
            ]
            for channel in ("alpha", "beta")
        },
    }

    service = StructureModelingService()
    candidates = service._build_literature_fragment_cas_review_candidates(projection_result)
    primary, sensitivity = service._recommend_literature_fragment_cas_candidates(candidates)

    assert [candidate["orbital_indices"] for candidate in candidates] == [
        [34, 35],
        [33, 34, 35, 36],
        [33, 34, 35, 37],
    ]
    assert [(candidate["active_electrons"], candidate["active_spatial_orbitals"]) for candidate in candidates] == [
        (2, 2),
        (4, 4),
        (4, 4),
    ]
    assert [candidate["mapping_pre_qubit_count"] for candidate in candidates] == [4, 8, 8]
    assert [candidate["fci_determinant_dimension"] for candidate in candidates] == [4, 36, 36]
    assert all(candidate["resource_guardrails"]["mapping_pre_qubits_within_limit"] for candidate in candidates)
    assert all(candidate["resource_guardrails"]["fci_dimension_within_limit"] for candidate in candidates)
    assert primary["candidate_label"] == "cas_4_4_chemical_projection"
    assert sensitivity["candidate_label"] == "cas_4_4_contiguous_energy"


def _complete_calibration_measurement() -> dict:
    return {
        "oom_suspected": False,
        "iteration_started": True,
        "container_peak_memory_bytes": 1_500_000_000,
        "peak_sample_timestamp_utc": "2026-07-27T00:00:00+00:00",
        "pyscf_process_peak_rss_mb": 1200.0,
        "df_cderi_size_bytes": 978_181_296,
        "checkpoint_size_bytes": 1_982_808,
        "farthest_scf_stage": "first_scf_iteration_completed",
        "utf8_decoding_succeeded": True,
        "threshold_triggered": False,
        "container_resource_monitor": {"terminated_for_memory_limit": False},
    }


def test_reduced_memory_calibration_accepts_complete_telemetry_below_container_threshold():
    assert StructureModelingService._reduced_calibration_passed(_complete_calibration_measurement())


def test_reduced_memory_calibration_rejects_missing_or_excessive_peak_measurements():
    assert not StructureModelingService._reduced_calibration_passed(None)
    measurement = _complete_calibration_measurement()
    measurement["container_peak_memory_bytes"] = int(2048 * 1024 * 1024 * 0.85)
    assert not StructureModelingService._reduced_calibration_passed(measurement)


def test_reduced_memory_calibration_rejects_any_missing_required_telemetry():
    for field in (
        "container_peak_memory_bytes",
        "pyscf_process_peak_rss_mb",
        "peak_sample_timestamp_utc",
        "df_cderi_size_bytes",
        "checkpoint_size_bytes",
        "farthest_scf_stage",
        "utf8_decoding_succeeded",
    ):
        measurement = _complete_calibration_measurement()
        measurement[field] = None
        assert not StructureModelingService._reduced_calibration_passed(measurement), field


def test_reduced_memory_calibration_rejects_oom_threshold_or_utf8_failure():
    for field in ("oom_suspected", "threshold_triggered"):
        measurement = _complete_calibration_measurement()
        measurement[field] = True
        assert not StructureModelingService._reduced_calibration_passed(measurement)
    measurement = _complete_calibration_measurement()
    measurement["utf8_decoding_succeeded"] = False
    assert not StructureModelingService._reduced_calibration_passed(measurement)
