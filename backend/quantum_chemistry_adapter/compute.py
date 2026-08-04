"""Run a small, real restricted Hartree-Fock calculation inside the Linux PySCF runtime."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256

import numpy as np
from openfermion import FermionOperator, QubitOperator, binary_code_transform, jordan_wigner, parity_code, taper_off_qubits
import pyscf
from pyscf import ao2mo, dft, fci, gto, scf
from pyscf.lib import chkfile

from guardrails import has_rapid_residual_amplification, has_sustained_gradient_oscillation

MAX_SPATIAL_ORBITALS = 12
MAX_CLASSICAL_REFERENCE_ORBITALS = 8


class PreconditionerGuardrailStop(RuntimeError):
    """Stop UKS preconditioning after a declared numerical guardrail is reached."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _file_sha256(path: str) -> str:
    """Hash a potentially large artifact without loading it into memory."""
    digest = sha256()
    with open(path, "rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: str | None, payload: dict) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as artifact_file:
        json.dump(payload, artifact_file, ensure_ascii=False, indent=2)
        artifact_file.flush()
        os.fsync(artifact_file.fileno())


def _structure_sha256(atomic_sites: list[dict]) -> str:
    canonical_sites = [
        {
            "index": site["index"],
            "element": site["element"],
            "position_angstrom": site["position_angstrom"],
        }
        for site in atomic_sites
    ]
    encoded = json.dumps(canonical_sites, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_restart_checkpoint(request: dict, scf_options: dict) -> dict | None:
    """Verify the checkpoint molecule matches the frozen calculation request before SCF."""
    expected = request.get("expected_checkpoint_metadata")
    if not expected:
        return None
    checkpoint_path = scf_options.get("checkpoint_validation_source_path") or scf_options.get("checkpoint_path")
    validation_path = scf_options.get("checkpoint_validation_path")
    validation = {
        "status": "failed",
        "checkpoint_path": checkpoint_path,
        "expected": expected,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if not checkpoint_path or not os.path.isfile(checkpoint_path):
            raise ValueError("Restart checkpoint is missing.")
        checkpoint_molecule = chkfile.load_mol(checkpoint_path)
        request_sites = request["atomic_sites"]
        checkpoint_elements = [checkpoint_molecule.atom_symbol(index) for index in range(checkpoint_molecule.natm)]
        request_elements = [site["element"] for site in request_sites]
        checkpoint_coordinates = checkpoint_molecule.atom_coords(unit="Angstrom")
        request_coordinates = np.asarray([site["position_angstrom"] for site in request_sites], dtype=float)
        actual = {
            "checkpoint_sha256": _file_sha256(checkpoint_path),
            "structure_sha256": _structure_sha256(request_sites),
            "basis_set": str(checkpoint_molecule.basis).strip().lower(),
            "total_charge": int(checkpoint_molecule.charge),
            "spin": int(checkpoint_molecule.spin),
            "spin_multiplicity": int(checkpoint_molecule.spin) + 1,
            "atom_count": int(checkpoint_molecule.natm),
            "elements_match": checkpoint_elements == request_elements,
            "coordinates_match": bool(np.allclose(checkpoint_coordinates, request_coordinates, atol=1e-8, rtol=0.0)),
        }
        actual["structure_basis_sha256"] = sha256(
            json.dumps(
                {"structure_sha256": actual["structure_sha256"], "basis_set": actual["basis_set"]},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        validation["actual"] = actual
        required_matches = (
            actual["checkpoint_sha256"] == expected["checkpoint_sha256"],
            actual["structure_sha256"] == expected["structure_sha256"],
            actual["basis_set"] == str(expected["basis_set"]).strip().lower(),
            actual["total_charge"] == int(expected["total_charge"]),
            actual["spin_multiplicity"] == int(expected["spin_multiplicity"]),
            actual["elements_match"],
            actual["coordinates_match"],
            actual["structure_basis_sha256"] == expected["structure_basis_sha256"],
        )
        if not all(required_matches):
            raise ValueError("Checkpoint molecule metadata does not match the frozen request.")
        validation["status"] = "passed"
        _write_json(validation_path, validation)
        return validation
    except Exception as exc:
        validation["error"] = str(exc)
        _write_json(validation_path, validation)
        raise


def serialize_pauli_terms(qubit_operator, coefficient_cutoff: float) -> tuple[list[dict], float]:
    """Serialize only numerically meaningful real Pauli coefficients and report discarded weight."""
    terms: list[dict] = []
    truncation_error_estimate = 0.0
    for term, value in qubit_operator.terms.items():
        coefficient = complex(value)
        if abs(coefficient.imag) > coefficient_cutoff:
            raise ValueError("量子比特 Hamiltonian 出现不可忽略的复系数，当前实数 VQE 执行器不能安全处理。")
        if abs(coefficient.real) < coefficient_cutoff:
            truncation_error_estimate += abs(coefficient.real)
            continue
        terms.append(
            {
                "pauli_string": " ".join(f"{gate}{index}" for index, gate in term) or "I",
                "coefficient": float(coefficient.real),
            }
        )
    return terms, float(truncation_error_estimate)


def discover_z_only_symmetries(qubit_operator, qubit_count: int) -> list[int]:
    """Find Z_i symmetries that commute with every Pauli term without inferring a physical sector."""
    symmetric_qubits: list[int] = []
    for qubit_index in range(qubit_count):
        if all(
            all(index != qubit_index or gate in {"I", "Z"} for index, gate in term)
            for term in qubit_operator.terms
        ):
            symmetric_qubits.append(qubit_index)
    return symmetric_qubits


def taper_z2_symmetries(qubit_operator, qubit_count: int, sectors: dict) -> tuple[object, list[dict], str | None]:
    """Taper user-selected Z-only sectors after checking that they are Hamiltonian symmetries."""
    available = discover_z_only_symmetries(qubit_operator, qubit_count)
    selected: list[dict] = []
    stabilizers = []
    for raw_index, raw_sector in (sectors or {}).items():
        index = int(raw_index)
        sector = int(raw_sector)
        if index not in available:
            raise ValueError(f"量子比特 {index} 不是可验证的 Z2 对称性，不能裁剪。")
        if sector not in {-1, 1}:
            raise ValueError(f"量子比特 {index} 的 Z2 扇区必须是 -1 或 1。")
        stabilizers.append(QubitOperator(((index, "Z"),), sector))
        selected.append({"pauli_string": f"Z{index}", "sector": sector})
    if not stabilizers:
        if available:
            return qubit_operator, [], "检测到 Z2 对称性，但未提供经确认的本征扇区，因此未执行裁剪。"
        return qubit_operator, [], "未检测到可安全裁剪的单量子比特 Z2 对称性。"
    return taper_off_qubits(qubit_operator, stabilizers), selected, None


def map_fermionic_hamiltonian(request: dict) -> dict:
    """Map a real integral artifact to Pauli terms and optionally taper verified user sectors."""
    if "spin_orbital_one_body_integrals" in request:
        one_body = np.asarray(request["spin_orbital_one_body_integrals"], dtype=float)
        two_body = np.asarray(request["spin_orbital_two_body_integrals"], dtype=float)
        spin_orbital_count = one_body.shape[0]
        fermion_operator = FermionOperator((), request["core_energy_hartree"])
        for p in range(spin_orbital_count):
            for q in range(spin_orbital_count):
                if abs(one_body[p, q]) > 1e-12:
                    fermion_operator += FermionOperator(((p, 1), (q, 0)), float(one_body[p, q]))
        for p in range(spin_orbital_count):
            for q in range(spin_orbital_count):
                for r in range(spin_orbital_count):
                    for s in range(spin_orbital_count):
                        coefficient = 0.5 * float(two_body[p, s, q, r])
                        if abs(coefficient) > 1e-12:
                            fermion_operator += FermionOperator(((p, 1), (q, 1), (r, 0), (s, 0)), coefficient)
    else:
        one_body = np.asarray(request["one_body_integrals"], dtype=float)
        two_body = np.asarray(request["two_body_integrals"], dtype=float)
        fermion_operator = FermionOperator((), request["core_energy_hartree"])
        orbital_count = one_body.shape[0]
        for p in range(orbital_count):
            for q in range(orbital_count):
                for spin in range(2):
                    fermion_operator += FermionOperator(
                        ((int(2 * p + spin), 1), (int(2 * q + spin), 0)),
                        float(one_body[p, q]),
                    )
        for p in range(orbital_count):
            for q in range(orbital_count):
                for r in range(orbital_count):
                    for s in range(orbital_count):
                        # PySCF emits chemist integrals (pq|rs); the normal-ordered
                        # operator below requires the (ps|qr) index arrangement.
                        coefficient = 0.5 * float(two_body[p, s, q, r])
                        if coefficient:
                            for first_spin in range(2):
                                for second_spin in range(2):
                                    fermion_operator += FermionOperator(
                                        (
                                            (int(2 * p + first_spin), 1),
                                            (int(2 * q + second_spin), 1),
                                            (int(2 * r + second_spin), 0),
                                            (int(2 * s + first_spin), 0),
                                        ),
                                        coefficient,
                                    )
    spin_orbital_count = one_body.shape[0] if "spin_orbital_one_body_integrals" in request else orbital_count * 2
    mapping_method = request.get("mapping_method", "parity")
    fallback_reason = None
    try:
        qubit_operator = (
            binary_code_transform(fermion_operator, parity_code(int(spin_orbital_count)))
            if mapping_method == "parity"
            else jordan_wigner(fermion_operator)
        )
    except Exception as exc:
        qubit_operator = jordan_wigner(fermion_operator)
        mapping_method = "jordan_wigner"
        fallback_reason = str(exc)

    qubit_count_before_tapering = spin_orbital_count
    available_z2_symmetries = discover_z_only_symmetries(qubit_operator, qubit_count_before_tapering)
    tapering_applied = False
    tapered_symmetries: list[dict] = []
    tapering_reason = "用户未请求 Z2 裁剪。"
    if request.get("enable_z2_tapering", False):
        qubit_operator, tapered_symmetries, tapering_reason = taper_z2_symmetries(
            qubit_operator,
            qubit_count_before_tapering,
            request.get("z2_tapering_sectors") or {},
        )
        tapering_applied = bool(tapered_symmetries)
    cutoff = float(request.get("coefficient_cutoff", 1e-6))
    terms, truncation_error_estimate = serialize_pauli_terms(qubit_operator, cutoff)
    return {
        "mapping_method": mapping_method,
        "fallback_reason": fallback_reason,
        "qubit_count": qubit_count_before_tapering - len(tapered_symmetries),
        "qubit_count_before_tapering": qubit_count_before_tapering,
        "pauli_terms": terms,
        "truncation_error_estimate": truncation_error_estimate,
        "z2_tapering_applied": tapering_applied,
        "tapered_symmetries": tapered_symmetries,
        "available_z2_symmetries": [f"Z{index}" for index in available_z2_symmetries],
        "tapering_reason": tapering_reason,
    }


def build_active_space_candidates(
    orbital_energies: list[float],
    occupancies: list[float],
    orbital_details: list[dict],
    is_open_shell: bool,
) -> list[dict]:
    orbital_count = len(orbital_energies)
    occupied_indices = [index for index, occupancy in enumerate(occupancies) if occupancy > 0.1]
    singly_occupied_indices = [index for index, occupancy in enumerate(occupancies) if 0.1 < occupancy < 1.9]
    frontier_index = singly_occupied_indices[len(singly_occupied_indices) // 2] if is_open_shell and singly_occupied_indices else occupied_indices[-1]
    minimum_active_orbitals = len(singly_occupied_indices) if is_open_shell else 2
    candidates: list[dict] = []
    for active_orbitals in (2, 4, 6, 8):
        if active_orbitals < minimum_active_orbitals or active_orbitals > orbital_count or active_orbitals > MAX_SPATIAL_ORBITALS:
            continue
        if is_open_shell and singly_occupied_indices:
            start = min(
                max(0, max(singly_occupied_indices) - active_orbitals + 1),
                min(singly_occupied_indices),
            )
        else:
            start = max(0, min(frontier_index - active_orbitals // 2 + 1, orbital_count - active_orbitals))
        indices = list(range(start, start + active_orbitals))
        active_electrons = int(round(sum(occupancies[index] for index in indices)))
        selected_details = [orbital_details[index] for index in indices]
        selected_types = sorted({detail["orbital_type"] for detail in selected_details})
        candidates.append(
            {
                "active_electrons": active_electrons,
                "active_orbitals": active_orbitals,
                "orbital_indices": indices,
                "orbital_energies_hartree": [orbital_energies[index] for index in indices],
                "orbital_details": selected_details,
                "estimated_spin_orbitals": active_orbitals * 2,
                "selection_reason": f"CAS({active_electrons}, {active_orbitals})：覆盖 {'、'.join(selected_types)} 与前线轨道邻域。",
            }
        )
    return candidates


def build_orbital_details(molecule, coefficients, orbital_energies: list[float], occupancies: list[float]) -> list[dict]:
    """Describe dominant atom/AO contributions so active-space selection is auditable."""
    ao_labels = molecule.ao_labels(fmt=False)
    overlap = molecule.intor("int1e_ovlp")
    eigenvalues, eigenvectors = np.linalg.eigh(overlap)
    orthogonalization = eigenvectors @ np.diag(np.sqrt(np.clip(eigenvalues, 0.0, None))) @ eigenvectors.T
    orthogonal_coefficients = orthogonalization @ coefficients
    details: list[dict] = []
    for orbital_index, energy in enumerate(orbital_energies):
        weights_by_atom: dict[int, float] = {}
        weights_by_ao: dict[tuple[int, str], float] = {}
        for ao_index, coefficient in enumerate(orthogonal_coefficients[:, orbital_index]):
            atom_index, _, atomic_orbital, _ = ao_labels[ao_index]
            weight = float(coefficient * coefficient)
            weights_by_atom[atom_index] = weights_by_atom.get(atom_index, 0.0) + weight
            key = (atom_index, atomic_orbital)
            weights_by_ao[key] = weights_by_ao.get(key, 0.0) + weight
        dominant_atom_index = max(weights_by_atom, key=weights_by_atom.get)
        dominant_ao = max(weights_by_ao, key=weights_by_ao.get)[1]
        dominant_element = molecule.atom_symbol(dominant_atom_index)
        if dominant_element in {"Fe", "Co", "Ni", "Mn", "Mo", "V"} and "d" in dominant_ao:
            orbital_type = "metal_d_orbital"
        elif dominant_element in {"N", "S", "O"} and "p" in dominant_ao:
            orbital_type = "ligand_p_orbital"
        else:
            orbital_type = "frontier_orbital"
        details.append(
            {
                "orbital_index": orbital_index,
                "energy_hartree": energy,
                "occupation": float(occupancies[orbital_index]),
                "dominant_atom_index": dominant_atom_index,
                "dominant_element": dominant_element,
                "dominant_atomic_orbital": dominant_ao,
                "dominant_contribution": float(weights_by_atom[dominant_atom_index]),
                "orbital_type": orbital_type,
            }
        )
    return details


def _angular_momentum_label(atomic_orbital: str) -> str:
    """Normalize PySCF AO labels for a chemically readable projection report."""
    match = re.search(r"[spdfgh]", atomic_orbital.lower())
    return match.group(0) if match else "other"


def _lowdin_coefficients(molecule, coefficients: np.ndarray) -> np.ndarray:
    """Express MO coefficients in the symmetric Lowdin orthogonalized AO basis."""
    overlap = molecule.intor("int1e_ovlp")
    eigenvalues, eigenvectors = np.linalg.eigh(overlap)
    overlap_square_root = eigenvectors @ np.diag(np.sqrt(np.clip(eigenvalues, 0.0, None))) @ eigenvectors.T
    return overlap_square_root @ coefficients


def _serialize_projection_bucket(weights: dict, key_names: tuple[str, ...]) -> list[dict]:
    """Convert tuple-keyed AO weights to stable JSON records."""
    return [
        {**dict(zip(key_names, key)), "weight": float(weight)}
        for key, weight in sorted(weights.items())
    ]


def _analyze_spin_orbitals(
    molecule,
    atomic_sites: list[dict],
    coefficients: np.ndarray,
    orbital_energies: np.ndarray,
    occupations: np.ndarray,
    orbital_indices: list[int],
    spin_channel: str,
) -> list[dict]:
    """Return complete Lowdin AO projections for the requested canonical orbitals."""
    if coefficients.ndim != 2:
        raise ValueError("Checkpoint MO coefficients must be a two-dimensional AO-by-MO array.")
    orbital_count = coefficients.shape[1]
    if any(index < 0 or index >= orbital_count for index in orbital_indices):
        raise ValueError("Requested orbital index is outside the checkpoint orbital range.")

    ao_labels = molecule.ao_labels(fmt=False)
    lowdin_coefficients = _lowdin_coefficients(molecule, coefficients)
    source_indices = {
        local_index: site.get("source_original_index")
        for local_index, site in enumerate(atomic_sites)
    }
    results: list[dict] = []
    for orbital_index in orbital_indices:
        weights_by_atom: dict[tuple[int, str], float] = {}
        weights_by_element_l: dict[tuple[str, str], float] = {}
        weights_by_atom_l: dict[tuple[int, str, str], float] = {}
        ao_projection: list[dict] = []
        for ao_index, coefficient in enumerate(lowdin_coefficients[:, orbital_index]):
            atom_index, element, atomic_orbital, component = ao_labels[ao_index]
            angular_momentum = _angular_momentum_label(str(atomic_orbital))
            weight = float(abs(coefficient) ** 2)
            weights_by_atom[(int(atom_index), str(element))] = weights_by_atom.get((int(atom_index), str(element)), 0.0) + weight
            weights_by_element_l[(str(element), angular_momentum)] = (
                weights_by_element_l.get((str(element), angular_momentum), 0.0) + weight
            )
            weights_by_atom_l[(int(atom_index), str(element), angular_momentum)] = (
                weights_by_atom_l.get((int(atom_index), str(element), angular_momentum), 0.0) + weight
            )
            ao_projection.append(
                {
                    "ao_index": ao_index,
                    "atom_index": int(atom_index),
                    "source_original_index": source_indices.get(int(atom_index)),
                    "element": str(element),
                    "atomic_orbital": str(atomic_orbital),
                    "component": str(component),
                    "angular_momentum": angular_momentum,
                    "weight": weight,
                }
            )
        results.append(
            {
                "orbital_index": orbital_index,
                "spin_channel": spin_channel,
                "energy_hartree": float(orbital_energies[orbital_index]),
                "occupation": float(occupations[orbital_index]),
                "orbital_class": "occupied" if occupations[orbital_index] > 1e-7 else "virtual",
                "ao_projection": ao_projection,
                "projection_by_atom": _serialize_projection_bucket(weights_by_atom, ("atom_index", "element")),
                "projection_by_atom_angular_momentum": _serialize_projection_bucket(
                    weights_by_atom_l,
                    ("atom_index", "element", "angular_momentum"),
                ),
                "projection_by_element_angular_momentum": _serialize_projection_bucket(
                    weights_by_element_l,
                    ("element", "angular_momentum"),
                ),
            }
        )
    return results


def analyze_orbital_projections_from_checkpoint(molecule, request: dict, checkpoint_validation: dict) -> dict:
    """Read a validated SCF checkpoint without running SCF and emit complete AO projections."""
    checkpoint_path = request.get("scf_options", {}).get("checkpoint_validation_source_path")
    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        raise ValueError("A readable checkpoint_validation_source_path is required for orbital projection analysis.")

    orbital_indices = [int(index) for index in request.get("orbital_indices", [])]
    if not orbital_indices:
        raise ValueError("At least one orbital index is required for orbital projection analysis.")
    mo_coefficients = np.asarray(chkfile.load(checkpoint_path, "scf/mo_coeff"))
    mo_energies = np.asarray(chkfile.load(checkpoint_path, "scf/mo_energy"))
    mo_occupations = np.asarray(chkfile.load(checkpoint_path, "scf/mo_occ"))
    if mo_coefficients.ndim == 2:
        mo_coefficients = np.asarray([mo_coefficients, mo_coefficients])
        mo_energies = np.asarray([mo_energies, mo_energies])
        mo_occupations = np.asarray([mo_occupations / 2.0, mo_occupations / 2.0])
    if mo_coefficients.ndim != 3 or mo_energies.ndim != 2 or mo_occupations.ndim != 2:
        raise ValueError("Checkpoint does not contain a supported UHF/RHF molecular-orbital representation.")

    combined_occupations = mo_occupations[0] + mo_occupations[1]
    combined_energies = (mo_energies[0] + mo_energies[1]) / 2.0
    occupied_indices = np.flatnonzero(combined_occupations > 1e-7)
    if not len(occupied_indices):
        raise ValueError("Checkpoint has no occupied molecular orbitals.")
    homo_index = int(occupied_indices[-1])
    virtual_indices = np.flatnonzero((np.arange(len(combined_occupations)) > homo_index) & (combined_occupations <= 1e-7))
    if not len(virtual_indices):
        raise ValueError("Checkpoint has no virtual molecular orbitals after the HOMO.")
    lumo_index = int(virtual_indices[0])

    return {
        "status": "completed",
        "operation": "orbital_projection_analysis",
        "analysis_mode": "checkpoint_read_only_no_scf_kernel",
        "checkpoint_validation": checkpoint_validation,
        "orbital_count": int(mo_coefficients.shape[-1]),
        "electron_count": int(molecule.nelectron),
        "homo_index": homo_index,
        "lumo_index": lumo_index,
        "homo_energy_hartree": float(combined_energies[homo_index]),
        "lumo_energy_hartree": float(combined_energies[lumo_index]),
        "homo_lumo_gap_hartree": float(combined_energies[lumo_index] - combined_energies[homo_index]),
        "spatial_orbitals": [
            {
                "orbital_index": index,
                "energy_hartree": float(combined_energies[index]),
                "alpha_energy_hartree": float(mo_energies[0, index]),
                "beta_energy_hartree": float(mo_energies[1, index]),
                "alpha_beta_energy_difference_hartree": float(mo_energies[0, index] - mo_energies[1, index]),
                "occupation": float(combined_occupations[index]),
                "orbital_class": "occupied" if combined_occupations[index] > 1e-7 else "virtual",
            }
            for index in orbital_indices
        ],
        "spin_channel_projections": {
            "alpha": _analyze_spin_orbitals(
                molecule,
                request["atomic_sites"],
                mo_coefficients[0],
                mo_energies[0],
                mo_occupations[0],
                orbital_indices,
                "alpha",
            ),
            "beta": _analyze_spin_orbitals(
                molecule,
                request["atomic_sites"],
                mo_coefficients[1],
                mo_energies[1],
                mo_occupations[1],
                orbital_indices,
                "beta",
            ),
        },
    }


def _array_sha256(values) -> str:
    """Hash numerical integral content with explicit dtype and shape metadata."""
    array = np.ascontiguousarray(np.asarray(values, dtype=np.float64))
    digest = sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def build_checkpoint_active_space_benchmark(molecule, request: dict, checkpoint_validation: dict) -> dict:
    """Build a UHF spin-orbital CAS Hamiltonian and FCI reference without rerunning SCF."""
    options = request.get("scf_options", {})
    checkpoint_path = options.get("checkpoint_validation_source_path")
    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        raise ValueError("A validated checkpoint_validation_source_path is required for checkpoint Hamiltonian construction.")
    active_indices = [int(index) for index in request.get("orbital_indices", [])]
    active_electrons = int(request["active_electrons"])
    if not active_indices or active_electrons <= 0:
        raise ValueError("Active orbital indices and a positive active electron count are required.")
    if len(active_indices) > MAX_CLASSICAL_REFERENCE_ORBITALS:
        raise ValueError("Requested active space exceeds the bounded FCI orbital limit.")
    if active_electrons % 2:
        raise ValueError("Singlet UHF active-space benchmark requires an even active electron count.")

    mo_coefficients = np.asarray(chkfile.load(checkpoint_path, "scf/mo_coeff"))
    mo_energies = np.asarray(chkfile.load(checkpoint_path, "scf/mo_energy"))
    mo_occupations = np.asarray(chkfile.load(checkpoint_path, "scf/mo_occ"))
    if mo_coefficients.ndim != 3 or mo_coefficients.shape[0] != 2:
        raise ValueError("Benchmark requires an unrestricted checkpoint with alpha and beta coefficients.")
    if max(active_indices) >= mo_coefficients.shape[-1] or min(active_indices) < 0:
        raise ValueError("Active orbital index is outside the checkpoint orbital range.")

    # The UHF alpha/beta coefficients are retained as separate spin-orbital bases.
    # This avoids silently averaging non-identical orbitals before the FCI/Pauli comparison.
    calculation = scf.UHF(molecule)
    calculation.mo_coeff = mo_coefficients
    calculation.mo_energy = mo_energies
    calculation.mo_occ = mo_occupations
    active_integrals = build_open_shell_hamiltonian(molecule, calculation, active_indices)
    alpha_electrons = beta_electrons = active_electrons // 2
    fci_energy, _ = fci.direct_uhf.kernel(
        tuple(np.asarray(values) for values in active_integrals["uhf_one_body_integrals"]),
        tuple(np.asarray(values) for values in active_integrals["uhf_two_body_integrals"]),
        len(active_indices),
        (alpha_electrons, beta_electrons),
        ecore=active_integrals["core_energy_hartree"],
    )
    one_body = active_integrals["spin_orbital_one_body_integrals"]
    two_body = active_integrals["spin_orbital_two_body_integrals"]
    core_indices = list(range(min(active_indices)))
    return {
        "status": "completed",
        "operation": "checkpoint_active_space_benchmark",
        "method_name": "PySCF_UHF_checkpoint_active_space",
        "basis_set": request.get("basis_set", "sto-3g"),
        "checkpoint_validation": checkpoint_validation,
        "checkpoint_sha256": _file_sha256(checkpoint_path),
        "alpha_beta_coefficient_treatment": "separate_checkpoint_uhf_spin_orbital_bases_no_averaging",
        "active_orbital_indices": active_indices,
        "core_orbital_indices": core_indices,
        "active_electrons": active_electrons,
        "alpha_electrons": alpha_electrons,
        "beta_electrons": beta_electrons,
        "active_spatial_orbitals": len(active_indices),
        "spin_orbital_count": active_integrals["spin_orbital_count"],
        "nuclear_repulsion_hartree": float(molecule.energy_nuc()),
        "core_energy_hartree": active_integrals["core_energy_hartree"],
        "spin_orbital_one_body_integrals": one_body,
        "spin_orbital_two_body_integrals": two_body,
        "uhf_one_body_integrals": active_integrals["uhf_one_body_integrals"],
        "uhf_two_body_integrals": active_integrals["uhf_two_body_integrals"],
        "one_body_integrals_sha256": _array_sha256(one_body),
        "two_body_integrals_sha256": _array_sha256(two_body),
        "classical_fci": {
            "method": "PySCF_direct_uhf_FCI_same_spin_orbital_hamiltonian",
            "energy_hartree": float(fci_energy),
            "constant_energy_offset_hartree": active_integrals["core_energy_hartree"],
            "electron_sector": {"alpha_electrons": alpha_electrons, "beta_electrons": beta_electrons},
        },
        "software": {"python_version": platform.python_version(), "pyscf_version": pyscf.__version__},
    }


def transform_eri(molecule, first, second, third, fourth) -> np.ndarray:
    """Transform a compact AO integral block while preserving PySCF's chemist notation."""
    shape = (first.shape[1], second.shape[1], third.shape[1], fourth.shape[1])
    return ao2mo.general(molecule, (first, second, third, fourth), compact=False).reshape(shape)


def build_open_shell_hamiltonian(molecule, calculation, active_indices: list[int]) -> dict:
    """Freeze only doubly occupied UHF orbitals and emit a spin-orbital active Hamiltonian."""
    alpha_coefficients, beta_coefficients = calculation.mo_coeff
    alpha_occupations, beta_occupations = calculation.mo_occ
    core_indices = [
        index
        for index in range(min(active_indices))
        if alpha_occupations[index] > 0.9 and beta_occupations[index] > 0.9
    ]
    active_alpha = alpha_coefficients[:, active_indices]
    active_beta = beta_coefficients[:, active_indices]
    core_alpha = alpha_coefficients[:, core_indices]
    core_beta = beta_coefficients[:, core_indices]
    active_coefficients = (active_alpha, active_beta)
    core_coefficients = (core_alpha, core_beta)
    active_orbital_count = len(active_indices)
    spin_orbital_count = active_orbital_count * 2
    one_body = np.zeros((spin_orbital_count, spin_orbital_count))
    two_body = np.zeros((spin_orbital_count,) * 4)
    hcore = calculation.get_hcore()
    active_hcore = tuple(coefficients.T @ hcore @ coefficients for coefficients in active_coefficients)
    core_hcore = tuple(coefficients.T @ hcore @ coefficients for coefficients in core_coefficients)
    coulomb_blocks = {}
    exchange_blocks = {}
    active_blocks = {}
    for first_spin in range(2):
        for second_spin in range(2):
            coulomb_blocks[first_spin, second_spin] = transform_eri(
                molecule,
                active_coefficients[first_spin],
                active_coefficients[first_spin],
                core_coefficients[second_spin],
                core_coefficients[second_spin],
            )
            active_blocks[first_spin, second_spin] = transform_eri(
                molecule,
                active_coefficients[first_spin],
                active_coefficients[first_spin],
                active_coefficients[second_spin],
                active_coefficients[second_spin],
            )
        exchange_blocks[first_spin] = transform_eri(
            molecule,
            active_coefficients[first_spin],
            core_coefficients[first_spin],
            core_coefficients[first_spin],
            active_coefficients[first_spin],
        )
    core_energy = molecule.energy_nuc()
    for spin in range(2):
        core_energy += float(np.trace(core_hcore[spin]))
        for other_spin in range(2):
            coulomb = transform_eri(
                molecule,
                core_coefficients[spin],
                core_coefficients[spin],
                core_coefficients[other_spin],
                core_coefficients[other_spin],
            )
            core_energy += 0.5 * float(np.einsum("iijj->", coulomb))
            if spin == other_spin:
                exchange = transform_eri(
                    molecule,
                    core_coefficients[spin],
                    core_coefficients[spin],
                    core_coefficients[spin],
                    core_coefficients[spin],
                )
                core_energy -= 0.5 * float(np.einsum("ijji->", exchange))
    for spin in range(2):
        for p in range(active_orbital_count):
            for q in range(active_orbital_count):
                value = active_hcore[spin][p, q]
                for core_spin in range(2):
                    value += np.trace(coulomb_blocks[spin, core_spin][p, q])
                value -= np.trace(exchange_blocks[spin][p, :, :, q])
                one_body[2 * p + spin, 2 * q + spin] = value
    for first_spin in range(2):
        for second_spin in range(2):
            block = active_blocks[first_spin, second_spin]
            for p in range(active_orbital_count):
                for s in range(active_orbital_count):
                    for q in range(active_orbital_count):
                        for r in range(active_orbital_count):
                            two_body[2 * p + first_spin, 2 * s + first_spin, 2 * q + second_spin, 2 * r + second_spin] = block[p, s, q, r]
    return {
        "core_energy_hartree": float(core_energy),
        "spin_orbital_one_body_integrals": one_body.tolist(),
        "spin_orbital_two_body_integrals": two_body.tolist(),
        "uhf_one_body_integrals": [
            one_body[0::2, 0::2].tolist(),
            one_body[1::2, 1::2].tolist(),
        ],
        "uhf_two_body_integrals": [
            active_blocks[0, 0].tolist(),
            active_blocks[0, 1].tolist(),
            active_blocks[1, 1].tolist(),
        ],
        "spin_orbital_count": spin_orbital_count,
    }


def _as_float(value) -> float | None:
    """Convert PySCF callback scalars without serializing arrays into artifacts."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_progress(progress_path: str | None, record: dict) -> None:
    """Flush every SCF iteration so a hard container timeout still has diagnostics."""
    if not progress_path:
        return
    with open(progress_path, "a", encoding="utf-8") as progress_file:
        progress_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        progress_file.flush()
        os.fsync(progress_file.fileno())


def _runtime_metadata(started_wall_time: float, started_cpu_time: float) -> dict:
    """Capture runtime details needed to reproduce and diagnose a bounded SCF job."""
    maximum_rss_mb = None
    try:
        import resource

        maximum_rss_mb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
    except (ImportError, AttributeError):
        pass
    return {
        "python_version": platform.python_version(),
        "pyscf_version": pyscf.__version__,
        "wall_time_seconds": time.monotonic() - started_wall_time,
        "process_cpu_time_seconds": time.process_time() - started_cpu_time,
        "process_max_rss_mb": maximum_rss_mb,
        "process_max_rss_sampled_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _df_artifact_metadata(scf_options: dict) -> dict:
    """Describe the disk-backed DF tensor without loading it back into memory."""
    cderi_path = scf_options.get("df_cderi_load_path") or scf_options.get("df_cderi_path")
    if not cderi_path:
        return {
            "df_cderi_path": None,
            "df_cderi_size_bytes": None,
            "df_cderi_available": False,
            "df_cderi_access": None,
        }
    return {
        "df_cderi_path": cderi_path,
        "df_cderi_size_bytes": os.path.getsize(cderi_path) if os.path.isfile(cderi_path) else None,
        "df_cderi_available": os.path.isfile(cderi_path),
        "df_cderi_access": "read_only_reuse" if scf_options.get("df_cderi_load_path") else "generated",
    }


def _density_artifact_metadata(path: str | None) -> dict:
    return {
        "density_path": path,
        "density_available": bool(path and os.path.isfile(path)),
        "density_size_bytes": os.path.getsize(path) if path and os.path.isfile(path) else None,
        "density_format": "numpy_npz_alpha_beta" if path else None,
    }


def _callable_name(value) -> str | None:
    return getattr(value, "__name__", None) if value is not None else None


def run_uks_density_preconditioner(
    molecule,
    request: dict,
    checkpoint_validation: dict | None,
    started_wall_time: float,
    started_cpu_time: float,
) -> dict:
    """Run UKS/PBE only to generate an independently reviewable alpha/beta density."""
    options = request.get("scf_options", {})
    progress_path = options.get("progress_path")
    source_checkpoint_path = options["initial_density_checkpoint_path"]
    density_path = options.get("density_output_path")
    initial_guess = scf.UHF(molecule)
    initial_guess.chkfile = source_checkpoint_path
    initial_density = initial_guess.get_init_guess(key="chkfile")

    calculation = dft.UKS(molecule).density_fit(auxbasis=options.get("density_fitting_auxbasis"))
    cderi_load_path = options.get("df_cderi_load_path")
    if cderi_load_path:
        calculation.with_df._cderi = cderi_load_path
    calculation.xc = options.get("xc", "PBE")
    calculation.grids.level = int(options.get("grid_level", 1))
    calculation.max_memory = int(options.get("max_memory_mb", 1024))
    calculation.max_cycle = int(options.get("max_cycle", 100))
    calculation.conv_tol = float(options.get("conv_tol", 1e-7))
    calculation.conv_tol_grad = float(options.get("conv_tol_grad", 1e-4))
    calculation.chkfile = options.get("checkpoint_path")
    calculation.verbose = 0
    cycle_log: list[dict] = []

    def stop(code: str, message: str, cycle: int | None, details: dict | None = None) -> None:
        event = {"event": "preconditioner_guardrail_stop", "reason": code, "cycle": cycle}
        if details:
            event.update(details)
        _append_progress(progress_path, event)
        raise PreconditionerGuardrailStop(code, message)

    def record_cycle(values) -> None:
        cycle_index = values.get("cycle")
        energy = _as_float(values.get("e_tot"))
        gradient = _as_float(values.get("norm_gorb"))
        density_residual = _as_float(values.get("norm_ddm"))
        delta_energy = _as_float(values.get("de"))
        record = {
            "event": "iteration",
            "method": "UKS/PBE",
            "cycle": cycle_index,
            "iteration_kind": "uks_preconditioner_cycle",
            "energy_hartree": energy,
            "delta_energy_hartree": delta_energy,
            "orbital_gradient_norm": gradient,
            "density_change_norm": density_residual,
            "preconditioner_only": True,
        }
        cycle_log.append(record)
        _append_progress(progress_path, record)
        finite_values = [value for value in (energy, gradient, density_residual) if value is not None]
        if any(not np.isfinite(value) for value in finite_values):
            stop("stopped_for_nonfinite_values", "UKS produced non-finite diagnostic values.", cycle_index)
        if len(cycle_log) >= 2:
            previous = cycle_log[-2]
            multiplier = float(options.get("rapid_residual_growth_multiplier", 10.0))
            rapidly_growing = {
                "orbital_gradient": has_rapid_residual_amplification(
                    previous.get("orbital_gradient_norm"), gradient, multiplier
                ),
                "density_residual": has_rapid_residual_amplification(
                    previous.get("density_change_norm"), density_residual, multiplier
                ),
            }
            if any(rapidly_growing.values()):
                stop(
                    "stopped_for_rapid_residual_amplification",
                    "UKS residual increased by at least the approved one-cycle multiplier.",
                    cycle_index,
                    {"rapid_growth_multiplier": multiplier, "triggered_metrics": rapidly_growing},
                )
        gradients = [item["orbital_gradient_norm"] for item in cycle_log if item["orbital_gradient_norm"] is not None]
        if has_sustained_gradient_oscillation(
            gradients,
            minimum_completed_cycles=int(options.get("oscillation_minimum_completed_cycles", 12)),
            window_size=int(options.get("oscillation_window_size", 6)),
            minimum_direction_reversals=int(options.get("oscillation_minimum_direction_reversals", 3)),
            minimum_gradient=float(options.get("oscillation_minimum_gradient", 1e-3)),
        ):
            stop(
                "stopped_for_sustained_gradient_oscillation",
                "UKS met the approved sustained orbital-gradient oscillation rule.",
                cycle_index,
                {"gradient_window": gradients[-int(options.get("oscillation_window_size", 6)) :]},
            )

    calculation.callback = record_cycle
    grid_configuration = {
        "level": calculation.grids.level,
        "atom_grid": calculation.grids.atom_grid,
        "prune": _callable_name(calculation.grids.prune),
        "radi_method": _callable_name(calculation.grids.radi_method),
        "becke_scheme": _callable_name(calculation.grids.becke_scheme),
    }
    _append_progress(
        progress_path,
        {
            "event": "uks_preconditioner_start",
            "xc": calculation.xc,
            "grid_configuration": grid_configuration,
            "max_cycle": calculation.max_cycle,
            "initial_density_source": source_checkpoint_path,
        },
    )
    stop_code = None
    error_message = None
    try:
        calculation.kernel(dm0=initial_density)
    except PreconditionerGuardrailStop as exc:
        stop_code = exc.code
        error_message = str(exc)
    except Exception as exc:
        stop_code = "stopped_for_uks_runtime_error"
        error_message = str(exc)
        _append_progress(progress_path, {"event": "uks_preconditioner_error", "error": str(exc)})

    common = {
        "preconditioner_only": True,
        "downstream_consumable": False,
        "scientific_validation": False,
        "method_name": f"UKS/PBE/{request.get('basis_set', 'def2-svp')}",
        "basis_set": request.get("basis_set", "def2-svp"),
        "xc": calculation.xc,
        "converged": bool(calculation.converged),
        "stop_code": stop_code,
        "message": error_message,
        "cycles": cycle_log,
        "runtime_metadata": _runtime_metadata(started_wall_time, started_cpu_time),
        "scf_configuration": options,
        "grid_configuration": {
            **grid_configuration,
            "grid_point_count": len(calculation.grids.weights) if calculation.grids.weights is not None else None,
        },
        "density_fitting_auxbasis": calculation.with_df.auxbasis or "auto",
        "df_artifact": _df_artifact_metadata(options),
        "density_artifact": _density_artifact_metadata(density_path),
        "checkpoint_validation": checkpoint_validation,
    }
    if not calculation.converged:
        return {"status": stop_code or "uks_not_converged", **common}

    density = calculation.make_rdm1()
    np.savez(density_path, alpha=density[0], beta=density[1])
    observed_spin_square = float(calculation.spin_square()[0])
    alpha_energies, beta_energies = calculation.mo_energy
    alpha_occupations, beta_occupations = calculation.mo_occ
    return {
        "status": "uks_preconditioner_converged_pending_review",
        **common,
        "preconditioner_diagnostics": {
            "uks_energy_hartree": float(calculation.e_tot),
            "spin_square": observed_spin_square,
            "expected_spin_square": 2.0,
            "spin_contamination_delta": abs(observed_spin_square - 2.0),
            "alpha_orbital_energies_hartree": [float(value) for value in alpha_energies],
            "beta_orbital_energies_hartree": [float(value) for value in beta_energies],
            "alpha_orbital_occupations": [float(value) for value in alpha_occupations],
            "beta_orbital_occupations": [float(value) for value in beta_occupations],
        },
        "density_artifact": _density_artifact_metadata(density_path),
    }


def run_scf(
    molecule,
    spin_multiplicity: int,
    requested_methods: list[str] | None = None,
    max_attempts: int = 3,
    scf_options: dict | None = None,
) -> tuple[object | None, list[dict]]:
    attempts: list[dict] = []
    options = scf_options or {}
    method_lookup = {"RHF": scf.RHF, "UHF": scf.UHF, "ROHF": scf.ROHF}
    default_methods = ["RHF"] if spin_multiplicity == 1 else ["UHF", "ROHF"]
    selected_methods = requested_methods or default_methods
    if spin_multiplicity != 1 and "RHF" in selected_methods:
        raise ValueError("开壳层候选不能使用 RHF。")
    method_classes = [method_lookup[name] for name in selected_methods]
    strategies = options.get("strategies") or (
        {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False},
        {"level_shift": 0.5, "initial_guess": "atom", "damping": 0.2, "use_newton": True},
        {"level_shift": 0.0, "initial_guess": "minao", "damping": 0.0, "use_newton": False},
    )
    checkpoint_path = options.get("checkpoint_path")
    progress_path = options.get("progress_path")
    for method_class in method_classes:
        for strategy in strategies[:max_attempts]:
            level_shift = float(strategy["level_shift"])
            initial_guess = strategy["initial_guess"]
            damping = float(strategy["damping"])
            use_newton = bool(strategy["use_newton"])
            initial_calculation = method_class(molecule)
            if options.get("density_fitting", False):
                initial_calculation = initial_calculation.density_fit(auxbasis=options.get("density_fitting_auxbasis"))
                cderi_path = options.get("df_cderi_path")
                if cderi_path:
                    initial_calculation.with_df._cderi_to_save = cderi_path
            if options.get("max_memory_mb") is not None:
                initial_calculation.max_memory = int(options["max_memory_mb"])
            if checkpoint_path:
                initial_calculation.chkfile = checkpoint_path
            calculation = scf.newton(initial_calculation) if use_newton else initial_calculation
            if options.get("max_memory_mb") is not None:
                calculation.max_memory = int(options["max_memory_mb"])
            calculation.max_cycle = int(options.get("max_cycle", 200))
            calculation.diis_space = int(options.get("diis_space", 12))
            calculation.conv_tol = float(options.get("conv_tol", 1e-8))
            calculation.conv_tol_grad = float(options.get("conv_tol_grad", 1e-5))
            calculation.level_shift = level_shift
            calculation.damp = damping
            cycle_log: list[dict] = []
            previous_density = None

            def record_cycle(values):
                nonlocal previous_density
                raw_cycle = values.get("cycle")
                if raw_cycle is None:
                    raw_cycle = values.get("imacro")
                if cycle_log and raw_cycle is not None and cycle_log[-1].get("cycle") == raw_cycle:
                    return
                density = values.get("dm")
                density_change = _as_float(values.get("norm_ddm"))
                if density_change is None and density is not None and previous_density is not None:
                    density_change = float(np.linalg.norm(np.asarray(density) - previous_density))
                if density is not None:
                    previous_density = np.asarray(density).copy()
                energy = _as_float(values.get("e_tot"))
                delta_energy = _as_float(values.get("de"))
                if delta_energy is None and values.get("last_hf_e") is not None and energy is not None:
                    delta_energy = energy - float(values["last_hf_e"])
                cycle = {
                    "event": "iteration",
                    "method": method_class.__name__,
                    "cycle": raw_cycle,
                    "iteration_kind": "newton_macro_cycle" if use_newton else "scf_cycle",
                    "orbital_gradient_norm": _as_float(values.get("norm_gorb")),
                    "density_change_norm": density_change,
                }
                if options.get("record_iteration_energy", True):
                    cycle["energy_hartree"] = energy
                    cycle["delta_energy_hartree"] = delta_energy
                cycle_log.append(cycle)
                _append_progress(progress_path, cycle)
                numerical_values = [
                    value
                    for value in (energy, cycle["orbital_gradient_norm"], density_change)
                    if value is not None
                ]
                if use_newton and any(not np.isfinite(value) for value in numerical_values):
                    guardrail = {"event": "scf_guardrail_stop", "reason": "numerical_divergence", "cycle": raw_cycle}
                    _append_progress(progress_path, guardrail)
                    raise RuntimeError("Newton/AH stopped after non-finite numerical values were detected.")
                stagnation_window = int(options.get("macro_gradient_stagnation_window", 0))
                gradient_history = [
                    item["orbital_gradient_norm"]
                    for item in cycle_log
                    if item.get("orbital_gradient_norm") is not None
                ]
                if use_newton and stagnation_window > 1 and len(gradient_history) >= stagnation_window:
                    window = gradient_history[-stagnation_window:]
                    if window[-1] >= window[0]:
                        guardrail = {
                            "event": "scf_guardrail_stop",
                            "reason": "macro_gradient_no_overall_decrease",
                            "cycle": raw_cycle,
                            "window_size": stagnation_window,
                            "gradient_window": window,
                        }
                        _append_progress(progress_path, guardrail)
                        raise RuntimeError(
                            f"Newton/AH stopped because the orbital gradient did not decrease overall across {stagnation_window} macro cycles."
                        )

            calculation.callback = record_cycle
            calculation.verbose = 0
            restart_from_checkpoint = bool(checkpoint_path and os.path.isfile(checkpoint_path))
            guess_key = "chkfile" if restart_from_checkpoint else initial_guess
            _append_progress(
                progress_path,
                {
                    "event": "scf_kernel_start",
                    "method": method_class.__name__,
                    "density_fitting": bool(options.get("density_fitting", False)),
                    "initial_guess": guess_key,
                    "max_cycle": calculation.max_cycle,
                },
            )
            try:
                initial_density = initial_calculation.get_init_guess(key=guess_key)
                previous_density = np.asarray(initial_density).copy()
                calculation.kernel(dm0=initial_density)
            except Exception as exc:
                _append_progress(
                    progress_path,
                    {"event": "scf_kernel_error", "method": method_class.__name__, "error": str(exc)},
                )
                attempts.append(
                    {
                        "method": method_class.__name__,
                        "level_shift": level_shift,
                        "initial_guess": guess_key,
                        "damping": damping,
                        "second_order": use_newton,
                        "density_fitting": bool(options.get("density_fitting", False)),
                        "converged": False,
                        "error": str(exc),
                        "iterations": cycle_log,
                    }
                )
                continue
            _append_progress(
                progress_path,
                {
                    "event": "scf_kernel_end",
                    "method": method_class.__name__,
                    "converged": bool(calculation.converged),
                    "iteration_count": len(cycle_log),
                },
            )
            attempts.append(
                {
                    "method": method_class.__name__,
                    "level_shift": level_shift,
                    "initial_guess": guess_key,
                    "damping": damping,
                    "second_order": use_newton,
                    "density_fitting": bool(options.get("density_fitting", False)),
                    "converged": calculation.converged,
                    "iterations": cycle_log,
                }
            )
            if calculation.converged:
                return calculation, attempts
    return None, attempts


def calculate_closed_shell_fci(molecule, calculation, active_indices: list[int], active_electrons: int) -> dict:
    """Calculate a bounded active-space FCI reference from the same SCF orbitals as the Hamiltonian."""
    if len(active_indices) > MAX_CLASSICAL_REFERENCE_ORBITALS:
        return {
            "status": "not_supported",
            "method": "PySCF_FCI_active_space",
            "message": f"活性空间含 {len(active_indices)} 个空间轨道，超过经典 FCI 上限 {MAX_CLASSICAL_REFERENCE_ORBITALS}。",
        }
    if active_electrons <= 0 or active_electrons % 2:
        return {
            "status": "not_supported",
            "method": "PySCF_FCI_active_space",
            "message": "当前闭壳层 FCI 参考仅支持正偶数活性电子数。",
        }

    core_indices = list(range(min(active_indices)))
    coefficients = calculation.mo_coeff
    orbital_count = coefficients.shape[1]
    one_body = coefficients.T @ calculation.get_hcore() @ coefficients
    two_body = ao2mo.kernel(molecule, coefficients, compact=False).reshape((orbital_count,) * 4)
    active_one_body = one_body[np.ix_(active_indices, active_indices)].copy()
    for core_index in core_indices:
        active_one_body += 2 * two_body[np.ix_(active_indices, active_indices, [core_index], [core_index])][:, :, 0, 0]
        active_one_body -= two_body[np.ix_(active_indices, [core_index], [core_index], active_indices)][:, 0, 0, :]
    core_energy = molecule.energy_nuc()
    for core_index in core_indices:
        core_energy += 2 * one_body[core_index, core_index]
        for other_index in core_indices:
            core_energy += 2 * two_body[core_index, core_index, other_index, other_index] - two_body[core_index, other_index, other_index, core_index]
    active_two_body = two_body[np.ix_(active_indices, active_indices, active_indices, active_indices)]
    electron_pair = (active_electrons // 2, active_electrons // 2)
    electronic_energy, _ = fci.direct_spin1.kernel(
        active_one_body,
        active_two_body,
        len(active_indices),
        electron_pair,
        ecore=float(core_energy),
    )
    return {
        "status": "completed",
        "method": "PySCF_FCI_active_space",
        "energy_hartree": float(electronic_energy),
        "core_energy_hartree": float(core_energy),
        "active_electrons": active_electrons,
        "active_orbitals": len(active_indices),
    }


def calculate_open_shell_fci(molecule, calculation, active_indices: list[int], active_electrons: int, spin_multiplicity: int) -> dict:
    """Run UHF-FCI in a small active space without relabelling an open-shell system as closed-shell."""
    if len(active_indices) > MAX_CLASSICAL_REFERENCE_ORBITALS:
        return {
            "status": "not_supported",
            "method": "PySCF_UHF_FCI_active_space",
            "message": f"活性空间含 {len(active_indices)} 个空间轨道，超过经典 FCI 上限 {MAX_CLASSICAL_REFERENCE_ORBITALS}。",
        }
    spin_excess = spin_multiplicity - 1
    if active_electrons < spin_excess or (active_electrons + spin_excess) % 2:
        return {
            "status": "not_supported",
            "method": "PySCF_UHF_FCI_active_space",
            "message": "活性电子数与目标自旋多重度不兼容，不能构造 UHF-FCI 参考。",
        }
    active_integrals = build_open_shell_hamiltonian(molecule, calculation, active_indices)
    alpha_electrons = (active_electrons + spin_excess) // 2
    beta_electrons = active_electrons - alpha_electrons
    energy, _ = fci.direct_uhf.kernel(
        tuple(np.asarray(item) for item in active_integrals["uhf_one_body_integrals"]),
        tuple(np.asarray(item) for item in active_integrals["uhf_two_body_integrals"]),
        len(active_indices),
        (alpha_electrons, beta_electrons),
        ecore=active_integrals["core_energy_hartree"],
    )
    return {
        "status": "completed",
        "method": "PySCF_UHF_FCI_active_space",
        "energy_hartree": float(energy),
        "core_energy_hartree": active_integrals["core_energy_hartree"],
        "active_electrons": active_electrons,
        "active_orbitals": len(active_indices),
        "alpha_electrons": alpha_electrons,
        "beta_electrons": beta_electrons,
    }


def main() -> None:
    request = json.load(sys.stdin)
    started_wall_time = time.monotonic()
    started_cpu_time = time.process_time()
    if request.get("operation") == "map_hamiltonian":
        print(json.dumps(map_fermionic_hamiltonian(request)))
        return
    atom_specification = [(site["element"], site["position_angstrom"]) for site in request["atomic_sites"]]
    molecule = gto.M(
        atom=atom_specification,
        basis=request.get("basis_set", "sto-3g"),
        charge=request["total_charge"],
        spin=request["spin_multiplicity"] - 1,
        unit="Angstrom",
        verbose=0,
    )
    checkpoint_validation = validate_restart_checkpoint(request, request.get("scf_options", {}))
    if request.get("operation") == "orbital_projection_analysis":
        print(
            json.dumps(
                analyze_orbital_projections_from_checkpoint(molecule, request, checkpoint_validation),
                ensure_ascii=False,
            )
        )
        return
    if request.get("operation") == "checkpoint_active_space_benchmark":
        print(
            json.dumps(
                build_checkpoint_active_space_benchmark(molecule, request, checkpoint_validation),
                ensure_ascii=False,
            )
        )
        return
    if request.get("operation") == "density_preconditioner":
        print(
            json.dumps(
                run_uks_density_preconditioner(
                    molecule,
                    request,
                    checkpoint_validation,
                    started_wall_time,
                    started_cpu_time,
                ),
                ensure_ascii=False,
            )
        )
        return
    calculation, scf_attempts = run_scf(
        molecule,
        request["spin_multiplicity"],
        request.get("requested_methods"),
        int(request.get("max_scf_attempts", 3)),
        request.get("scf_options"),
    )
    if request.get("resource_calibration_only"):
        print(
            json.dumps(
                {
                    "status": "needs_model_review",
                    "error_code": "resource_calibration_only",
                    "message": "仅完成资源标定；未生成或披露能量、轨道、CAS 或 Hamiltonian 结果。",
                    "basis_set": request.get("basis_set", "sto-3g"),
                    "scf_attempts": scf_attempts,
                    "runtime_metadata": _runtime_metadata(started_wall_time, started_cpu_time),
                    "scf_configuration": request.get("scf_options", {}),
                    "df_artifact": _df_artifact_metadata(request.get("scf_options", {})),
                    "checkpoint_validation": checkpoint_validation,
                },
                ensure_ascii=False,
            )
        )
        return
    if calculation is None:
        print(
            json.dumps(
                {
                    "status": "needs_model_review",
                    "error_code": "scf_not_converged",
                    "message": (
                        "Newton/AH 救援未达到收敛条件或被专用护栏停止；未生成收敛能量、轨道或 <S²>。"
                        if request.get("scf_options", {}).get("newton_rescue_mode")
                        else "已尝试配置的 SCF 策略但仍未收敛；请复核几何、电荷、自旋与数值设置。"
                    ),
                    "basis_set": request.get("basis_set", "sto-3g"),
                    "scf_attempts": scf_attempts,
                    "runtime_metadata": _runtime_metadata(started_wall_time, started_cpu_time),
                    "scf_configuration": request.get("scf_options", {}),
                    "df_artifact": _df_artifact_metadata(request.get("scf_options", {})),
                    "checkpoint_validation": checkpoint_validation,
                },
                ensure_ascii=False,
            )
        )
        return
    energy = calculation.e_tot
    is_open_shell = request["spin_multiplicity"] != 1
    is_unrestricted_reference = np.asarray(calculation.mo_energy).ndim == 2
    if is_unrestricted_reference:
        alpha_energies, beta_energies = calculation.mo_energy
        alpha_occupations, beta_occupations = calculation.mo_occ
        orbital_energies = [float(value) for value in alpha_energies]
        occupancies = [float(alpha + beta) for alpha, beta in zip(alpha_occupations, beta_occupations)]
        orbital_details = build_orbital_details(molecule, calculation.mo_coeff[0], orbital_energies, occupancies)
    else:
        orbital_energies = [float(value) for value in calculation.mo_energy]
        occupancies = [float(value) for value in calculation.mo_occ]
        orbital_details = build_orbital_details(molecule, calculation.mo_coeff, orbital_energies, occupancies)
    expected_spin_square = ((request["spin_multiplicity"] - 1) / 2) * ((request["spin_multiplicity"] + 1) / 2)
    observed_spin_square = float(calculation.spin_square()[0])
    spin_contamination = abs(observed_spin_square - expected_spin_square)
    spin_contamination_threshold = request.get("spin_contamination_threshold")
    result = {
                "status": "completed",
                "method_name": f"{type(calculation).__name__}/{request.get('basis_set', 'sto-3g')}",
                "basis_set": request.get("basis_set", "sto-3g"),
                "electron_count": molecule.nelectron,
                "orbital_count": len(orbital_energies),
                "hf_total_energy_hartree": float(energy),
                "orbital_energies_hartree": orbital_energies,
                "active_space_candidates": (
                    build_active_space_candidates(orbital_energies, occupancies, orbital_details, is_open_shell)
                    if request.get("include_active_space_candidates", True)
                    else []
                ),
                "orbital_details": orbital_details,
                "scf_attempts": scf_attempts,
                "runtime_metadata": _runtime_metadata(started_wall_time, started_cpu_time),
                "scf_configuration": request.get("scf_options", {}),
                "df_artifact": _df_artifact_metadata(request.get("scf_options", {})),
                "checkpoint_validation": checkpoint_validation,
                "spin_square": observed_spin_square,
                "expected_spin_square": expected_spin_square,
                "spin_contamination": spin_contamination,
                "spin_contamination_warning": (
                    spin_contamination_threshold is not None
                    and spin_contamination > float(spin_contamination_threshold)
                ),
                "unrestricted_reference": is_unrestricted_reference,
                "open_shell_hamiltonian_supported": True,
            }
    if request.get("operation") == "classical_reference":
        reference = (
            calculate_closed_shell_fci(
                molecule,
                calculation,
                request["orbital_indices"],
                request["active_electrons"],
            )
            if request["spin_multiplicity"] == 1
            else calculate_open_shell_fci(
                molecule,
                calculation,
                request["orbital_indices"],
                request["active_electrons"],
                request["spin_multiplicity"],
            )
        )
        reference["scf_attempts"] = scf_attempts
        print(json.dumps(reference, ensure_ascii=False))
        return

    if request.get("operation") == "build_hamiltonian":
        active_indices = request["orbital_indices"]
        active_electrons = request["active_electrons"]
        core_indices = list(range(min(active_indices)))
        if set(core_indices) & set(active_indices):
            raise ValueError("冻结核心轨道不能与确认的活性轨道重叠。")
        if request["spin_multiplicity"] != 1:
            result.update(build_open_shell_hamiltonian(molecule, calculation, active_indices))
            result["open_shell_hamiltonian_supported"] = True
            print(json.dumps(result))
            return
        mo_coefficients = calculation.mo_coeff
        one_body = mo_coefficients.T @ calculation.get_hcore() @ mo_coefficients
        two_body = ao2mo.kernel(molecule, mo_coefficients, compact=False).reshape((len(orbital_energies),) * 4)
        active_one_body = one_body[np.ix_(active_indices, active_indices)].copy()
        for core_index in core_indices:
            active_one_body += 2 * two_body[np.ix_(active_indices, active_indices, [core_index], [core_index])][:, :, 0, 0]
            active_one_body -= two_body[np.ix_(active_indices, [core_index], [core_index], active_indices)][:, 0, 0, :]
        core_energy = molecule.energy_nuc()
        for core_index in core_indices:
            core_energy += 2 * one_body[core_index, core_index]
            for other_index in core_indices:
                core_energy += 2 * two_body[core_index, core_index, other_index, other_index] - two_body[core_index, other_index, other_index, core_index]
        result["core_energy_hartree"] = float(core_energy)
        result["one_body_integrals"] = active_one_body.tolist()
        result["two_body_integrals"] = two_body[np.ix_(active_indices, active_indices, active_indices, active_indices)].tolist()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
