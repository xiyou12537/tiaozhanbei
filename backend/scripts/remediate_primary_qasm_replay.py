"""Execute the one approved, non-optimizing QASM replay remediation for the frozen primary CAS."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from backend.services.quantum_chemistry.fixed_sector_vqe import FixedSectorUccsdVqeService, FixedSectorVqeError


ARTIFACT_ROOT = Path("data/structure_artifacts")
SOURCE_ARTIFACT_ID = "literature_fragment_primary_fixed_sector_vqe_514396f1969546308d60e9fd84d926d5"
HAMILTONIAN_ARTIFACT_ID = "literature_fragment_hamiltonian_99866b44ecf54f0b98c09c219288bd9c"
EXPECTED_SOURCE_ENERGY_HARTREE = -1604.653142370703
EXPECTED_PARAMETER_COUNT = 26


def _read_artifact(artifact_id: str) -> dict:
    """Load one frozen JSON artifact from the project Artifact root."""
    return json.loads((ARTIFACT_ROOT / f"{artifact_id}.json").read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    """Hash a frozen input artifact without interpreting its contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Create exactly one remediation Artifact; no optimization or alternative CAS execution is possible."""
    existing = list(ARTIFACT_ROOT.glob("literature_fragment_primary_qasm_remediation_*.json"))
    if existing:
        raise RuntimeError("A primary QASM remediation Artifact already exists; a second remediation is not approved.")

    source = _read_artifact(SOURCE_ARTIFACT_ID)
    hamiltonian_path = ARTIFACT_ROOT / f"{HAMILTONIAN_ARTIFACT_ID}.json"
    hamiltonian = _read_artifact(HAMILTONIAN_ARTIFACT_ID)
    result = source["result"]
    if source["role"] != "primary" or source["source_hamiltonian_artifact_id"] != HAMILTONIAN_ARTIFACT_ID:
        raise RuntimeError("Source VQE Artifact provenance does not match the approved primary Hamiltonian.")
    parameters = result["final_measurement"]["parameters"]
    if len(parameters) != EXPECTED_PARAMETER_COUNT:
        raise RuntimeError("Source VQE Artifact does not contain the approved 26-parameter vector.")

    pauli = hamiltonian["jordan_wigner_pauli"]["mapping"]
    service = FixedSectorUccsdVqeService()
    try:
        remediation = service.remediate_qasm_replay(
            pauli_terms=pauli["pauli_terms"],
            qubit_count=8,
            alpha_electrons=2,
            beta_electrons=2,
            frozen_parameters=parameters,
            expected_source_energy_hartree=EXPECTED_SOURCE_ENERGY_HARTREE,
        )
    except FixedSectorVqeError as exc:
        remediation = {"status": "qasm_mismatch", "failure_code": exc.code, "failure_message": str(exc)}

    artifact = {
        "report_type": "literature_fragment_primary_qasm_replay_remediation",
        "status": remediation["status"],
        "source_vqe_artifact_id": SOURCE_ARTIFACT_ID,
        "source_hamiltonian_artifact_id": HAMILTONIAN_ARTIFACT_ID,
        "source_hamiltonian_sha256": _sha256(hamiltonian_path),
        "frozen_parameter_count": EXPECTED_PARAMETER_COUNT,
        "serialization": {
            "format": "OpenQASM 2.0",
            "basis_gates": ["u3", "cx"],
            "optimization_level": 0,
            "float_format": ".17g",
            "gate_sequence_modified": False,
            "optimizer_reexecuted": False,
            "sensitivity_execution_started": False,
        },
        "remediation": remediation,
        "benchmark_validated_simulator_vqe_with_active_space_sensitivity": False,
        "scientific_adsorption_validation": False,
        "ground_state_assessed": False,
        "requires_independent_approval_before_sensitivity": True,
    }
    artifact_id = f"literature_fragment_primary_qasm_remediation_{uuid4().hex}"
    output_path = ARTIFACT_ROOT / f"{artifact_id}.json"
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"artifact_id": artifact_id, "status": artifact["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
