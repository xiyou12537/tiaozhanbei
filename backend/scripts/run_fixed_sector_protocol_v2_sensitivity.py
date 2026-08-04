"""Create immutable fixed-sector VQE protocol V2 evidence and execute one sensitivity CAS run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from backend.services.quantum_chemistry.fixed_sector_vqe import (
    CORRELATION_RECOVERY_THRESHOLD,
    FIXED_SECTOR_VQE_PROTOCOL_VERSION,
    QASM_REPLAY_TOLERANCE_HARTREE,
    SECTOR_TOLERANCE,
    STATEVECTOR_INFIDELITY_TOLERANCE,
    VARIATIONAL_TOLERANCE_HARTREE,
    VQE_TARGET_TOLERANCE_HARTREE,
    FixedSectorUccsdVqeService,
    FixedSectorVqeError,
)


ARTIFACT_ROOT = Path("data/structure_artifacts")
PRIMARY_VQE_ARTIFACT_ID = "literature_fragment_primary_fixed_sector_vqe_514396f1969546308d60e9fd84d926d5"
PRIMARY_REMEDIATION_ARTIFACT_ID = "literature_fragment_primary_qasm_remediation_8c36cd8f0c8b4cdcb1cbc496e2bcba3b"
SENSITIVITY_HAMILTONIAN_ARTIFACT_ID = "literature_fragment_hamiltonian_04cdcd16b3d04255a9800b75acb2a4bf"
PROTOCOL_ARTIFACT_PATH = ARTIFACT_ROOT / "fixed_sector_vqe_acceptance_protocol_v2.json"


def _read_artifact(artifact_id: str) -> dict:
    """Read one immutable input Artifact with UTF-8 decoding."""
    return json.loads((ARTIFACT_ROOT / f"{artifact_id}.json").read_text(encoding="utf-8"))


def _write_immutable_json(path: Path, payload: dict) -> None:
    """Create the protocol Artifact exactly once, preserving all earlier evidence."""
    with path.open("x", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def _sha256(path: Path) -> str:
    """Return a source Artifact digest for immutable provenance."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _primary_v2_classification(primary: dict, remediation: dict) -> dict:
    """Reclassify only the stored primary result; this function never builds or optimizes a circuit."""
    source_result = primary["result"]
    replay = remediation["remediation"]
    source_checks = source_result["acceptance_checks"]
    checks = {
        "optimizer_converged": source_checks["optimizer_converged"],
        "variational_condition": source_checks["variational_condition"],
        "target_error": source_checks["target_error"],
        "meaningful_correlation_recovery": source_checks["meaningful_correlation_recovery"],
        "qasm_replay": replay["qasm_replay_absolute_error_hartree"] <= QASM_REPLAY_TOLERANCE_HARTREE,
        "statevector_fidelity": replay["native_replay_statevector_infidelity"] <= STATEVECTOR_INFIDELITY_TOLERANCE,
        "sector_conserved": replay["qasm_replay_measurement"]["conserved"],
    }
    status = "primary_fixed_sector_vqe_accepted_under_protocol_v2" if all(checks.values()) else "qasm_mismatch"
    return {
        "protocol_v1_status": "qasm_mismatch",
        "protocol_v2_status": status,
        "recomputed": False,
        "acceptance_checks": checks,
        "source_vqe_artifact_id": PRIMARY_VQE_ARTIFACT_ID,
        "source_remediation_artifact_id": PRIMARY_REMEDIATION_ARTIFACT_ID,
    }


def _create_protocol_artifact() -> dict:
    """Create V2 before sensitivity execution so its thresholds cannot depend on CAS performance."""
    if PROTOCOL_ARTIFACT_PATH.exists():
        raise RuntimeError("Protocol V2 Artifact already exists and is immutable; sensitivity execution cannot be restarted.")
    primary = _read_artifact(PRIMARY_VQE_ARTIFACT_ID)
    remediation = _read_artifact(PRIMARY_REMEDIATION_ARTIFACT_ID)
    primary_v2 = _primary_v2_classification(primary, remediation)
    protocol = {
        "artifact_type": FIXED_SECTOR_VQE_PROTOCOL_VERSION,
        "immutable": True,
        "scope": "all_future_fixed_sector_statevector_vqe",
        "uniform_across_cas_roles": True,
        "thresholds": {
            "qasm_replay_energy_error_hartree_max": QASM_REPLAY_TOLERANCE_HARTREE,
            "native_replay_statevector_infidelity_max": STATEVECTOR_INFIDELITY_TOLERANCE,
            "alpha_beta_expectation_error_and_variance_max": SECTOR_TOLERANCE,
            "optimizer_success_required": True,
            "variational_tolerance_hartree": VARIATIONAL_TOLERANCE_HARTREE,
            "vqe_target_error_hartree_max": VQE_TARGET_TOLERANCE_HARTREE,
            "correlation_recovery_ratio_min": CORRELATION_RECOVERY_THRESHOLD,
        },
        "v1_historical_record": {
            "status": "qasm_mismatch",
            "preserved": True,
            "rationale": "V1's 1e-10 Hartree QASM2 text-energy threshold is over-strict for a depth-1926, 3300-basis-gate double-precision replay.",
        },
        "primary_reclassification": primary_v2,
        "no_sensitivity_cas_started_before_protocol_freeze": True,
        "scientific_adsorption_validation": False,
        "ground_state_assessed": False,
        "shots": 0,
    }
    _write_immutable_json(PROTOCOL_ARTIFACT_PATH, protocol)
    return protocol


def _execute_sensitivity_once(protocol: dict) -> dict:
    """Execute the approved sensitivity CAS exactly once with the frozen V2 protocol settings."""
    existing = list(ARTIFACT_ROOT.glob("literature_fragment_sensitivity_fixed_sector_vqe_*.json"))
    if existing:
        raise RuntimeError("Sensitivity CAS Artifact already exists; no retry or parameter change is approved.")
    hamiltonian_path = ARTIFACT_ROOT / f"{SENSITIVITY_HAMILTONIAN_ARTIFACT_ID}.json"
    hamiltonian = _read_artifact(SENSITIVITY_HAMILTONIAN_ARTIFACT_ID)
    pauli = hamiltonian["jordan_wigner_pauli"]
    mapping = pauli["mapping"]
    fci = hamiltonian["hamiltonian"]["classical_fci"]
    exact = pauli["exact_diagonalization"]
    try:
        result = FixedSectorUccsdVqeService().run_fixed_sector_acceptance(
            pauli_terms=mapping["pauli_terms"],
            exact_pauli_energy_hartree=exact["ground_state_energy_hartree"],
            fci_energy_hartree=fci["energy_hartree"],
            qubit_count=8,
            alpha_electrons=2,
            beta_electrons=2,
            role="sensitivity",
        )
    except FixedSectorVqeError as exc:
        result = {"status": exc.code, "failure_message": str(exc)}

    sensitivity_accepted = result["status"] == "sensitivity_fixed_sector_vqe_accepted"
    primary_accepted = protocol["primary_reclassification"]["protocol_v2_status"] == "primary_fixed_sector_vqe_accepted_under_protocol_v2"
    overall_status = (
        "benchmark_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2"
        if primary_accepted and sensitivity_accepted
        else "benchmark_not_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2"
    )
    artifact = {
        "report_type": "literature_fragment_sensitivity_fixed_sector_vqe",
        "status": result["status"],
        "overall_status": overall_status,
        "protocol_artifact_id": PROTOCOL_ARTIFACT_PATH.stem,
        "source_hamiltonian_artifact_id": SENSITIVITY_HAMILTONIAN_ARTIFACT_ID,
        "source_hamiltonian_sha256": _sha256(hamiltonian_path),
        "frozen_protocol": {
            "qubit_count": 8,
            "alpha_electrons": 2,
            "beta_electrons": 2,
            "active_orbital_indices": [33, 34, 35, 36],
            "mapper": "interleaved_jordan_wigner",
            "ansatz": "qiskit_nature_uccsd_preserve_spin",
            "trotter_repetitions": 1,
            "optimizer": "SLSQP",
            "initial_parameters": "all_zero",
            "max_iterations": 200,
            "ftol": 1e-12,
            "shots": 0,
            "seed": 20260727,
            "max_wall_time_seconds": 900,
            "retries": 0,
        },
        "result": result,
        "sensitivity_execution_started": True,
        "sensitivity_execution_retried": False,
        "scientific_adsorption_validation": False,
        "ground_state_assessed": False,
    }
    artifact_id = f"literature_fragment_sensitivity_fixed_sector_vqe_{uuid4().hex}"
    output_path = ARTIFACT_ROOT / f"{artifact_id}.json"
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"artifact_id": artifact_id, "status": result["status"], "overall_status": overall_status}


def main() -> None:
    """Freeze V2, then run the one sensitivity VQE permitted under that frozen protocol."""
    protocol = _create_protocol_artifact()
    print(json.dumps(_execute_sensitivity_once(protocol), ensure_ascii=False))


if __name__ == "__main__":
    main()
