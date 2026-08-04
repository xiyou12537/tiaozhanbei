"""Perform the single approved read-only Protocol V2 telemetry backfill for sensitivity VQE."""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.quantum_chemistry.fixed_sector_vqe import (
    QASM_REPLAY_TOLERANCE_HARTREE,
    SECTOR_TOLERANCE,
    STATEVECTOR_INFIDELITY_TOLERANCE,
    FixedSectorUccsdVqeService,
    FixedSectorVqeError,
)


ARTIFACT_ROOT = Path("data/structure_artifacts")
SENSITIVITY_ARTIFACT_ID = "literature_fragment_sensitivity_fixed_sector_vqe_4a95b573f3f54846a6f194631d8af511"
SENSITIVITY_HAMILTONIAN_ARTIFACT_ID = "literature_fragment_hamiltonian_04cdcd16b3d04255a9800b75acb2a4bf"
PROTOCOL_ARTIFACT_ID = "fixed_sector_vqe_acceptance_protocol_v2"
OUTPUT_PATH = ARTIFACT_ROOT / "fixed_sector_vqe_protocol_v2_sensitivity_telemetry_backfill.json"
EXPECTED_PARAMETER_SHA256 = "c207cb3f9a3773de71975f73ed54fc5b565a5cbaa856dbaec76dfbc892dbd8e7"
EXPECTED_QASM_SHA256 = "5002c8a3c0502b0334ae3b91182d4ea2e4b231ee8fe89172c8eb36f6db4b6601"
EXPECTED_NATIVE_ENERGY_HARTREE = -1604.6529095023739
EXPECTED_QASM_REPLAY_ENERGY_HARTREE = -1604.6529095026788


def _read_artifact(artifact_id: str) -> dict:
    """Load one frozen input Artifact using UTF-8 without rewriting it."""
    return json.loads((ARTIFACT_ROOT / f"{artifact_id}.json").read_text(encoding="utf-8"))


def main() -> None:
    """Backfill only frozen QASM/statevector telemetry and write one immutable result."""
    if OUTPUT_PATH.exists():
        raise RuntimeError("Sensitivity telemetry backfill already exists; no second backfill is approved.")
    sensitivity = _read_artifact(SENSITIVITY_ARTIFACT_ID)
    hamiltonian = _read_artifact(SENSITIVITY_HAMILTONIAN_ARTIFACT_ID)
    protocol = _read_artifact(PROTOCOL_ARTIFACT_ID)
    result = sensitivity["result"]
    parameters = result["final_measurement"]["parameters"]
    mapping = hamiltonian["jordan_wigner_pauli"]["mapping"]
    try:
        telemetry = FixedSectorUccsdVqeService().backfill_frozen_qasm_telemetry(
            mapping["pauli_terms"], 8, 2, 2, parameters, result["qasm_content"],
            EXPECTED_PARAMETER_SHA256, EXPECTED_QASM_SHA256,
            EXPECTED_NATIVE_ENERGY_HARTREE, EXPECTED_QASM_REPLAY_ENERGY_HARTREE,
        )
    except FixedSectorVqeError as exc:
        telemetry = {"status": exc.code, "failure_message": str(exc)}

    source_checks = result["acceptance_checks"]
    telemetry_checks = telemetry.get("acceptance_checks", {})
    acceptance_checks = {
        "optimizer_converged": source_checks["optimizer_converged"],
        "variational_condition": source_checks["variational_condition"],
        "target_error": source_checks["target_error"],
        "meaningful_correlation_recovery": source_checks["meaningful_correlation_recovery"],
        "qasm_replay": telemetry_checks.get("qasm_replay", False),
        "statevector_fidelity": telemetry_checks.get("statevector_fidelity", False),
        "sector_conserved": telemetry_checks.get("sector_conserved", False),
    }
    sensitivity_status = (
        "sensitivity_fixed_sector_vqe_accepted_under_protocol_v2"
        if all(acceptance_checks.values())
        else "sensitivity_fixed_sector_vqe_not_accepted_under_protocol_v2"
    )
    primary_accepted = protocol["primary_reclassification"]["protocol_v2_status"] == "primary_fixed_sector_vqe_accepted_under_protocol_v2"
    overall_status = (
        "benchmark_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2"
        if primary_accepted and sensitivity_status == "sensitivity_fixed_sector_vqe_accepted_under_protocol_v2"
        else "benchmark_not_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2"
    )
    artifact = {
        "artifact_type": "fixed_sector_vqe_protocol_v2_sensitivity_telemetry_backfill",
        "immutable": True,
        "source_sensitivity_artifact_id": SENSITIVITY_ARTIFACT_ID,
        "source_hamiltonian_artifact_id": SENSITIVITY_HAMILTONIAN_ARTIFACT_ID,
        "protocol_artifact_id": PROTOCOL_ARTIFACT_ID,
        "frozen_inputs": {
            "parameter_count": len(parameters),
            "parameter_vector_sha256": EXPECTED_PARAMETER_SHA256,
            "qasm_sha256": EXPECTED_QASM_SHA256,
            "source_native_energy_hartree": EXPECTED_NATIVE_ENERGY_HARTREE,
            "source_qasm_replay_energy_hartree": EXPECTED_QASM_REPLAY_ENERGY_HARTREE,
        },
        "telemetry": telemetry,
        "acceptance_checks": acceptance_checks,
        "thresholds": {
            "qasm_replay_energy_error_hartree_max": QASM_REPLAY_TOLERANCE_HARTREE,
            "native_replay_statevector_infidelity_max": STATEVECTOR_INFIDELITY_TOLERANCE,
            "alpha_beta_expectation_error_and_variance_max": SECTOR_TOLERANCE,
        },
        "status": sensitivity_status,
        "overall_status": overall_status,
        "optimizer_reexecuted": False,
        "qasm_retranspiled": False,
        "qasm_reserialized": False,
        "optimization_history_created": False,
        "original_qasm_mismatch_preserved": True,
        "original_execution_audit_preserved": True,
        "scientific_adsorption_validation": False,
        "ground_state_assessed": False,
        "shots": 0,
    }
    with OUTPUT_PATH.open("x", encoding="utf-8") as output_file:
        json.dump(artifact, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(json.dumps({"artifact_id": OUTPUT_PATH.stem, "status": sensitivity_status, "overall_status": overall_status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
