"""Preserve the sensitivity VQE protocol-implementation discrepancy without rerunning it."""

from __future__ import annotations

import json
from pathlib import Path


ARTIFACT_ROOT = Path("data/structure_artifacts")
SENSITIVITY_ARTIFACT_ID = "literature_fragment_sensitivity_fixed_sector_vqe_4a95b573f3f54846a6f194631d8af511"
OUTPUT_PATH = ARTIFACT_ROOT / "fixed_sector_vqe_protocol_v2_sensitivity_execution_audit.json"


def main() -> None:
    """Write immutable evidence that explains why the already-completed run is not accepted."""
    if OUTPUT_PATH.exists():
        raise RuntimeError("The V2 sensitivity execution audit already exists and is immutable.")
    sensitivity = json.loads((ARTIFACT_ROOT / f"{SENSITIVITY_ARTIFACT_ID}.json").read_text(encoding="utf-8"))
    result = sensitivity["result"]
    audit = {
        "artifact_type": "fixed_sector_vqe_protocol_v2_sensitivity_execution_audit",
        "immutable": True,
        "source_sensitivity_artifact_id": SENSITIVITY_ARTIFACT_ID,
        "executed_once": True,
        "retries_started": False,
        "observed_qasm_replay_error_hartree": result["qasm_replay_absolute_error_hartree"],
        "protocol_v2_qasm_replay_threshold_hartree": 1e-9,
        "legacy_hardcoded_threshold_hartree": 1e-10,
        "finding": "The completed sensitivity execution evaluated its QASM replay using the legacy 1e-10 Hartree literal rather than Protocol V2's uniform 1e-9 Hartree threshold.",
        "v2_fidelity_telemetry_present": "native_replay_statevector_infidelity" in result,
        "v2_acceptance_decision": "not_issued_due_to_missing_required_fidelity_telemetry",
        "overall_status": "benchmark_not_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2",
        "no_rerun_or_parameter_change_performed": True,
        "scientific_adsorption_validation": False,
        "ground_state_assessed": False,
    }
    with OUTPUT_PATH.open("x", encoding="utf-8") as output_file:
        json.dump(audit, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(json.dumps({"artifact_id": OUTPUT_PATH.stem, "status": audit["v2_acceptance_decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
