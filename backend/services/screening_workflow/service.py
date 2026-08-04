from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


MIN_CANDIDATE_COUNT = 3


@dataclass(frozen=True)
class MaterialProfile:
    material_id: str
    material_name: str
    material_family: str
    active_site: str
    adsorption_energy_li2s6: float
    adsorption_energy_li2s4: float
    reaction_barrier_proxy: float
    conductivity_score: float
    stability_score: float
    synthesis_feasibility_score: float
    source_type: str
    source_reference: str


class ScreeningWorkflowService:
    """Build a demo Li-S catalyst screening loop for multiple materials."""

    MATERIAL_CATALOG: dict[str, MaterialProfile] = {
        "Fe-N4/C": MaterialProfile(
            material_id="mat-fe-n4-c",
            material_name="Fe-N4/C",
            material_family="single-atom M-N-C",
            active_site="Fe-N4",
            adsorption_energy_li2s6=-1.18,
            adsorption_energy_li2s4=-1.05,
            reaction_barrier_proxy=0.42,
            conductivity_score=0.82,
            stability_score=0.78,
            synthesis_feasibility_score=0.74,
            source_type="demo_literature_proxy",
            source_reference="Li-S single-atom catalyst demo profile",
        ),
        "Co-N4/C": MaterialProfile(
            material_id="mat-co-n4-c",
            material_name="Co-N4/C",
            material_family="single-atom M-N-C",
            active_site="Co-N4",
            adsorption_energy_li2s6=-1.02,
            adsorption_energy_li2s4=-0.92,
            reaction_barrier_proxy=0.47,
            conductivity_score=0.79,
            stability_score=0.76,
            synthesis_feasibility_score=0.8,
            source_type="demo_literature_proxy",
            source_reference="Li-S single-atom catalyst demo profile",
        ),
        "MoS2": MaterialProfile(
            material_id="mat-mos2",
            material_name="MoS2",
            material_family="transition-metal sulfide",
            active_site="Mo-edge",
            adsorption_energy_li2s6=-0.86,
            adsorption_energy_li2s4=-0.78,
            reaction_barrier_proxy=0.54,
            conductivity_score=0.64,
            stability_score=0.84,
            synthesis_feasibility_score=0.88,
            source_type="demo_literature_proxy",
            source_reference="Layered sulfide catalyst demo profile",
        ),
        "VN": MaterialProfile(
            material_id="mat-vn",
            material_name="VN",
            material_family="transition-metal nitride",
            active_site="V-top",
            adsorption_energy_li2s6=-0.94,
            adsorption_energy_li2s4=-0.82,
            reaction_barrier_proxy=0.5,
            conductivity_score=0.86,
            stability_score=0.7,
            synthesis_feasibility_score=0.68,
            source_type="demo_literature_proxy",
            source_reference="Conductive nitride catalyst demo profile",
        ),
    }

    def list_materials(self) -> list[dict]:
        return [self._profile_to_dict(profile) for profile in self.MATERIAL_CATALOG.values()]

    def create_workflow(self, case_id: str, candidate_materials: list[str]) -> dict:
        normalized = self._normalize_candidates(candidate_materials)
        candidate_results = [self._build_candidate_result(name) for name in normalized]
        leaderboard = self._rank_candidates(candidate_results)
        candidate_results_by_name = {item["candidate_material"]: item for item in candidate_results}
        for row in leaderboard:
            candidate_results_by_name[row["candidate_material"]]["score"] = row["score"]
            candidate_results_by_name[row["candidate_material"]]["explanation"] = row["explanation"]

        workflow_id = str(uuid4())
        return {
            "workflow_id": workflow_id,
            "case_id": case_id,
            "status": "completed",
            "candidate_count": len(candidate_results),
            "candidate_results": candidate_results,
            "classical_screening": [
                {
                    "candidate_material": item["candidate_material"],
                    "material_profile": item["material_profile"],
                    "screening": item["screening"],
                }
                for item in candidate_results
            ],
            "quantum_refinement": [
                {
                    "candidate_material": item["candidate_material"],
                    "chemistry_model": item["chemistry_model"],
                    "quantum_problem": item["quantum_problem"],
                    "distributed_execution": item["distributed_execution"],
                    "quantum_refinement": item["quantum_refinement"],
                }
                for item in candidate_results
                if item["screening"]["passed"] or item["score"]["rank_position"] <= 2
            ],
            "explanations": {
                item["material_profile"]["material_id"]: item["explanation"] for item in candidate_results
            },
            "leaderboard": leaderboard,
            "recommended_material": leaderboard[0]["candidate_material"],
        }

    def _normalize_candidates(self, candidate_materials: list[str]) -> list[str]:
        normalized = []
        for item in candidate_materials:
            name = item.strip()
            if name and name not in normalized:
                normalized.append(name)
        if len(normalized) < MIN_CANDIDATE_COUNT:
            raise ValueError(f"candidate_materials must contain at least {MIN_CANDIDATE_COUNT} unique materials.")
        return normalized

    def _build_candidate_result(self, material_name: str) -> dict:
        profile = self._get_profile(material_name)
        screening = self._build_classical_screening(profile)
        chemistry_model = self._build_chemistry_model(profile)
        quantum_problem = self._build_quantum_problem(profile, chemistry_model)
        distributed_execution = self._build_distributed_execution(quantum_problem, screening)
        quantum_refinement = self._build_quantum_refinement(profile, quantum_problem, distributed_execution)

        return {
            "candidate_material": profile.material_name,
            "material_profile": self._profile_to_dict(profile),
            "screening": screening,
            "chemistry_model": chemistry_model,
            "quantum_problem": quantum_problem,
            "distributed_execution": distributed_execution,
            "quantum_refinement": quantum_refinement,
            "score": {},
            "explanation": {},
        }

    def _get_profile(self, material_name: str) -> MaterialProfile:
        if material_name in self.MATERIAL_CATALOG:
            return self.MATERIAL_CATALOG[material_name]

        return MaterialProfile(
            material_id=f"mat-custom-{material_name.lower().replace(' ', '-')}",
            material_name=material_name,
            material_family="custom-candidate",
            active_site="reported-active-site",
            adsorption_energy_li2s6=-0.9,
            adsorption_energy_li2s4=-0.8,
            reaction_barrier_proxy=0.58,
            conductivity_score=0.62,
            stability_score=0.66,
            synthesis_feasibility_score=0.6,
            source_type="user_supplied_demo_default",
            source_reference="Generated fallback profile; replace with measured or literature data.",
        )

    def _build_classical_screening(self, profile: MaterialProfile) -> dict:
        adsorption_score = self._score_adsorption(profile.adsorption_energy_li2s6, profile.adsorption_energy_li2s4)
        catalytic_activity_score = self._clip01(1.0 - profile.reaction_barrier_proxy)
        classical_score = round(
            100
            * (
                0.3 * adsorption_score
                + 0.25 * catalytic_activity_score
                + 0.2 * profile.stability_score
                + 0.15 * profile.conductivity_score
                + 0.1 * profile.synthesis_feasibility_score
            ),
            2,
        )
        passed = classical_score >= 68
        return {
            "adsorption_score": round(adsorption_score * 100, 2),
            "catalytic_activity_score": round(catalytic_activity_score * 100, 2),
            "stability_score": round(profile.stability_score * 100, 2),
            "conductivity_score": round(profile.conductivity_score * 100, 2),
            "synthesis_score": round(profile.synthesis_feasibility_score * 100, 2),
            "classical_screening_score": classical_score,
            "passed": passed,
            "screening_reason": self._screening_reason(profile, classical_score, passed),
            "score_formula": {
                "adsorption": 0.3,
                "catalytic_activity": 0.25,
                "stability": 0.2,
                "conductivity": 0.15,
                "synthesis": 0.1,
            },
            "field_sources": {
                "adsorption_score": "proxy_model",
                "catalytic_activity_score": "proxy_model",
                "stability_score": "literature",
                "conductivity_score": "literature",
                "synthesis_score": "literature",
                "classical_screening_score": "proxy_model",
            },
        }

    def _build_chemistry_model(self, profile: MaterialProfile) -> dict:
        orbital_count = 8 if profile.material_family == "single-atom M-N-C" else 10
        electron_count = orbital_count + (2 if profile.adsorption_energy_li2s6 < -1.0 else 0)
        return {
            "reaction_system": "Li-S battery polysulfide conversion",
            "polysulfide_species": ["Li2S6", "Li2S4"],
            "catalyst_active_site": profile.active_site,
            "adsorption_configuration": f"{profile.active_site} anchored polysulfide adsorption",
            "active_space": {
                "label": f"{profile.active_site}-polysulfide-frontier",
                "orbitals": orbital_count,
                "electrons": electron_count,
            },
            "electron_count": electron_count,
            "orbital_count": orbital_count,
            "model_assumption": "Rule-based demo model calibrated from adsorption and barrier proxy fields.",
            "model_source": profile.source_reference,
            "source_type": profile.source_type,
        }

    def _build_quantum_problem(self, profile: MaterialProfile, chemistry_model: dict) -> dict:
        qubit_count = chemistry_model["orbital_count"]
        pauli_term_count = qubit_count * 3 + 5
        hamiltonian_terms = self._build_demo_hamiltonian(profile, qubit_count)
        qasm_lines = [
            "OPENQASM 2.0;",
            'include "qelib1.inc";',
            f"qreg q[{qubit_count}];",
        ]
        for index in range(qubit_count):
            qasm_lines.append(f"ry({round(0.08 * (index + 1), 3)}) q[{index}];")
        for index in range(qubit_count - 1):
            qasm_lines.append(f"cx q[{index}],q[{index + 1}];")

        return {
            "hamiltonian_terms": hamiltonian_terms,
            "mapping_method": "Jordan-Wigner demo mapping",
            "ansatz_type": "hardware-efficient RY-CX ansatz",
            "optimizer": "COBYLA-demo",
            "active_space": chemistry_model["active_space"],
            "qubit_count": qubit_count,
            "pauli_term_count": pauli_term_count,
            "vqe_circuit_qasm": "\n".join(qasm_lines) + "\n",
            "expected_outputs": ["vqe_energy", "refined_adsorption_energy", "barrier_proxy"],
            "source_type": "proxy_model",
        }

    def _build_distributed_execution(self, quantum_problem: dict, screening: dict) -> dict:
        qubit_count = quantum_problem["qubit_count"]
        partition_count = 2 if qubit_count <= 8 else 3
        subcircuits = [
            {"subcircuit_id": f"sub-{index + 1}", "qubits": list(range(index, qubit_count, partition_count))}
            for index in range(partition_count)
        ]
        communication_cost = round((partition_count - 1) * 0.08 + qubit_count * 0.01, 3)
        execution_quality = round(max(0.5, 0.96 - communication_cost + screening["conductivity_score"] / 1000), 3)
        return {
            "subcircuits": subcircuits,
            "assigned_qpus": [f"demo-qpu-{index + 1}" for index in range(partition_count)],
            "execution_backend": "demo-distributed-statevector",
            "shots": 2048,
            "estimated_runtime": round(1.4 + qubit_count * 0.18 + partition_count * 0.35, 2),
            "communication_cost": communication_cost,
            "execution_quality": execution_quality,
            "measurement_summary": {
                "dominant_state": "polysulfide-bound",
                "success_probability": round(execution_quality * 0.92, 3),
            },
            "source_type": "simulator_output",
        }

    def _build_quantum_refinement(
        self,
        profile: MaterialProfile,
        quantum_problem: dict,
        distributed_execution: dict,
    ) -> dict:
        mean_adsorption = (profile.adsorption_energy_li2s6 + profile.adsorption_energy_li2s4) / 2
        correction = 0.04 * distributed_execution["execution_quality"] - 0.02 * profile.reaction_barrier_proxy
        refined_adsorption_energy = round(mean_adsorption - correction, 3)
        barrier_proxy = round(max(0.18, profile.reaction_barrier_proxy - 0.12 * distributed_execution["execution_quality"]), 3)
        confidence = round(min(0.96, 0.62 + distributed_execution["execution_quality"] * 0.22), 3)
        quantum_refine_score = round(
            100
            * (
                0.42 * self._score_adsorption(refined_adsorption_energy, refined_adsorption_energy)
                + 0.28 * self._clip01(1 - barrier_proxy)
                + 0.18 * distributed_execution["execution_quality"]
                + 0.12 * confidence
            ),
            2,
        )
        return {
            "refined_adsorption_energy": refined_adsorption_energy,
            "reaction_energy_proxy": round(refined_adsorption_energy + barrier_proxy * 0.35, 3),
            "barrier_proxy": barrier_proxy,
            "electronic_correlation_indicator": round(quantum_problem["pauli_term_count"] / 100, 3),
            "vqe_energy": round(refined_adsorption_energy - quantum_problem["qubit_count"] * 0.035, 3),
            "confidence": confidence,
            "quantum_refine_score": quantum_refine_score,
            "field_sources": {
                "refined_adsorption_energy": "proxy_model",
                "reaction_energy_proxy": "proxy_model",
                "barrier_proxy": "proxy_model",
                "electronic_correlation_indicator": "proxy_model",
                "vqe_energy": "simulator_output",
                "confidence": "proxy_model",
                "quantum_refine_score": "proxy_model",
            },
        }

    def _rank_candidates(self, candidate_results: list[dict]) -> list[dict]:
        rows = []
        for result in candidate_results:
            screening = result["screening"]
            refinement = result["quantum_refinement"]
            execution = result["distributed_execution"]
            deploy_score = round(max(0.0, 100 * execution["execution_quality"] - execution["communication_cost"] * 20), 2)
            confidence_score = round(refinement["confidence"] * 100, 2)
            final_score = round(
                0.35 * screening["classical_screening_score"]
                + 0.35 * refinement["quantum_refine_score"]
                + 0.2 * deploy_score
                + 0.1 * confidence_score,
                2,
            )
            rows.append(
                {
                    "candidate_material": result["candidate_material"],
                    "score": {
                        "classical_screening_score": screening["classical_screening_score"],
                        "quantum_refine_score": refinement["quantum_refine_score"],
                        "deploy_score": deploy_score,
                        "confidence_score": confidence_score,
                        "final_score": final_score,
                        "rank_position": 0,
                        "recommendation_level": self._recommendation_level(final_score),
                        "reason": "",
                        "risk_notes": [],
                        "score_breakdown": {},
                        "evidence_source_summary": {},
                        "model_limitations": [],
                        "next_validation_step": "",
                    },
                    "explanation": {},
                }
            )

        rows.sort(key=lambda item: item["score"]["final_score"], reverse=True)
        for index, row in enumerate(rows, start=1):
            row["score"]["rank_position"] = index
            result = next(item for item in candidate_results if item["candidate_material"] == row["candidate_material"])
            row["score"]["reason"] = self._ranking_reason(index, result)
            row["score"]["risk_notes"] = self._risk_notes(result)
            row["score"]["score_breakdown"] = {
                "classical_screening_score": screening["classical_screening_score"]
                if (screening := result["screening"])
                else 0,
                "quantum_refine_score": result["quantum_refinement"]["quantum_refine_score"],
                "deploy_score": row["score"]["deploy_score"],
                "confidence_score": row["score"]["confidence_score"],
                "weights": {
                    "classical_screening_score": 0.35,
                    "quantum_refine_score": 0.35,
                    "deploy_score": 0.2,
                    "confidence_score": 0.1,
                },
            }
            row["score"]["evidence_source_summary"] = {
                "material_profile": result["material_profile"]["source_type"],
                "classical_screening": "proxy_model",
                "chemistry_model": result["chemistry_model"]["source_type"],
                "quantum_problem": result["quantum_problem"]["source_type"],
                "distributed_execution": result["distributed_execution"]["source_type"],
                "quantum_refinement": "proxy_model",
            }
            row["score"]["model_limitations"] = [
                "Current Hamiltonian terms are demo proxies, not ab initio electronic structure outputs.",
                "Distributed execution quality is estimated from rule-based partition cost rather than hardware telemetry.",
            ]
            row["score"]["next_validation_step"] = self._next_validation_step(index)
            row["explanation"] = {
                "candidate_material": row["candidate_material"],
                "recommendation_reason": row["score"]["reason"],
                "risk_notes": row["score"]["risk_notes"],
                "score_breakdown": row["score"]["score_breakdown"],
                "evidence_source_summary": row["score"]["evidence_source_summary"],
                "model_limitations": row["score"]["model_limitations"],
                "next_validation_step": row["score"]["next_validation_step"],
                "key_evidence": {
                    "screening": result["screening"],
                    "quantum_refinement": result["quantum_refinement"],
                    "distributed_execution": result["distributed_execution"],
                },
            }
        return rows

    def _build_demo_hamiltonian(self, profile: MaterialProfile, qubit_count: int) -> list[dict]:
        base = abs(profile.adsorption_energy_li2s6)
        return [
            {"pauli": "I", "coefficient": round(-base, 4), "meaning": "adsorption baseline"},
            {"pauli": "Z0", "coefficient": round(base * 0.18, 4), "meaning": "active-site charge response"},
            {"pauli": "Z1", "coefficient": round(profile.reaction_barrier_proxy * 0.16, 4), "meaning": "barrier proxy"},
            {
                "pauli": f"X0 X{min(1, qubit_count - 1)}",
                "coefficient": round(profile.conductivity_score * 0.07, 4),
                "meaning": "electron-transfer coupling",
            },
        ]

    def _score_adsorption(self, li2s6_energy: float, li2s4_energy: float) -> float:
        target = -1.0
        average_energy = (li2s6_energy + li2s4_energy) / 2
        return self._clip01(1 - abs(average_energy - target) / 0.8)

    def _screening_reason(self, profile: MaterialProfile, classical_score: float, passed: bool) -> str:
        if passed:
            return f"{profile.material_name} has balanced adsorption, conductivity and stability for Li-S screening."
        return f"{profile.material_name} is retained for traceability, but the classical score is below the refinement threshold."

    def _ranking_reason(self, rank: int, result: dict) -> str:
        material = result["candidate_material"]
        screening = result["screening"]
        refinement = result["quantum_refinement"]
        if rank == 1:
            return f"{material} ranks first because it combines strong classical screening with the best quantum refinement signal."
        if rank == 2:
            return f"{material} ranks second with competitive refinement, but its deployment or adsorption balance is weaker than the leader."
        return f"{material} remains a viable fallback, but its final score is limited by screening and refinement trade-offs."

    def _risk_notes(self, result: dict) -> list[str]:
        notes = []
        profile = result["material_profile"]
        if profile["synthesis_feasibility_score"] < 0.72:
            notes.append("Synthesis feasibility should be validated before scale-up.")
        if result["distributed_execution"]["communication_cost"] > 0.22:
            notes.append("Distributed execution cost may reduce confidence for larger active spaces.")
        if result["quantum_refinement"]["confidence"] < 0.78:
            notes.append("Quantum refinement confidence is moderate; use as a demo-level estimate.")
        return notes or ["No major demo-level risk flagged."]

    def _recommendation_level(self, final_score: float) -> str:
        if final_score >= 82:
            return "strong_recommend"
        if final_score >= 74:
            return "recommend"
        if final_score >= 66:
            return "backup"
        return "not_recommended"

    def _next_validation_step(self, rank_position: int) -> str:
        if rank_position == 1:
            return "Validate the top-ranked catalyst with adsorption DFT and coin-cell cycling."
        return "Use higher-fidelity adsorption and barrier calculations before experimental prioritization."

    def _profile_to_dict(self, profile: MaterialProfile) -> dict:
        return {
            "material_id": profile.material_id,
            "material_name": profile.material_name,
            "material_family": profile.material_family,
            "active_site": profile.active_site,
            "adsorption_energy_li2s6": profile.adsorption_energy_li2s6,
            "adsorption_energy_li2s4": profile.adsorption_energy_li2s4,
            "reaction_barrier_proxy": profile.reaction_barrier_proxy,
            "conductivity_score": profile.conductivity_score,
            "stability_score": profile.stability_score,
            "synthesis_feasibility_score": profile.synthesis_feasibility_score,
            "source_type": profile.source_type,
            "source_reference": profile.source_reference,
        }

    def _clip01(self, value: float) -> float:
        return max(0.0, min(1.0, value))
