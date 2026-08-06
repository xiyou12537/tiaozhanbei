"""Run a small, real restricted Hartree-Fock calculation inside the Linux PySCF runtime."""

from __future__ import annotations

import json
import sys

import numpy as np
from openfermion import FermionOperator, QubitOperator, binary_code_transform, jordan_wigner, parity_code, taper_off_qubits
from pyscf import ao2mo, fci, gto, scf

MAX_SPATIAL_ORBITALS = 12
MAX_CLASSICAL_REFERENCE_ORBITALS = 8


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


def run_scf(
    molecule,
    spin_multiplicity: int,
    requested_methods: list[str] | None = None,
    max_attempts: int = 3,
) -> tuple[object | None, list[dict]]:
    attempts: list[dict] = []
    method_lookup = {"RHF": scf.RHF, "UHF": scf.UHF, "ROHF": scf.ROHF}
    default_methods = ["RHF"] if spin_multiplicity == 1 else ["UHF", "ROHF"]
    selected_methods = requested_methods or default_methods
    if spin_multiplicity != 1 and "RHF" in selected_methods:
        raise ValueError("开壳层候选不能使用 RHF。")
    method_classes = [method_lookup[name] for name in selected_methods]
    strategies = (
        (0.3, "atom", 0.1, False),
        (0.5, "atom", 0.2, True),
        (0.0, "minao", 0.0, False),
    )
    for method_class in method_classes:
        for level_shift, initial_guess, damping, use_newton in strategies[:max_attempts]:
            initial_calculation = method_class(molecule)
            calculation = scf.newton(initial_calculation) if use_newton else initial_calculation
            calculation.max_cycle = 200
            calculation.diis_space = 12
            calculation.level_shift = level_shift
            calculation.damp = damping
            cycle_log: list[dict] = []
            calculation.callback = lambda values: cycle_log.append({"cycle": values.get("cycle"), "energy_hartree": values.get("e_tot")})
            calculation.verbose = 0
            calculation.kernel(dm0=initial_calculation.get_init_guess(key=initial_guess))
            attempts.append({"method": method_class.__name__, "level_shift": level_shift, "initial_guess": initial_guess, "damping": damping, "second_order": use_newton, "converged": calculation.converged, "iterations": cycle_log})
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
    calculation, scf_attempts = run_scf(
        molecule,
        request["spin_multiplicity"],
        request.get("requested_methods"),
        int(request.get("max_scf_attempts", 3)),
    )
    if calculation is None:
        print(
            json.dumps(
                {
                    "status": "needs_model_review",
                    "error_code": "scf_not_converged",
                    "message": "已尝试 UHF/ROHF、level shift、阻尼和二阶 SCF，仍未收敛；请复核几何、电荷和自旋多重度。",
                    "basis_set": request.get("basis_set", "sto-3g"),
                    "scf_attempts": scf_attempts,
                },
                ensure_ascii=False,
            )
        )
        return
    energy = calculation.e_tot
    is_open_shell = request["spin_multiplicity"] != 1
    if is_open_shell:
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
                "method_name": f"{type(calculation).__name__}/{request.get('basis_set', 'sto-3g')}",
                "basis_set": request.get("basis_set", "sto-3g"),
                "electron_count": molecule.nelectron,
                "orbital_count": len(orbital_energies),
                "hf_total_energy_hartree": float(energy),
                "orbital_energies_hartree": orbital_energies,
                "active_space_candidates": build_active_space_candidates(orbital_energies, occupancies, orbital_details, is_open_shell),
                "orbital_details": orbital_details,
                "scf_attempts": scf_attempts,
                "spin_square": observed_spin_square,
                "expected_spin_square": expected_spin_square,
                "spin_contamination": spin_contamination,
                "spin_contamination_warning": (
                    spin_contamination_threshold is not None
                    and spin_contamination > float(spin_contamination_threshold)
                ),
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
