from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from time import sleep
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.routers.platform import structure_modeling_service
from backend.core.config import settings
from backend.main import create_app
from backend.services.structure_modeling import service as structure_modeling_module
from backend.services.structure_modeling.service import MAX_FILE_SIZE_BYTES


FE_N4_XYZ = b"""5
FeN4 cluster
Fe 0.0 0.0 0.0
N 1.9 0.0 0.0
N -1.9 0.0 0.0
N 0.0 1.9 0.0
N 0.0 -1.9 0.0
"""

FE_N4_C_XYZ = b"""6
FeN4 carbon-supported model
Fe 0.0 0.0 0.0
N 1.9 0.0 0.0
N -1.9 0.0 0.0
N 0.0 1.9 0.0
N 0.0 -1.9 0.0
C 0.0 0.0 -2.5
"""

FE_N4_LI2S4_XYZ = b"""11
FeN4 plus Li2S4 imported DFT geometry
Fe 0.0 0.0 0.0
N 1.9 0.0 0.0
N -1.9 0.0 0.0
N 0.0 1.9 0.0
N 0.0 -1.9 0.0
Li -1.9 0.0 2.6
Li 8.05 0.0 2.6
S 0.0 0.0 2.6
S 2.05 0.0 2.6
S 4.10 0.0 2.6
S 6.15 0.0 2.6
"""

MOS2_CIF = b"""data_MoS2
_cell_length_a 3.160
_cell_length_b 3.160
_cell_length_c 12.300
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 120
_symmetry_space_group_name_H-M 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Mo1 Mo 0.000000 0.000000 0.000000
S1 S 0.333333 0.666667 0.250000
S2 S 0.666667 0.333333 0.750000
"""


class StructureModelingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client_context = TestClient(create_app(legacy_enabled=True))
        self.client = self.client_context.__enter__()
        self.owner_headers = self._register_headers("owner")
        self.other_headers = self._register_headers("other")

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_xyz_structure_reaches_quantum_region_without_scoring(self) -> None:
        parsed = self._upload_and_parse("fe_n4.xyz", FE_N4_XYZ, "Fe-N4")
        self.assertEqual(parsed["parse_status"], "parsed")
        self.assertEqual(parsed["formula"], "FeN4")
        self.assertEqual(parsed["validation_status"], "valid_with_warnings")

        structure_id = parsed["structure_id"]
        detail = self.client.get(f"/api/platform/structures/{structure_id}", headers=self.owner_headers)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data_source"], "user_uploaded_structure")
        self.assertNotIn("adsorption_energy", detail.json())

        suggested = self.client.post(
            f"/api/platform/structures/{structure_id}/active-sites/suggest",
            headers=self.owner_headers,
        ).json()["suggestions"][0]
        self.assertEqual(suggested["center_elements"], ["Fe"])
        self.assertEqual(suggested["coordination_number"], 4)
        self.assertIn("2.8 Å", suggested["recommendation_reason"])
        confirmed = self.client.post(
            f"/api/platform/structures/{structure_id}/active-sites/confirm",
            headers=self.owner_headers,
            json={
                "site_source": "suggested",
                "site_id": suggested["active_site_id"],
                "center_atom_indices": suggested["center_atom_indices"],
                "neighbor_atom_indices": suggested["neighbor_atom_indices"],
                "site_label": "Fe-N4",
            },
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertIsNotNone(confirmed.json()["confirmed_at"])
        self.assertIsNotNone(confirmed.json()["confirmed_by_user_id"])

        models = self.client.post(
            f"/api/platform/active-sites/{confirmed.json()['active_site_id']}/adsorption-models",
            headers=self.owner_headers,
            json={"polysulfide_species": ["Li2S4"], "max_conformations_per_species": 3, "initial_distance_angstrom": 2.6},
        )
        self.assertEqual(models.status_code, 200)
        self.assertEqual(models.json()["status"], "generated")
        self.assertEqual(len(models.json()["models"]), 3)

        geometry = self.client.post(
            f"/api/platform/adsorption-models/{models.json()['models'][0]['adsorption_model_id']}/geometry-optimizations",
            headers=self.owner_headers,
            json={"calculation_mode": "geometry_only"},
        )
        self.assertEqual(geometry.status_code, 200)
        self.assertEqual(geometry.json()["source_type"], "geometry_only")
        self.assertNotIn("energy", geometry.json())
        artifact_id = geometry.json()["geometry_artifact_id"]
        artifact_url = f"/api/platform/structure-screening-workflows/{parsed['workflow_id']}/artifacts/{artifact_id}"
        artifact_metadata = self.client.get(artifact_url, headers=self.owner_headers)
        self.assertEqual(artifact_metadata.status_code, 200)
        self.assertEqual(artifact_metadata.json()["artifact_role"], "optimized_geometry")
        self.assertNotIn("path", artifact_metadata.json())
        artifact_download = self.client.get(f"{artifact_url}/download", headers=self.owner_headers)
        self.assertEqual(artifact_download.status_code, 200)
        self.assertEqual(artifact_download.json()["source_type"], "geometry_only")
        self.assertEqual(self.client.get(artifact_url, headers=self.other_headers).status_code, 404)

        region = self.client.post(
            f"/api/platform/adsorption-models/{models.json()['models'][0]['adsorption_model_id']}/quantum-regions",
            headers=self.owner_headers,
            json={"geometry_optimization_id": geometry.json()["geometry_optimization_id"], "radius_angstrom": 5.0, "total_charge": 0, "spin_multiplicity": 1},
        )
        self.assertEqual(region.status_code, 200)
        self.assertEqual(region.json()["status"], "quantum_region_built")
        self.assertEqual(region.json()["embedding_method"], "frozen_atoms")

        workflow = self.client.get(
            f"/api/platform/structure-screening-workflows/{parsed['workflow_id']}",
            headers=self.owner_headers,
        )
        self.assertEqual(workflow.status_code, 200)
        self.assertEqual(workflow.json()["status"], "quantum_region_built")
        self.assertEqual(workflow.json()["stages"][1]["stage_name"], "active_site")
        self.assertTrue(workflow.json()["stages"][1]["confirmations"])
        workflow_list = self.client.get(
            "/api/platform/structure-screening-workflows",
            headers=self.owner_headers,
        )
        self.assertEqual(workflow_list.status_code, 200)
        self.assertIn(parsed["workflow_id"], {item["workflow_id"] for item in workflow_list.json()["items"]})
        other_workflows = self.client.get(
            "/api/platform/structure-screening-workflows",
            headers=self.other_headers,
        )
        self.assertNotIn(parsed["workflow_id"], {item["workflow_id"] for item in other_workflows.json()["items"]})

    def test_cif_is_parsed_and_other_users_cannot_read_it(self) -> None:
        parsed = self._upload_and_parse("mos2.cif", MOS2_CIF, "MoS2")
        self.assertEqual(parsed["formula"], "MoS2")
        self.assertEqual(parsed["structure_type"], "crystal")
        self.assertIn("Mo", parsed["elements"])

        file_id = parsed["file_id"]
        structure_id = parsed["structure_id"]
        self.assertEqual(self.client.get(f"/api/platform/structure-files/{file_id}", headers=self.other_headers).status_code, 404)
        self.assertEqual(self.client.get(f"/api/platform/structures/{structure_id}", headers=self.other_headers).status_code, 404)

    def test_invalid_structure_and_upload_limits_return_stable_errors(self) -> None:
        invalid = b"1\ninvalid\nH NaN 0.0 0.0\n"
        parsed = self._upload_and_parse("invalid.xyz", invalid, "invalid-cluster")
        self.assertEqual(parsed["parse_status"], "validation_failed")
        self.assertEqual(parsed["validation_status"], "validation_failed")

        unsupported = self.client.post(
            "/api/platform/structure-files",
            headers=self.owner_headers,
            data={"material_name": "unsupported"},
            files={"file": ("structure.txt", b"not a structure", "text/plain")},
        )
        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(unsupported.json()["detail"]["code"], "unsupported_format")

        oversized = self.client.post(
            "/api/platform/structure-files",
            headers=self.owner_headers,
            data={"material_name": "oversized"},
            files={"file": ("large.xyz", b"0" * (MAX_FILE_SIZE_BYTES + 1), "chemical/x-xyz")},
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["detail"]["code"], "file_too_large")

    def test_benchmark_rejects_minimal_fen4_and_preserves_supported_case_artifacts(self) -> None:
        minimal = self._upload_and_parse("minimal.xyz", FE_N4_XYZ, "minimal")
        rejected = self.client.post(
            "/api/platform/benchmark-cases",
            headers=self.owner_headers,
            json=self._benchmark_payload(minimal["structure_id"]),
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["detail"]["code"], "benchmark_structure_too_small")

        supported = self._upload_and_parse("supported.xyz", FE_N4_C_XYZ, "FeN4-carbon")
        created = self.client.post(
            "/api/platform/benchmark-cases",
            headers=self.owner_headers,
            json=self._benchmark_payload(supported["structure_id"]),
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["adsorbate_species"], "Li2S4")
        self.assertTrue(created.json()["structure_artifact_id"])
        artifact = self.client.get(
            f"/api/platform/structure-screening-workflows/{supported['workflow_id']}/artifacts/{created.json()['structure_artifact_id']}",
            headers=self.owner_headers,
        )
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.json()["artifact_role"], "benchmark_structure")

    def test_dft_import_requires_complete_metadata_and_comparable_energy_bundle(self) -> None:
        host = self._upload_and_parse("host.xyz", FE_N4_XYZ, "FeN4")
        imported = self._upload_and_parse("dft.xyz", FE_N4_LI2S4_XYZ, "FeN4-Li2S4")
        active_site = self.client.post(
            f"/api/platform/structures/{host['structure_id']}/active-sites/suggest",
            headers=self.owner_headers,
        ).json()["suggestions"][0]
        confirmed = self.client.post(
            f"/api/platform/structures/{host['structure_id']}/active-sites/confirm",
            headers=self.owner_headers,
            json={
                "site_source": "suggested",
                "site_id": active_site["active_site_id"],
                "center_atom_indices": active_site["center_atom_indices"],
                "neighbor_atom_indices": active_site["neighbor_atom_indices"],
                "site_label": "Fe-N4",
            },
        ).json()
        model = self.client.post(
            f"/api/platform/active-sites/{confirmed['active_site_id']}/adsorption-models",
            headers=self.owner_headers,
            json={"polysulfide_species": ["Li2S4"], "max_conformations_per_species": 3, "initial_distance_angstrom": 2.6},
        ).json()["models"][0]
        signature = {"software": "QE", "functional": "PBE", "basis": "PAW", "dispersion": "D3", "k_points": "2x2x1", "spin": "polarized"}
        complete = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/dft-imports",
            headers=self.owner_headers,
            json={
                "optimized_structure_id": imported["structure_id"],
                "calculation_metadata": {
                    "software": "Quantum ESPRESSO", "software_version": "7.3", "calculation_type": "geometry_optimization",
                    "functional": "PBE", "basis_or_pseudopotential": "PAW", "dispersion": "D3", "spin_polarization": True,
                    "total_charge": 0, "spin_multiplicity": 1, "convergence": {"force": 0.02}, "total_energy": -100.0, "energy_unit": "Hartree",
                },
                "energy_bundle": {
                    "adsorbed_system": {"energy_hartree": -100.0, "calculation_signature": signature},
                    "host": {"energy_hartree": -80.0, "calculation_signature": signature},
                    "adsorbate": {"energy_hartree": -19.0, "calculation_signature": signature},
                },
            },
        )
        self.assertEqual(complete.status_code, 201)
        self.assertEqual(complete.json()["status"], "dft_optimized")
        self.assertEqual(complete.json()["adsorption_energy_hartree"], -1.0)
        self.assertTrue(complete.json()["geometry_optimization_id"])

        incomplete = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/dft-imports",
            headers=self.owner_headers,
            json={"calculation_metadata": {"software": "QE"}, "energy_bundle": {}},
        )
        self.assertEqual(incomplete.status_code, 201)
        self.assertEqual(incomplete.json()["status"], "metadata_incomplete")
        self.assertIsNone(incomplete.json()["adsorption_energy_hartree"])
        self.assertIsNone(incomplete.json()["geometry_optimization_id"])

    def test_spin_candidates_are_asynchronous_and_contamination_requires_review(self) -> None:
        parsed = self._upload_and_parse("spin.xyz", FE_N4_XYZ, "FeN4")
        suggestion = self.client.post(
            f"/api/platform/structures/{parsed['structure_id']}/active-sites/suggest",
            headers=self.owner_headers,
        ).json()["suggestions"][0]
        active_site = self.client.post(
            f"/api/platform/structures/{parsed['structure_id']}/active-sites/confirm",
            headers=self.owner_headers,
            json={
                "site_source": "suggested", "site_id": suggestion["active_site_id"],
                "center_atom_indices": suggestion["center_atom_indices"], "neighbor_atom_indices": suggestion["neighbor_atom_indices"],
                "site_label": "Fe-N4",
            },
        ).json()
        model = self.client.post(
            f"/api/platform/active-sites/{active_site['active_site_id']}/adsorption-models",
            headers=self.owner_headers,
            json={"polysulfide_species": ["Li2S4"], "max_conformations_per_species": 3, "initial_distance_angstrom": 2.6},
        ).json()["models"][0]
        geometry = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/geometry-optimizations",
            headers=self.owner_headers,
            json={"calculation_mode": "geometry_only"},
        ).json()
        region = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/quantum-regions",
            headers=self.owner_headers,
            json={"geometry_optimization_id": geometry["geometry_optimization_id"], "radius_angstrom": 5.0, "total_charge": 0, "spin_multiplicity": 1},
        ).json()

        class FakeElectronicStructureAdapter:
            @staticmethod
            def generate_active_space_candidates(request, timeout_seconds):
                contamination = 0.1 if request["spin_multiplicity"] == 1 else 1.2
                return {
                    "status": "completed", "method_name": "UHF/def2-svp", "basis_set": "def2-svp", "scf_attempts": [{"converged": True}],
                    "hf_total_energy_hartree": -100.0 - request["spin_multiplicity"], "spin_square": contamination,
                    "expected_spin_square": 0.0, "spin_contamination": contamination,
                }

        with patch.object(structure_modeling_service, "electronic_structure_adapter", FakeElectronicStructureAdapter()):
            submitted = self.client.post(
                f"/api/platform/quantum-regions/{region['quantum_region_id']}/electronic-structure-candidates",
                headers=self.owner_headers,
                json={
                    "charge_candidates": [0], "spin_strategy": "explicit", "spin_multiplicities": [1, 3],
                    "requested_methods": ["UHF", "ROHF"], "basis_set": "def2-svp", "max_scf_attempts": 3,
                    "spin_contamination_threshold": 0.5,
                },
            )
            self.assertEqual(submitted.status_code, 202)
            task_id = submitted.json()["task_id"]
            task = None
            for _ in range(50):
                task = self.client.get(f"/api/platform/structure-tasks/{task_id}").json()
                if task["status"] in {"completed", "failed"}:
                    break
                sleep(0.02)
        self.assertEqual(task["status"], "completed")
        candidates = task["result"]["candidates"]
        self.assertEqual(len(candidates), 2)
        eligible = next(item for item in candidates if item["spin_multiplicity"] == 1)
        rejected = next(item for item in candidates if item["spin_multiplicity"] == 3)
        self.assertEqual(eligible["quality_status"], "eligible_for_confirmation")
        self.assertEqual(rejected["quality_status"], "needs_model_review")
        self.assertEqual(
            self.client.post(
                f"/api/platform/electronic-structure-candidates/{rejected['candidate_id']}/confirm",
                headers=self.owner_headers,
                json={},
            ).status_code,
            409,
        )

    def test_direct_dft_adapter_queues_and_persists_parsed_output(self) -> None:
        parsed = self._upload_and_parse("direct-dft.xyz", FE_N4_XYZ, "FeN4")
        suggestion = self.client.post(
            f"/api/platform/structures/{parsed['structure_id']}/active-sites/suggest", headers=self.owner_headers
        ).json()["suggestions"][0]
        active_site = self.client.post(
            f"/api/platform/structures/{parsed['structure_id']}/active-sites/confirm",
            headers=self.owner_headers,
            json={"site_source": "suggested", "site_id": suggestion["active_site_id"], "center_atom_indices": suggestion["center_atom_indices"], "neighbor_atom_indices": suggestion["neighbor_atom_indices"], "site_label": "Fe-N4"},
        ).json()
        model = self.client.post(
            f"/api/platform/active-sites/{active_site['active_site_id']}/adsorption-models",
            headers=self.owner_headers,
            json={"polysulfide_species": ["Li2S4"], "max_conformations_per_species": 3, "initial_distance_angstrom": 2.6},
        ).json()["models"][0]

        class FakeDftAdapter:
            @staticmethod
            def run(specification, working_directory, timeout_seconds, is_cancel_requested):
                self.assertFalse(is_cancel_requested())
                return {
                    "engine_name": "quantum_espresso", "input_artifact_path": str(working_directory / "pw.in"),
                    "output_artifact_path": str(working_directory / "engine.out"),
                    "parsed_result": {"converged": True, "total_energy_hartree": -101.25, "energy_unit": "Hartree", "optimized_atomic_sites": specification["atomic_sites"]},
                }

        metadata = {
            "software_version": "7.3", "functional": "PBE", "basis_or_pseudopotential": "PAW", "dispersion": "D3",
            "spin_polarization": True, "total_charge": 0, "spin_multiplicity": 3, "convergence": {"scf": 1e-8},
            "initial_magnetization_by_element": {"Fe": 0.5, "N": 0.0, "Li": 0.0, "S": 0.0},
        }
        runtime = self.client.get("/api/platform/dft-runtime", headers=self.owner_headers)
        self.assertEqual(runtime.status_code, 200)
        self.assertFalse(runtime.json()["neb_supported"])
        rejected_neb = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/dft-calculations",
            headers=self.owner_headers,
            json={"engine_name": "quantum_espresso", "calculation_type": "neb", "calculation_metadata": metadata},
        )
        self.assertEqual(rejected_neb.status_code, 422)
        missing_magnetization_metadata = dict(metadata)
        missing_magnetization_metadata.pop("initial_magnetization_by_element")
        rejected_spin_input = self.client.post(
            f"/api/platform/adsorption-models/{model['adsorption_model_id']}/dft-calculations",
            headers=self.owner_headers,
            json={
                "engine_name": "quantum_espresso",
                "calculation_type": "geometry_optimization",
                "calculation_metadata": missing_magnetization_metadata,
            },
        )
        self.assertEqual(rejected_spin_input.status_code, 422)
        with patch.dict(structure_modeling_service.dft_adapters, {"quantum_espresso": FakeDftAdapter()}):
            submitted = self.client.post(
                f"/api/platform/adsorption-models/{model['adsorption_model_id']}/dft-calculations",
                headers=self.owner_headers,
                json={"engine_name": "quantum_espresso", "calculation_type": "geometry_optimization", "calculation_metadata": metadata, "engine_settings": {"pseudopotentials": {}}, "max_attempts": 2, "timeout_seconds": 30},
            )
            self.assertEqual(submitted.status_code, 202)
            calculation_id = submitted.json()["dft_calculation_id"]
            for _ in range(50):
                detail = self.client.get(f"/api/platform/dft-calculations/{calculation_id}", headers=self.owner_headers).json()
                if detail["status"] in {"completed", "failed", "cancelled"}:
                    break
                sleep(0.02)
        self.assertEqual(detail["status"], "completed")
        self.assertEqual(detail["attempt_count"], 1)
        self.assertEqual(detail["parsed_result"]["total_energy_hartree"], -101.25)
        self.assertTrue(detail["parsed_result"]["geometry_optimization_id"])

    def test_materials_cloud_import_preserves_candidates_and_creates_reproduction_input(self) -> None:
        cell = b"""%BLOCK LATTICE_CART
10.0 0.0 0.0
0.0 10.0 0.0
0.0 0.0 18.0
%ENDBLOCK LATTICE_CART
KPOINTS_MP_GRID 3 3 1
Fe 0.0 0.0 0.0 SPIN=4.0
"""
        param = b"""task : GeometryOptimisation
xc_functional : pbe
cut_off_energy : 500 eV
SPIN_POLARIZED : TRUE
SPIN_FIX : 2
sedc_apply : true
sedc_scheme : g06
max_SCF_cycles : 160
elec_energy_tol : 1e-5
geom_force_tol : 1e-3
geom_method : bfgs
"""
        carbon_sites = "\n".join(f"C {index + 1}.0 0.0 -2.2" for index in range(65))
        frame = f"""77
Lattice=\"10 0 0 0 10 0 0 0 18\" Properties=species:S:1:pos:R:3 energy= -100.0 Time=0
Fe 0.0 0.0 0.0
N 1.8 0.0 0.0
N -1.8 0.0 0.0
N 0.0 1.8 0.0
N 0.0 -1.8 0.0
C 0.0 0.0 -2.2
{carbon_sites}
Li -1.8 0.0 3.0
Li 7.8 0.0 3.0
S 0.0 0.0 3.0
S 2.0 0.0 3.0
S 4.0 0.0 3.0
S 6.0 0.0 3.0
""".encode()
        archive_stream = io.BytesIO()
        with tarfile.open(fileobj=archive_stream, mode="w:gz") as archive:
            for name, content in {
                "FeN4C66-Li2S4/fe1n4c66-li2s4.1energies.dat": b"0 -100.0\n",
                "FeN4C66-Li2S4/fe1n4c66-li2s4.1str.xyz": frame,
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        files = {"fe1n4c66-li2s.cell": cell, "fe1n4c66-li2s.param": param, "FeLIPS_data.tar.gz": archive_stream.getvalue()}
        checksums = {name: hashlib.md5(content).hexdigest() for name, content in files.items()}

        def fake_download(filename: str, target: Path) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[filename])

        with TemporaryDirectory() as temporary_directory:
            with patch.object(structure_modeling_module, "RESEARCH_BENCHMARK_ROOT", Path(temporary_directory)), patch.dict(
                structure_modeling_module.MATERIALS_CLOUD_FILES,
                checksums,
                clear=True,
            ), patch.object(structure_modeling_service, "_download_materials_cloud_file", side_effect=fake_download), patch.object(
                settings,
                "RESEARCH_BENCHMARK_ADMIN_USERNAMES",
                self._username_from_headers(),
            ):
                benchmark_key = f"literature-test-{uuid4().hex}"
                imported = self.client.post(
                    "/api/platform/research-benchmarks/import-materials-cloud",
                    headers=self.owner_headers,
                    json={"benchmark_key": benchmark_key, "retain_raw_artifacts": True},
                )
                self.assertEqual(imported.status_code, 201)
                self.assertEqual(imported.json()["candidate_count"], 1)
                self.assertEqual(imported.json()["scientific_validation_level"], "reproduction_baseline_only")
                discovered = self.client.get(
                    f"/api/platform/research-benchmarks?benchmark_key={benchmark_key}",
                    headers=self.owner_headers,
                )
                self.assertEqual(discovered.status_code, 200)
                self.assertEqual(discovered.json()["items"][0]["benchmark_id"], imported.json()["benchmark_id"])
                self.assertTrue(discovered.json()["can_import"])
                candidates = self.client.get(
                    f"/api/platform/research-benchmarks/{imported.json()['benchmark_id']}/candidates",
                    headers=self.owner_headers,
                )
                self.assertEqual(candidates.status_code, 200)
                self.assertEqual(candidates.json()["items"][0]["source_energy_unit"], "dataset_native_unit_not_confirmed")
                self.assertEqual(candidates.json()["items"][0]["source_metadata"]["composition_validation"], "passed")
                candidate_artifact = self.client.get(
                    f"/api/platform/research-benchmarks/{imported.json()['benchmark_id']}/candidates/{candidates.json()['items'][0]['candidate_id']}/artifact",
                    headers=self.owner_headers,
                )
                self.assertEqual(candidate_artifact.status_code, 200)
                self.assertEqual(candidate_artifact.json()["artifact_role"], "literature_candidate_geometry")
                self.assertTrue(candidate_artifact.json()["checksum_sha256"])
                selected = self.client.post(
                    f"/api/platform/research-benchmarks/{imported.json()['benchmark_id']}/candidates/{candidates.json()['items'][0]['candidate_id']}/select",
                    headers=self.owner_headers,
                )
                self.assertEqual(selected.status_code, 201)
                self.assertEqual(selected.json()["status"], "literature_reproduction_input_selected")
                workflow = self.client.get(
                    f"/api/platform/structure-screening-workflows/{selected.json()['workflow_id']}",
                    headers=self.owner_headers,
                )
                self.assertEqual(workflow.status_code, 200)
                self.assertEqual(workflow.json()["data_source"], "literature_open_dataset")
                self.assertEqual(workflow.json()["scientific_validation_level"], "reproduction_baseline_only")

    def _username_from_headers(self) -> str:
        token = self.owner_headers["Authorization"].split(" ", 1)[1]
        payload = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(payload.status_code, 200)
        return payload.json()["username"]

    def _benchmark_payload(self, structure_id: str) -> dict:
        return {
            "title": "Fe-N4 + Li2S4 benchmark", "catalyst_model_type": "FeN4-graphene", "adsorbate_species": "Li2S4",
            "structure_id": structure_id, "structure_origin": "user_uploaded_structure", "geometry_status": "initial", "total_charge": 0,
            "spin_candidate_definitions": [{"strategy": "transition_metal_auto_candidates", "multiplicities": [1, 3, 5]}],
            "dft_metadata": {}, "version": "v1.0.0",
        }

    def _upload_and_parse(self, filename: str, content: bytes, material_name: str) -> dict:
        upload = self.client.post(
            "/api/platform/structure-files",
            headers=self.owner_headers,
            data={"material_name": material_name},
            files={"file": (filename, content, "application/octet-stream")},
        )
        self.assertEqual(upload.status_code, 201)
        parse = self.client.post(f"/api/platform/structure-files/{upload.json()['file_id']}/parse", headers=self.owner_headers)
        self.assertEqual(parse.status_code, 200)
        return parse.json()

    def _register_headers(self, prefix: str) -> dict[str, str]:
        username = f"{prefix}_{uuid4().hex[:12]}"
        response = self.client.post("/api/auth/register", json={"username": username, "password": "test-password"})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['token']}"}


if __name__ == "__main__":
    unittest.main()
