from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.models_db import (
    ActiveSpaceRecord,
    ClassicalReferenceRecord,
    FermionicHamiltonianRecord,
    QubitHamiltonianRecord,
    QuantumClosureBenchmarkRecord,
    QuantumRegionRecord,
    VqeCircuitRecord,
    VqeExecutionRecord,
)

from .canonical import (
    ordered_pauli_payload_bytes,
    parameter_vector_sha256,
    parse_bound_qasm2_strict,
    sha256_bytes,
    sha256_file,
)

OWNER_USER_ID = 183
RESEARCH_BENCHMARK_ID = "research_benchmark_40e77c676c7e4e8daae1cf6a23601d54"
RESEARCH_CANDIDATE_ID = "literature_candidate_567efdccf6404b07952c4084347e762b"
WORKFLOW_ID = "ssw_61650b3e9c8247f0b8b805e24008ee5d"
QUANTUM_REGION_ID = "qr_literature_fragment_bfda01cdd03a4ed2b97704aca12ad2f5"
SOURCE_CANDIDATE_SHA256 = "b3455d85aafcfb0068e5fdf1e9cba6d65829708e1b9997e1bf29a97c8f030f9e"
REGISTRATION_SCHEME = "legacy-artifact-registration-v1"


class HistoricalRegistrationError(RuntimeError):
    """Raised when frozen historical evidence cannot be registered exactly."""


@dataclass(frozen=True)
class FrozenRole:
    role: str
    hamiltonian_id: str
    hamiltonian_filename: str
    hamiltonian_sha256: str
    vqe_id: str
    vqe_filename: str
    vqe_sha256: str
    qasm_source_filename: str
    qasm_source_sha256: str
    orbital_indices: tuple[int, ...]
    active_electrons: int
    active_orbitals: int
    qubit_count: int
    pauli_term_count: int
    ordered_pauli_sha256: str
    raw_qasm_sha256: str
    canonical_circuit_sha256: str
    parameter_sha256: str
    vqe_status: str
    qualification_status: str
    failure_code: str | None
    qualification_protocol_id: str
    qualification_protocol_version: str
    remediation_filename: str | None = None
    remediation_id: str | None = None
    remediation_sha256: str | None = None
    qualification_protocol_filename: str | None = None
    qualification_protocol_sha256: str | None = None


FROZEN_ROLES = (
    FrozenRole(
        role="minimum_pipeline",
        hamiltonian_id="literature_fragment_hamiltonian_ef552009ff304746ac50193dd30d0b28",
        hamiltonian_filename="literature_fragment_hamiltonian_ef552009ff304746ac50193dd30d0b28.json",
        hamiltonian_sha256="40a16e7a4825eb1f9a421fcbda4b39e6aac4bddacf08974dd717be46667d4788",
        vqe_id="literature_fragment_minimum_fixed_sector_vqe_48ddd5939d204a91b15e44fc1a244d74",
        vqe_filename="literature_fragment_minimum_fixed_sector_vqe_48ddd5939d204a91b15e44fc1a244d74.json",
        vqe_sha256="435382630e9ae2db63d2a1e0dd7b7cd9201358edf7cd3867755be78dac234bcb",
        qasm_source_filename="literature_fragment_minimum_fixed_sector_vqe_48ddd5939d204a91b15e44fc1a244d74.json",
        qasm_source_sha256="435382630e9ae2db63d2a1e0dd7b7cd9201358edf7cd3867755be78dac234bcb",
        orbital_indices=(34, 35),
        active_electrons=2,
        active_orbitals=2,
        qubit_count=4,
        pauli_term_count=27,
        ordered_pauli_sha256="02611e34a743f3c9be1faa134456edbb14ff3755699a2cb60c05730eebde2630",
        raw_qasm_sha256="34a8432cac32dd67f5fda5d3859e9c1aed6591ae354e7b992de98f370a449e86",
        canonical_circuit_sha256="83bd90c14eb0585c37a0ea26f416694fb9ab125b696a1a832c0dd215ff38a542",
        parameter_sha256="8ae1c066e04ac5dcd7b986675ebe62567e8e056611e4abf0250e3c3ee9f78a8b",
        vqe_status="minimum_fixed_sector_vqe_accepted",
        qualification_status="minimum_fixed_sector_vqe_accepted",
        failure_code=None,
        qualification_protocol_id="minimum_fixed_sector_vqe_acceptance",
        qualification_protocol_version="1",
    ),
    FrozenRole(
        role="primary",
        hamiltonian_id="literature_fragment_hamiltonian_99866b44ecf54f0b98c09c219288bd9c",
        hamiltonian_filename="literature_fragment_hamiltonian_99866b44ecf54f0b98c09c219288bd9c.json",
        hamiltonian_sha256="68393af78e5e65cbba56eed4e96b56d40139885f3683f6d2e2cfc3bd80e22cac",
        vqe_id="literature_fragment_primary_fixed_sector_vqe_514396f1969546308d60e9fd84d926d5",
        vqe_filename="literature_fragment_primary_fixed_sector_vqe_514396f1969546308d60e9fd84d926d5.json",
        vqe_sha256="bd05a23cc42b4cb17ffda45de7da21eefb9b6621fa6cbec4846e049b5dc7fec9",
        qasm_source_filename="literature_fragment_primary_qasm_remediation_8c36cd8f0c8b4cdcb1cbc496e2bcba3b.json",
        qasm_source_sha256="183d6226ce1eefd81faab34ae8650c27c511df984da96ccab4b355da67312744",
        orbital_indices=(33, 34, 35, 37),
        active_electrons=4,
        active_orbitals=4,
        qubit_count=8,
        pauli_term_count=361,
        ordered_pauli_sha256="7b3093243e0d9efb59288f6e01c36543ec641a5ad14c934d4bce5baad3ccd69c",
        raw_qasm_sha256="f21358fc733ec68a4a297886d405ab1b670253d4f46c5127f9d5eb42e6e6fdb4",
        canonical_circuit_sha256="95eaa452d6af7bc78066ab15a5031b22b404e91446575b3d979f4eca5c2b7276",
        parameter_sha256="ace40284733bb93295513ecca45a99e2c6b716026e4968643f26d69b16386927",
        vqe_status="vqe_acceptance_not_met",
        qualification_status="primary_fixed_sector_vqe_accepted_under_protocol_v2",
        failure_code="qasm_mismatch",
        qualification_protocol_id="fixed_sector_vqe_acceptance_protocol",
        qualification_protocol_version="2",
        remediation_filename="literature_fragment_primary_qasm_remediation_8c36cd8f0c8b4cdcb1cbc496e2bcba3b.json",
        remediation_id="literature_fragment_primary_qasm_remediation_8c36cd8f0c8b4cdcb1cbc496e2bcba3b",
        remediation_sha256="183d6226ce1eefd81faab34ae8650c27c511df984da96ccab4b355da67312744",
        qualification_protocol_filename="fixed_sector_vqe_acceptance_protocol_v2.json",
        qualification_protocol_sha256="ac395d0fab207510054361b87b39abeb66f2b967f5518d0a961b3e2986fe3d20",
    ),
)


def _registration_key(
    table_name: str,
    role: str,
    source_artifact_id: str,
    source_artifact_sha256: str,
) -> str:
    preimage = "\0".join(
        (
            REGISTRATION_SCHEME,
            table_name,
            str(OWNER_USER_ID),
            role,
            source_artifact_id,
            source_artifact_sha256,
        )
    ).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def _business_id(prefix: str, registration_key: str) -> str:
    return f"{prefix}_{registration_key[:32]}"


def _load_role(
    artifact_root: Path,
    role: FrozenRole,
) -> dict[str, Any]:
    hamiltonian_path = artifact_root / role.hamiltonian_filename
    vqe_path = artifact_root / role.vqe_filename
    qasm_source_path = artifact_root / role.qasm_source_filename
    for path, expected in (
        (hamiltonian_path, role.hamiltonian_sha256),
        (vqe_path, role.vqe_sha256),
        (qasm_source_path, role.qasm_source_sha256),
    ):
        actual = sha256_file(path)
        if actual != expected:
            raise HistoricalRegistrationError(
                f"Frozen file SHA mismatch for {path.name}: {actual}"
            )
    hamiltonian = json.loads(hamiltonian_path.read_text(encoding="utf-8"))
    vqe = json.loads(vqe_path.read_text(encoding="utf-8"))
    qasm_source = json.loads(qasm_source_path.read_text(encoding="utf-8"))
    result = vqe["acceptance"] if role.role == "minimum_pipeline" else vqe["result"]
    qasm_text = (
        result["qasm_content"]
        if role.role == "minimum_pipeline"
        else qasm_source["remediation"]["qasm_content"]
    )
    parsed = parse_bound_qasm2_strict(qasm_text)
    if parsed.raw_qasm_sha256 != role.raw_qasm_sha256:
        raise HistoricalRegistrationError("Frozen raw QASM SHA mismatch.")
    if parsed.canonical_sha256 != role.canonical_circuit_sha256:
        raise HistoricalRegistrationError("Frozen canonical circuit SHA mismatch.")
    parameters = result["final_measurement"]["parameters"]
    if parameter_vector_sha256(parameters) != role.parameter_sha256:
        raise HistoricalRegistrationError("Frozen parameter SHA mismatch.")
    jordan_wigner = hamiltonian["jordan_wigner_pauli"]
    pauli_bytes = ordered_pauli_payload_bytes(
        jordan_wigner["mapping"],
        jordan_wigner["constant_energy_offset_hartree"],
    )
    if sha256_bytes(pauli_bytes) != role.ordered_pauli_sha256:
        raise HistoricalRegistrationError("Frozen ordered Pauli SHA mismatch.")
    if len(jordan_wigner["mapping"]["pauli_terms"]) != role.pauli_term_count:
        raise HistoricalRegistrationError("Frozen Pauli term count mismatch.")
    return {
        "hamiltonian_path": hamiltonian_path,
        "vqe_path": vqe_path,
        "qasm_source_path": qasm_source_path,
        "hamiltonian": hamiltonian,
        "vqe": vqe,
        "result": result,
        "qasm_text": qasm_text,
        "parameters": parameters,
    }


def _provenance(
    *,
    role: FrozenRole,
    table_name: str,
    source_artifact_id: str,
    source_path: Path,
    source_sha256: str,
    registered_at: datetime,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_origin": "historical_artifact_registration",
        "source_artifact_id": source_artifact_id,
        "source_artifact_path": str(source_path.resolve()),
        "source_artifact_sha256": source_sha256,
        "registration_scheme": REGISTRATION_SCHEME,
        "registration_key": _registration_key(
            table_name,
            role.role,
            source_artifact_id,
            source_sha256,
        ),
        "registered_at": registered_at,
        "registration_manifest": manifest,
    }


def _insert_or_verify(
    session: Session,
    model: type,
    primary_key_name: str,
    values: dict[str, Any],
) -> Any:
    registration_key = values["registration_key"]
    existing = (
        session.query(model)
        .filter(model.registration_scheme == REGISTRATION_SCHEME)
        .filter(model.registration_key == registration_key)
        .one_or_none()
    )
    if existing is not None:
        non_semantic_timestamp_fields = {"created_at", "registered_at", "completed_at"}
        for key, expected in values.items():
            if key in non_semantic_timestamp_fields:
                continue
            actual = getattr(existing, key)
            if actual != expected:
                raise HistoricalRegistrationError(
                    f"Historical registration conflict in {model.__tablename__}.{key}"
                )
        return existing
    record = model(**values)
    session.add(record)
    session.flush()
    if getattr(record, primary_key_name) != values[primary_key_name]:
        raise HistoricalRegistrationError("Historical registration ID mismatch.")
    return record


def register_frozen_history(
    session: Session,
    artifact_root: Path,
) -> dict[str, dict[str, str]]:
    """Idempotently register both frozen roles without creating compilations."""
    quantum_region = session.get(QuantumRegionRecord, QUANTUM_REGION_ID)
    if quantum_region is None or quantum_region.owner_user_id != OWNER_USER_ID:
        raise HistoricalRegistrationError("Verified owner-183 quantum region is missing.")
    registered_at = datetime.utcnow()
    output: dict[str, dict[str, str]] = {}

    for role in FROZEN_ROLES:
        loaded = _load_role(artifact_root, role)
        hamiltonian = loaded["hamiltonian"]
        result = loaded["result"]
        hamiltonian_payload = hamiltonian["hamiltonian"]
        mapping = hamiltonian["jordan_wigner_pauli"]["mapping"]
        manifest = {
            "benchmark_role": role.role,
            "owner_user_id": OWNER_USER_ID,
            "research_benchmark_id": RESEARCH_BENCHMARK_ID,
            "research_candidate_id": RESEARCH_CANDIDATE_ID,
            "workflow_id": WORKFLOW_ID,
            "quantum_region_id": QUANTUM_REGION_ID,
            "hamiltonian_artifact_id": role.hamiltonian_id,
            "hamiltonian_artifact_sha256": role.hamiltonian_sha256,
            "vqe_artifact_id": role.vqe_id,
            "vqe_artifact_sha256": role.vqe_sha256,
            "raw_qasm_sha256": role.raw_qasm_sha256,
            "canonical_circuit_sha256": role.canonical_circuit_sha256,
            "parameter_sha256": role.parameter_sha256,
            "ordered_pauli_payload_sha256": role.ordered_pauli_sha256,
            "checkpoint_sha256": hamiltonian["frozen_input"]["checkpoint_sha256"],
            "qualification_status": role.qualification_status,
            "qualification_recomputed": False,
            "scientific_adsorption_validation": False,
            "ground_state_assessed": False,
        }
        if role.remediation_sha256:
            manifest["remediation_artifact_sha256"] = role.remediation_sha256
        if role.qualification_protocol_sha256:
            manifest["qualification_protocol_artifact_sha256"] = (
                role.qualification_protocol_sha256
            )

        active_key = _registration_key(
            "active_spaces",
            role.role,
            role.hamiltonian_id,
            role.hamiltonian_sha256,
        )
        active_space_id = _business_id("as_hist", active_key)
        active_provenance = _provenance(
            role=role,
            table_name="active_spaces",
            source_artifact_id=role.hamiltonian_id,
            source_path=loaded["hamiltonian_path"],
            source_sha256=role.hamiltonian_sha256,
            registered_at=registered_at,
            manifest=manifest,
        )
        _insert_or_verify(
            session,
            ActiveSpaceRecord,
            "active_space_id",
            {
                "active_space_id": active_space_id,
                "quantum_region_id": QUANTUM_REGION_ID,
                "owner_user_id": OWNER_USER_ID,
                "active_electrons": role.active_electrons,
                "active_orbitals": role.active_orbitals,
                "orbital_indices": list(role.orbital_indices),
                "orbital_metadata": {
                    **manifest,
                    "alpha_beta_coefficient_treatment": hamiltonian_payload[
                        "alpha_beta_coefficient_treatment"
                    ],
                    "selection_rule_precedes_hamiltonian_execution": True,
                },
                "selection_reason": (
                    "Pre-frozen minimum CAS(2,2) [34,35] for pipeline validation; "
                    "not a scientific ground-state selection."
                    if role.role == "minimum_pipeline"
                    else "Independently reviewed primary CAS(4,4) [33,34,35,37], "
                    "frozen before Hamiltonian and VQE execution."
                ),
                "status": "algorithm_benchmark_frozen",
                "created_at": registered_at,
                **active_provenance,
            },
        )

        fermion_key = _registration_key(
            "fermionic_hamiltonians",
            role.role,
            role.hamiltonian_id,
            role.hamiltonian_sha256,
        )
        fermion_id = _business_id("fh_hist", fermion_key)
        _insert_or_verify(
            session,
            FermionicHamiltonianRecord,
            "hamiltonian_id",
            {
                "hamiltonian_id": fermion_id,
                "active_space_id": active_space_id,
                "owner_user_id": OWNER_USER_ID,
                "method_name": hamiltonian_payload["method_name"],
                "basis_set": hamiltonian_payload["basis_set"],
                "core_energy": hamiltonian_payload["core_energy_hartree"],
                "spin_orbital_count": hamiltonian_payload["spin_orbital_count"],
                "electron_count": hamiltonian_payload["active_electrons"],
                "artifact_path": str(loaded["hamiltonian_path"].resolve()),
                "artifact_hash": role.hamiltonian_sha256,
                "status": "active_space_mapping_validated",
                "created_at": registered_at,
                **_provenance(
                    role=role,
                    table_name="fermionic_hamiltonians",
                    source_artifact_id=role.hamiltonian_id,
                    source_path=loaded["hamiltonian_path"],
                    source_sha256=role.hamiltonian_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )

        qubit_key = _registration_key(
            "structure_qubit_hamiltonians",
            role.role,
            role.hamiltonian_id,
            role.hamiltonian_sha256,
        )
        qubit_hamiltonian_id = _business_id("qh_hist", qubit_key)
        _insert_or_verify(
            session,
            QubitHamiltonianRecord,
            "qubit_hamiltonian_id",
            {
                "qubit_hamiltonian_id": qubit_hamiltonian_id,
                "fermionic_hamiltonian_id": fermion_id,
                "owner_user_id": OWNER_USER_ID,
                "mapping_method": "jordan_wigner",
                "fallback_reason": None,
                "qubit_count": role.qubit_count,
                "qubit_count_before_tapering": role.qubit_count,
                "symmetry_tapering_applied": 0,
                "tapered_symmetries": [],
                "tapering_reason": "z2_tapering_not_requested",
                "truncation_error_estimate": 0.0,
                "pauli_term_count": role.pauli_term_count,
                "coefficient_cutoff": 0.0,
                "pauli_artifact_path": str(loaded["hamiltonian_path"].resolve()),
                "ordered_pauli_payload_sha256": role.ordered_pauli_sha256,
                "status": "active_space_mapping_validated",
                "created_at": registered_at,
                **_provenance(
                    role=role,
                    table_name="structure_qubit_hamiltonians",
                    source_artifact_id=role.hamiltonian_id,
                    source_path=loaded["hamiltonian_path"],
                    source_sha256=role.hamiltonian_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )

        qasm_source_id = (
            role.remediation_id
            if role.role == "primary"
            else role.vqe_id
        )
        circuit_key = _registration_key(
            "vqe_circuits",
            role.role,
            str(qasm_source_id),
            role.qasm_source_sha256,
        )
        circuit_id = _business_id("vc_hist", circuit_key)
        _insert_or_verify(
            session,
            VqeCircuitRecord,
            "vqe_circuit_id",
            {
                "vqe_circuit_id": circuit_id,
                "qubit_hamiltonian_id": qubit_hamiltonian_id,
                "owner_user_id": OWNER_USER_ID,
                "ansatz": "qiskit_nature_uccsd_fixed_sector",
                "ansatz_layers": 1,
                "parameter_count": len(loaded["parameters"]),
                "optimizer": "SLSQP",
                "max_iterations": 200,
                "convergence_tolerance": 1e-12,
                "shots": 0,
                "measurement_grouping": "not_applicable_statevector",
                "qasm_artifact_path": str(loaded["qasm_source_path"].resolve()),
                "measurement_plan_artifact_path": None,
                "status": "bound_qasm_frozen",
                "raw_qasm_sha256": role.raw_qasm_sha256,
                "canonical_circuit_sha256": role.canonical_circuit_sha256,
                "parameter_sha256": role.parameter_sha256,
                "parameter_hash_scheme": "parameter-ieee754-f64-le-c-v1",
                "parameters_bound": True,
                **_provenance(
                    role=role,
                    table_name="vqe_circuits",
                    source_artifact_id=str(qasm_source_id),
                    source_path=loaded["qasm_source_path"],
                    source_sha256=role.qasm_source_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )

        execution_key = _registration_key(
            "vqe_executions",
            role.role,
            role.vqe_id,
            role.vqe_sha256,
        )
        execution_id = _business_id("ve_hist", execution_key)
        _insert_or_verify(
            session,
            VqeExecutionRecord,
            "execution_id",
            {
                "execution_id": execution_id,
                "vqe_circuit_id": circuit_id,
                "owner_user_id": OWNER_USER_ID,
                "execution_backend_type": "statevector_simulator",
                "execution_backend_detail": "qiskit_fixed_sector_historical_artifact",
                "shots_total": 0,
                "converged": 1,
                "final_energy_hartree": result["final_energy_hartree"],
                "energy_uncertainty_hartree": 0.0,
                "energy_uncertainty_method": "exact_statevector_shots_0",
                "iteration_artifact_path": str(loaded["vqe_path"].resolve()),
                "status": role.vqe_status,
                **_provenance(
                    role=role,
                    table_name="vqe_executions",
                    source_artifact_id=role.vqe_id,
                    source_path=loaded["vqe_path"],
                    source_sha256=role.vqe_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )

        classical_key = _registration_key(
            "classical_references",
            role.role,
            role.hamiltonian_id,
            role.hamiltonian_sha256,
        )
        classical_id = _business_id("cr_hist", classical_key)
        _insert_or_verify(
            session,
            ClassicalReferenceRecord,
            "reference_id",
            {
                "reference_id": classical_id,
                "fermionic_hamiltonian_id": fermion_id,
                "owner_user_id": OWNER_USER_ID,
                "method": "fixed_active_space_fci",
                "energy_hartree": result["fci_energy_hartree"],
                "status": "active_space_mapping_validated",
                "artifact_path": str(loaded["hamiltonian_path"].resolve()),
                "created_at": registered_at,
                **_provenance(
                    role=role,
                    table_name="classical_references",
                    source_artifact_id=role.hamiltonian_id,
                    source_path=loaded["hamiltonian_path"],
                    source_sha256=role.hamiltonian_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )

        closure_key = _registration_key(
            "quantum_closure_benchmarks",
            role.role,
            role.vqe_id,
            role.vqe_sha256,
        )
        closure_id = _business_id("qb_hist", closure_key)
        _insert_or_verify(
            session,
            QuantumClosureBenchmarkRecord,
            "closure_benchmark_id",
            {
                "closure_benchmark_id": closure_id,
                "owner_user_id": OWNER_USER_ID,
                "research_benchmark_id": RESEARCH_BENCHMARK_ID,
                "research_candidate_id": RESEARCH_CANDIDATE_ID,
                "workflow_id": WORKFLOW_ID,
                "quantum_region_id": QUANTUM_REGION_ID,
                "active_space_id": active_space_id,
                "fermionic_hamiltonian_id": fermion_id,
                "qubit_hamiltonian_id": qubit_hamiltonian_id,
                "classical_reference_id": classical_id,
                "vqe_execution_id": execution_id,
                "source_candidate_sha256": SOURCE_CANDIDATE_SHA256,
                "fermionic_hamiltonian_sha256": role.hamiltonian_sha256,
                "pauli_hamiltonian_sha256": role.ordered_pauli_sha256,
                "mapping_method": "jordan_wigner",
                "qubit_count": role.qubit_count,
                "active_electrons": role.active_electrons,
                "active_orbitals": role.active_orbitals,
                "spin_multiplicity": 1,
                "basis_set": "def2-svp",
                "fci_energy_hartree": result["fci_energy_hartree"],
                "exact_pauli_energy_hartree": result["exact_pauli_energy_hartree"],
                "vqe_energy_hartree": result["final_energy_hartree"],
                "mapping_error_hartree": abs(
                    result["fci_energy_hartree"]
                    - result["exact_pauli_energy_hartree"]
                ),
                "vqe_error_hartree": result["absolute_error_hartree"],
                "mapping_tolerance_hartree": 1e-8,
                "vqe_target_tolerance_hartree": 0.0016,
                "status": role.vqe_status,
                "result_qualification": role.qualification_status,
                "failure_code": role.failure_code,
                "artifact_manifest": {
                    **manifest,
                    "hf_energy_hartree": result["hf_bitstring_check"][
                        "hartree_fock_energy_hartree"
                    ],
                    "correlation_recovery_ratio": result[
                        "correlation_recovery_ratio"
                    ],
                },
                "created_at": registered_at,
                "completed_at": registered_at,
                "benchmark_role": role.role,
                "qualification_protocol_id": role.qualification_protocol_id,
                "qualification_protocol_version": role.qualification_protocol_version,
                "qualification_status": role.qualification_status,
                "qualification_recomputed": False,
                "source_vqe_artifact_id": role.vqe_id,
                "source_vqe_artifact_path": str(loaded["vqe_path"].resolve()),
                "source_vqe_artifact_sha256": role.vqe_sha256,
                "remediation_artifact_id": role.remediation_id,
                "remediation_artifact_path": (
                    str((artifact_root / role.remediation_filename).resolve())
                    if role.remediation_filename
                    else None
                ),
                "remediation_artifact_sha256": role.remediation_sha256,
                "qualification_protocol_artifact_path": (
                    str(
                        (
                            artifact_root / role.qualification_protocol_filename
                        ).resolve()
                    )
                    if role.qualification_protocol_filename
                    else None
                ),
                "qualification_protocol_artifact_sha256": (
                    role.qualification_protocol_sha256
                ),
                "scientific_adsorption_validation": False,
                "ground_state_assessed": False,
                **_provenance(
                    role=role,
                    table_name="quantum_closure_benchmarks",
                    source_artifact_id=role.vqe_id,
                    source_path=loaded["vqe_path"],
                    source_sha256=role.vqe_sha256,
                    registered_at=registered_at,
                    manifest=manifest,
                ),
            },
        )
        output[role.role] = {
            "active_space_id": active_space_id,
            "fermionic_hamiltonian_id": fermion_id,
            "qubit_hamiltonian_id": qubit_hamiltonian_id,
            "vqe_circuit_id": circuit_id,
            "vqe_execution_id": execution_id,
            "classical_reference_id": classical_id,
            "closure_benchmark_id": closure_id,
        }
    return output
