class CandidateService:
    CANDIDATE_CATALOG = [
        {"candidate_name": "Li2S6", "family": "lithium-polysulfide", "adsorption_strength": 0.82},
        {"candidate_name": "S8-Host-A", "family": "sulfur-host", "adsorption_strength": 0.63},
        {"candidate_name": "Li2S4", "family": "lithium-polysulfide", "adsorption_strength": 0.79},
    ]

    def build_context(self, candidate_material: str, case_id: str | None) -> dict:
        family = "lithium-polysulfide" if candidate_material.startswith("Li2S") else "sulfur-host"
        adsorption_strength = 0.82 if family == "lithium-polysulfide" else 0.63
        return {
            "case_id": case_id,
            "candidate_name": candidate_material,
            "family": family,
            "screening_passed": adsorption_strength >= 0.6,
            "adsorption_strength": adsorption_strength,
            "active_site_hint": "bridge-site" if family == "lithium-polysulfide" else "top-site",
        }

    def list_candidates(self) -> list[dict]:
        return [dict(item) for item in self.CANDIDATE_CATALOG]
