class ChemistryModelingService:
    def build_model(self, candidate_context: dict) -> dict:
        strength = float(candidate_context["adsorption_strength"])
        atom_count = 8 if candidate_context["family"] == "lithium-polysulfide" else 12
        orbital_count = 4 + int(strength * 4)
        electron_count = orbital_count
        return {
            "candidate_name": candidate_context["candidate_name"],
            "atom_count": atom_count,
            "orbital_count": orbital_count,
            "electron_count": electron_count,
            "adsorption_energy": round(-1.0 * strength, 3),
            "geometry": {
                "site": candidate_context["active_site_hint"],
                "bond_scale": round(1.1 - strength / 10, 3),
            },
        }
