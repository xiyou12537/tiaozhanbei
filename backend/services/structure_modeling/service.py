from __future__ import annotations

import hashlib
import json
import logging
import math
import mimetypes
import re
import shutil
import tarfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import numpy as np
from ase import Atoms
from ase.calculators.lj import LennardJones
from ase.constraints import FixAtoms
from ase.io import read as ase_read
from ase.optimize import BFGS
from scipy.spatial import cKDTree

from backend.db.repositories.structure_modeling_repository import StructureModelingRepository
from backend.core.config import settings
from backend.services.dft_engine import Cp2kAdapter, DftEngineError, DftExecutionCancelled, QuantumEspressoAdapter
from backend.services.electronic_structure.docker_adapter import DockerPySCFAdapter, ElectronicStructureRuntimeError
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService
from backend.services.runtime_status import load_circuit_runtime, load_partition_pipeline
from backend.services.task_manager import task_manager

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
MAX_ATOM_COUNT = 10_000
MAX_ATOMIC_SITES_PAGE_SIZE = 500
MIN_INTERATOMIC_DISTANCE_ANGSTROM = 0.50
MIN_ADSORPTION_DISTANCE_ANGSTROM = 2.0
MAX_ADSORPTION_DISTANCE_ANGSTROM = 3.5
MIN_CONFORMATIONS_PER_SPECIES = 3
DEFAULT_QUANTUM_REGION_RADIUS_ANGSTROM = 5.0
MAX_QUANTUM_REGION_RADIUS_ANGSTROM = 12.0
MIN_QUANTUM_REGION_RADIUS_ANGSTROM = 1.0
MAX_GEOMETRY_RELAXATION_STEPS = 50
GEOMETRY_FORCE_TOLERANCE_EV_PER_ANGSTROM = 0.05
BACKGROUND_ELECTRONIC_STRUCTURE_TIMEOUT_SECONDS = 900
SUPPORTED_FILE_TYPES = {"xyz", "cif", "mol", "sdf", "poscar", "contcar"}
ASE_FORMATS = {"xyz": "xyz", "cif": "cif", "mol": "mol", "sdf": "sdf", "poscar": "vasp", "contcar": "vasp"}
TRANSITION_METALS = {"Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Mo", "W", "Nb", "Ta"}
ADSORPTION_ORIENTATIONS = ("li_end_toward_site", "s_chain_toward_site", "side_on_adsorption")
CONFORMATION_DISTANCE_OFFSETS_ANGSTROM = (0.0, -0.25, 0.25)
DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
STRUCTURE_UPLOAD_ROOT = DATA_ROOT / "structure_uploads"
STRUCTURE_ARTIFACT_ROOT = DATA_ROOT / "structure_artifacts"
DFT_RUN_ROOT = DATA_ROOT / "dft_runs"
RESEARCH_BENCHMARK_ROOT = DATA_ROOT / "research_benchmarks"
MATERIALS_CLOUD_DATASET_URL = "https://archive.materialscloud.org/records/f5t2r-6qf35"
MATERIALS_CLOUD_FILES_URL = f"{MATERIALS_CLOUD_DATASET_URL}/files"
MATERIALS_CLOUD_FILES = {
    "fe1n4c66-li2s.cell": "1911f4716dab03abf4664145f6221821",
    "fe1n4c66-li2s.param": "81f00f321c14eef15bf8847d8a4c7e5c",
    "FeLIPS_data.tar.gz": "e02c63af54a4478722cc82e5754d569f",
}
MAX_RESEARCH_BENCHMARK_DOWNLOAD_BYTES = 100 * 1024 * 1024


class StructureModelingError(Exception):
    """A stable API error for user-correctable structure modeling failures."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class StructureModelingService:
    """Build the non-scoring, user-owned structural modeling stage of the chemistry workflow."""

    def __init__(self, repository: StructureModelingRepository | None = None, electronic_structure_adapter: DockerPySCFAdapter | None = None) -> None:
        self.repository = repository or StructureModelingRepository()
        self.electronic_structure_adapter = electronic_structure_adapter or DockerPySCFAdapter()
        self.vqe_service = VqeSimulatorService()
        self.dft_adapters = {
            "quantum_espresso": QuantumEspressoAdapter(settings.QE_EXECUTABLE, settings.QE_PSEUDO_DIR or None),
            "cp2k": Cp2kAdapter(settings.CP2K_EXECUTABLE),
        }

    def upload_structure_file(
        self,
        *,
        owner_user_id: int,
        material_name: str,
        material_family: str | None,
        description: str | None,
        original_filename: str,
        content: bytes,
    ) -> dict:
        file_type = self._detect_file_type(original_filename, content)
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise StructureModelingError("file_too_large", "文件超过 20 MB 限制。", 413)

        file_id = self._new_id("sf")
        normalized_filename = f"{file_id}.{file_type}"
        storage_path = STRUCTURE_UPLOAD_ROOT / normalized_filename
        self._write_bytes(storage_path, content)
        record = self.repository.create_file(
            {
                "file_id": file_id,
                "owner_user_id": owner_user_id,
                "material_name": material_name,
                "material_family": material_family,
                "description": description,
                "original_filename": original_filename,
                "normalized_filename": normalized_filename,
                "file_type": file_type,
                "file_size_bytes": len(content),
                "file_hash": hashlib.sha256(content).hexdigest(),
                "storage_path": str(storage_path),
                "parse_status": "uploaded",
            }
        )
        return self.serialize_file(record)

    def parse_structure_file(self, file_id: str, owner_user_id: int) -> dict:
        file_record = self._get_file_or_raise(file_id, owner_user_id)
        if file_record.structure_id:
            structure = self.repository.get_structure(file_record.structure_id, owner_user_id)
            if structure is not None:
                return self.serialize_parse_result(file_record, structure)

        self.repository.update_file(file_id, owner_user_id, parse_status="parsing", parse_error_code=None, parse_error_message=None)
        try:
            parsed = self._parse_file(file_record.storage_path, file_record.file_type)
            validation = self._validate_structure(parsed)
            structure_id = self._new_id("st")
            workflow_id = self._new_id("ssw")
            structure = self.repository.save_structure(
                {
                    "structure_id": structure_id,
                    "file_id": file_record.file_id,
                    "owner_user_id": owner_user_id,
                    "workflow_id": workflow_id,
                    **parsed,
                    **validation,
                }
            )
            parse_status = "parsed" if validation["validation_status"] in {"valid", "valid_with_warnings"} else "validation_failed"
            self.repository.update_file(file_id, owner_user_id, parse_status=parse_status, structure_id=structure_id)
            workflow_status = "active_site_pending" if parse_status == "parsed" else "validation_failed"
            self.repository.create_workflow(
                {
                    "workflow_id": workflow_id,
                    "structure_id": structure_id,
                    "owner_user_id": owner_user_id,
                    "status": workflow_status,
                    "payload": {"data_source": "user_uploaded_structure", "structure_id": structure_id, "events": []},
                }
            )
            updated_file = self._get_file_or_raise(file_id, owner_user_id)
            return self.serialize_parse_result(updated_file, structure)
        except StructureModelingError as exc:
            self.repository.update_file(
                file_id,
                owner_user_id,
                parse_status="parse_failed",
                parse_error_code=exc.code,
                parse_error_message=exc.message,
            )
            raise
        except Exception as exc:
            logger.exception("Structure parsing failed for file_id=%s", file_id)
            self.repository.update_file(
                file_id,
                owner_user_id,
                parse_status="parse_failed",
                parse_error_code="parse_failed",
                parse_error_message="文件格式或内容无法解析，请检查结构文件后重新上传。",
            )
            raise StructureModelingError("parse_failed", "文件格式或内容无法解析，请检查结构文件后重新上传。") from exc

    def get_file(self, file_id: str, owner_user_id: int) -> dict:
        return self.serialize_file(self._get_file_or_raise(file_id, owner_user_id))

    def list_files(self, owner_user_id: int, parse_status: str | None, page: int, page_size: int) -> dict:
        records, total = self.repository.list_files(owner_user_id, parse_status, (page - 1) * page_size, page_size)
        return {"items": [self.serialize_file(record) for record in records], "page": page, "page_size": page_size, "total": total}

    def get_structure(self, structure_id: str, owner_user_id: int, include_atomic_sites: bool) -> dict:
        structure = self._get_structure_or_raise(structure_id, owner_user_id)
        file_record = self._get_file_or_raise(structure.file_id, owner_user_id)
        return self.serialize_structure(structure, file_record, include_atomic_sites)

    def list_atomic_sites(self, structure_id: str, owner_user_id: int, page: int, page_size: int) -> dict:
        structure = self._get_structure_or_raise(structure_id, owner_user_id)
        start = (page - 1) * page_size
        return {
            "structure_id": structure_id,
            "items": structure.atomic_sites[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": structure.atom_count,
        }

    def suggest_active_sites(self, structure_id: str, owner_user_id: int) -> dict:
        structure = self._require_valid_structure(structure_id, owner_user_id)
        existing = self.repository.list_active_sites(structure_id, owner_user_id)
        suggestions = [site for site in existing if site.status == "suggested"]
        if not suggestions:
            for candidate in self._build_active_site_candidates(structure):
                suggestions.append(self.repository.create_active_site({"active_site_id": self._new_id("as"), "structure_id": structure_id, "owner_user_id": owner_user_id, **candidate}))
        return {
            "structure_id": structure_id,
            "suggestions": [self.serialize_active_site(site, structure) for site in suggestions],
        }

    def confirm_active_site(self, structure_id: str, owner_user_id: int, request: dict) -> dict:
        structure = self._require_valid_structure(structure_id, owner_user_id)
        center_indices = request["center_atom_indices"]
        neighbor_indices = request["neighbor_atom_indices"]
        self._validate_atom_indices(structure.atom_count, center_indices, "中心原子")
        self._validate_atom_indices(structure.atom_count, neighbor_indices, "邻居原子")
        if set(center_indices) & set(neighbor_indices):
            raise StructureModelingError("invalid_active_site", "中心原子和邻居原子不能重复。")

        suggested_id = request.get("site_id")
        if request["site_source"] == "suggested" and not suggested_id:
            raise StructureModelingError("active_site_required", "选择系统建议位点时必须提供 site_id。")
        if request["site_source"] == "manual" and suggested_id:
            raise StructureModelingError("invalid_active_site", "手工指定活性位点时不能同时提供 site_id。")
        if suggested_id:
            site = self._get_active_site_or_raise(suggested_id, owner_user_id)
            if site.structure_id != structure_id:
                raise StructureModelingError("invalid_active_site", "候选活性位点不属于当前结构。")
            if site.center_atom_indices != center_indices or site.neighbor_atom_indices != neighbor_indices:
                raise StructureModelingError("active_site_mismatch", "确认的原子索引必须与所选候选活性位点一致。")
            site = self.repository.update_active_site(
                site.active_site_id,
                owner_user_id,
                status="confirmed",
                detection_method="user_confirmed",
                selected_by_user_id=owner_user_id,
                confirmed_at=datetime.utcnow(),
                site_label=request["site_label"],
                user_note=request.get("user_note"),
            )
        else:
            site = self.repository.create_active_site(
                {
                    "active_site_id": self._new_id("as"),
                    "structure_id": structure_id,
                    "owner_user_id": owner_user_id,
                    "center_atom_indices": center_indices,
                    "neighbor_atom_indices": neighbor_indices,
                    "site_label": request["site_label"],
                    "site_type": "user_specified",
                    "detection_method": "user_confirmed",
                    "confidence": 1.0,
                    "status": "confirmed",
                    "selected_by_user_id": owner_user_id,
                    "confirmed_at": datetime.utcnow(),
                    "user_note": request.get("user_note"),
                }
            )
        self._set_workflow_status(structure.workflow_id, owner_user_id, "active_site_confirmed", "active_site_confirmed", {"active_site_id": site.active_site_id})
        return self.serialize_active_site(site, structure)

    def generate_adsorption_models(self, active_site_id: str, owner_user_id: int, request: dict) -> dict:
        active_site = self._get_active_site_or_raise(active_site_id, owner_user_id)
        if active_site.status != "confirmed":
            raise StructureModelingError("active_site_not_confirmed", "请先确认活性位点，再生成吸附初始构型。", 409)
        structure = self._require_valid_structure(active_site.structure_id, owner_user_id)
        species_list = request["polysulfide_species"]
        max_conformations = request["max_conformations_per_species"]
        distance = request["initial_distance_angstrom"]
        center = self._site_center(structure.atomic_sites, active_site.center_atom_indices)
        created_models: list[dict] = []
        warnings: list[str] = []
        for species in species_list:
            models = self._generate_species_models(
                structure=structure,
                active_site=active_site,
                species=species,
                center=center,
                initial_distance=distance,
                max_conformations=max_conformations,
            )
            created_models.extend(models)
            if len(models) < MIN_CONFORMATIONS_PER_SPECIES:
                warnings.append(f"{species} 仅生成 {len(models)} 个有效初始构型，未达到最少 {MIN_CONFORMATIONS_PER_SPECIES} 个。")
        workflow_status = "adsorption_models_generated" if not warnings else "partial_result"
        self._set_workflow_status(structure.workflow_id, owner_user_id, workflow_status, "adsorption_models_generated", {"active_site_id": active_site_id, "model_count": len(created_models), "warnings": warnings})
        return {"active_site_id": active_site_id, "status": "generated" if not warnings else "insufficient_conformations", "models": created_models, "warnings": warnings}

    def create_geometry_optimization(self, adsorption_model_id: str, owner_user_id: int, request: dict) -> dict:
        """Create a non-scoring geometry relaxation or record an imported optimized geometry."""
        adsorption_model = self._get_adsorption_model_or_raise(adsorption_model_id, owner_user_id)
        active_site = self._get_active_site_or_raise(adsorption_model.active_site_id, owner_user_id)
        structure = self._require_valid_structure(active_site.structure_id, owner_user_id)
        geometry_optimization_id = self._new_id("go")
        if request["calculation_mode"] == "geometry_only":
            atomic_sites = self._relax_initial_geometry(structure, adsorption_model)
            source_type = "geometry_only"
            method_name = "ASE Lennard-Jones frozen-host collision relaxation"
            imported_structure_id = None
            warnings = ["仅消除明显原子碰撞，不计算或声明 DFT 吸附能。", "该几何不能单独作为科研结论。"]
        else:
            atomic_sites, method_name = self._load_imported_optimized_geometry(structure, adsorption_model, owner_user_id, request)
            source_type = "imported_dft_result" if request["calculation_mode"] == "dft_optimized" else "imported_optimized"
            imported_structure_id = request["imported_structure_id"]
            warnings = ["优化方法和几何文件由用户导入，后续计算将保留该来源声明。"]
        artifact_path = self._write_json_artifact(
            geometry_optimization_id,
            {
                "adsorption_model_id": adsorption_model_id,
                "source_type": source_type,
                "method_name": method_name,
                "calculation_metadata": request.get("calculation_metadata", {}),
                "atomic_sites": atomic_sites,
            },
        )
        record = self.repository.create_geometry_optimization(
            {
                "geometry_optimization_id": geometry_optimization_id,
                "adsorption_model_id": adsorption_model_id,
                "owner_user_id": owner_user_id,
                "calculation_mode": request["calculation_mode"],
                "source_type": source_type,
                "method_name": method_name,
                "status": "completed",
                "geometry_artifact_path": str(artifact_path),
                "imported_structure_id": imported_structure_id,
                "warnings": warnings,
                "completed_at": datetime.utcnow(),
            }
        )
        self._set_workflow_status(structure.workflow_id, owner_user_id, "geometry_optimized", "geometry_optimization_completed", {"geometry_optimization_id": record.geometry_optimization_id, "source_type": source_type})
        return self.serialize_geometry_optimization(record)

    def build_quantum_region(self, adsorption_model_id: str, owner_user_id: int, request: dict) -> dict:
        adsorption_model = self._get_adsorption_model_or_raise(adsorption_model_id, owner_user_id)
        active_site = self._get_active_site_or_raise(adsorption_model.active_site_id, owner_user_id)
        structure = self._require_valid_structure(active_site.structure_id, owner_user_id)
        optimization = self._get_geometry_optimization_or_raise(request["geometry_optimization_id"], owner_user_id)
        if optimization.adsorption_model_id != adsorption_model_id or optimization.status != "completed":
            raise StructureModelingError("geometry_not_ready", "必须先完成当前吸附模型的几何优化，才能构建量子区。", 409)
        geometry = self._read_json_artifact(optimization.geometry_artifact_path)
        atomic_sites = geometry["atomic_sites"]
        host_atom_count = structure.atom_count
        if len(atomic_sites) < host_atom_count:
            raise StructureModelingError("invalid_optimized_geometry", "优化几何缺少材料骨架原子，无法构建量子区。")
        radius = request["radius_angstrom"]
        center = self._site_center(atomic_sites, active_site.center_atom_indices)
        host_positions = np.asarray([site["position_angstrom"] for site in atomic_sites[:host_atom_count]], dtype=float)
        distances = np.linalg.norm(host_positions - center, axis=1)
        required_indices = set(active_site.center_atom_indices + active_site.neighbor_atom_indices)
        adsorbate_indices = set(range(host_atom_count, len(atomic_sites)))
        region_indices = sorted({index for index, distance in enumerate(distances) if distance <= radius} | required_indices | adsorbate_indices)
        frozen_indices = [index for index in range(host_atom_count) if index not in set(region_indices)]
        warnings = ["该量子区引用已记录的优化几何，尚未执行电子结构计算。"]
        status = "quantum_region_built"
        if request.get("total_charge") is None or request.get("spin_multiplicity") is None:
            status = "needs_model_review"
            warnings.append("未确认总电荷或自旋多重度，不能进入活性空间计算。")
        quantum_region_id = self._new_id("qr")
        artifact_path = self._write_json_artifact(
            quantum_region_id,
            {"structure_id": structure.structure_id, "adsorption_model_id": adsorption_model_id, "geometry_optimization_id": optimization.geometry_optimization_id, "region_atom_indices": region_indices, "frozen_environment_atom_indices": frozen_indices, "radius_angstrom": radius, "embedding_method": "frozen_atoms", "atomic_sites": [atomic_sites[index] for index in region_indices]},
        )
        region = self.repository.create_quantum_region(
            {"quantum_region_id": quantum_region_id, "adsorption_model_id": adsorption_model_id, "geometry_optimization_id": optimization.geometry_optimization_id, "owner_user_id": owner_user_id, "region_atom_indices": region_indices, "frozen_environment_atom_indices": frozen_indices, "embedding_method": "frozen_atoms", "total_charge": request.get("total_charge"), "spin_multiplicity": request.get("spin_multiplicity"), "geometry_source_type": optimization.source_type, "geometry_method": optimization.method_name, "geometry_artifact_path": str(artifact_path), "status": status, "warnings": warnings}
        )
        self._set_workflow_status(structure.workflow_id, owner_user_id, status, "quantum_region_built", {"quantum_region_id": region.quantum_region_id})
        return self.serialize_quantum_region(region)

    def get_structure_workflow(self, workflow_id: str, owner_user_id: int) -> dict:
        resources = self.repository.get_workflow_resources(workflow_id, owner_user_id)
        if resources is None:
            raise StructureModelingError("workflow_not_found", "未找到结构建模工作流。", 404)
        workflow = resources["workflow"]
        payload = workflow.payload or {}
        return {
            "workflow_id": workflow.workflow_id,
            "structure_id": workflow.structure_id,
            "status": workflow.status,
            # 文献复现输入必须沿链路保留来源，避免被 UI 或下游误标为用户自建模型。
            "data_source": payload.get("data_source", "user_uploaded_structure"),
            "scientific_validation_level": payload.get("scientific_validation_level"),
            "geometry_status": payload.get("geometry_status"),
            "payload": payload,
            "stages": self._build_workflow_stages(resources),
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
        }

    def list_structure_workflows(
        self,
        owner_user_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        records, total = self.repository.list_workflows(
            owner_user_id,
            status,
            (page - 1) * page_size,
            page_size,
        )
        return {
            "items": [self._serialize_workflow_list_item(record) for record in records],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_structure_artifact_metadata(
        self,
        workflow_id: str,
        artifact_id: str,
        owner_user_id: int,
    ) -> dict:
        artifact = self._resolve_workflow_artifact(workflow_id, artifact_id, owner_user_id)
        return {key: value for key, value in artifact.items() if key != "path"}

    def resolve_structure_artifact_download(
        self,
        workflow_id: str,
        artifact_id: str,
        owner_user_id: int,
    ) -> tuple[Path, str, str]:
        artifact = self._resolve_workflow_artifact(workflow_id, artifact_id, owner_user_id)
        return artifact["path"], artifact["filename"], artifact["media_type"]

    def create_benchmark_case(self, owner_user_id: int, request: dict) -> dict:
        """Persist a versioned research input package without inventing a unique Fe-N4 spin state."""
        structure = self._require_valid_structure(request["structure_id"], owner_user_id)
        if (
            "fe" in request["catalyst_model_type"].lower()
            and "n4" in request["catalyst_model_type"].lower()
            and (structure.atom_count <= 5 or "C" not in structure.elements)
        ):
            raise StructureModelingError(
                "benchmark_structure_too_small",
                "Fe-N4 科研基准必须包含碳载体或等价边界环境，不能使用仅 5 原子的 FeN4 小团簇。",
                409,
            )
        adsorbate_symbols, adsorbate_positions = self._polysulfide_template(request["adsorbate_species"])
        artifact_path = self._write_json_artifact(
            self._new_id("benchmark_structure"),
            {
                "structure_id": structure.structure_id,
                "atomic_sites": structure.atomic_sites,
                "source": "user_uploaded_structure",
                "version": request["version"],
                "adsorbate_initial_configurations": [
                    {
                        "conformation_id": f"{request['adsorbate_species'].lower()}_template_{index + 1}",
                        "source_type": "generated_initial_template",
                        "atomic_sites": [
                            {
                                "index": site_index,
                                "element": symbol,
                                "position_angstrom": [float(value) for value in adsorbate_positions[site_index]],
                            }
                            for site_index, symbol in enumerate(adsorbate_symbols)
                        ],
                    }
                    for index in range(MIN_CONFORMATIONS_PER_SPECIES)
                ],
            },
        )
        record = self.repository.create_benchmark_case(
            {
                "benchmark_case_id": self._new_id("benchmark"),
                "owner_user_id": owner_user_id,
                "title": request["title"],
                "catalyst_model_type": request["catalyst_model_type"],
                "adsorbate_species": request["adsorbate_species"],
                "structure_artifact_path": str(artifact_path),
                "structure_origin": request["structure_origin"],
                "geometry_status": request["geometry_status"],
                "total_charge": request["total_charge"],
                "spin_candidate_definitions": request["spin_candidate_definitions"],
                "dft_metadata": request["dft_metadata"],
                "version": request["version"],
                "status": "ready_for_spin_comparison",
            }
        )
        return self.serialize_benchmark_case(record)

    def submit_electronic_structure_candidates(self, quantum_region_id: str, owner_user_id: int, request: dict) -> dict:
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None:
            raise StructureModelingError("quantum_region_not_found", "未找到量子区或无权访问。", 404)
        if region.status not in {"quantum_region_built", "needs_model_review"}:
            raise StructureModelingError("quantum_region_not_ready", "量子区尚未准备好进行自旋候选比较。", 409)
        if request.get("benchmark_case_id") and self.repository.get_benchmark_case(request["benchmark_case_id"], owner_user_id) is None:
            raise StructureModelingError("benchmark_case_not_found", "未找到科研基准案例或无权访问。", 404)
        if request["spin_strategy"] == "explicit" and not request["spin_multiplicities"]:
            raise StructureModelingError("spin_multiplicities_required", "显式自旋策略必须提供至少一个自旋多重度。")
        task_id = task_manager.submit(
            self._generate_electronic_structure_candidates,
            quantum_region_id,
            owner_user_id,
            request,
        )
        return {"task_id": task_id, "status": "queued", "message": "多自旋电子结构候选已提交后台执行。"}

    def get_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_electronic_structure_candidate(candidate_id, owner_user_id)
        if record is None:
            raise StructureModelingError("electronic_structure_candidate_not_found", "未找到电子结构候选或无权访问。", 404)
        return self.serialize_electronic_structure_candidate(record)

    def confirm_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int, request: dict) -> dict:
        candidate = self.repository.get_electronic_structure_candidate(candidate_id, owner_user_id)
        if candidate is None:
            raise StructureModelingError("electronic_structure_candidate_not_found", "未找到电子结构候选或无权访问。", 404)
        if candidate.quality_status != "eligible_for_confirmation":
            raise StructureModelingError("electronic_structure_candidate_not_eligible", "该候选未通过收敛或自旋质量检查，不能确认。", 409)
        confirmed = self.repository.update_electronic_structure_candidate(
            candidate_id,
            owner_user_id,
            quality_status="confirmed",
            confirmed_by_user_id=owner_user_id,
            confirmed_at=datetime.utcnow(),
        )
        region = self.repository.get_quantum_region(candidate.quantum_region_id, owner_user_id)
        self.repository.update_quantum_region(
            region.quantum_region_id,
            owner_user_id,
            total_charge=confirmed.total_charge,
            spin_multiplicity=confirmed.spin_multiplicity,
            status="quantum_region_built",
            warnings=list(region.warnings or []) + [f"已确认电子结构候选 {confirmed.candidate_id}。"],
        )
        if confirmed.benchmark_case_id:
            self.repository.update_benchmark_case(
                confirmed.benchmark_case_id,
                owner_user_id,
                accepted_reference_id=confirmed.candidate_id,
                status="electronic_structure_confirmed",
            )
        return {**self.serialize_electronic_structure_candidate(confirmed), "confirmation_note": request.get("confirmation_note")}

    def import_dft_result(self, adsorption_model_id: str, owner_user_id: int, request: dict) -> dict:
        """Record external DFT evidence and only promote complete, comparable input to dft_optimized."""
        adsorption_model = self._get_adsorption_model_or_raise(adsorption_model_id, owner_user_id)
        metadata = request["calculation_metadata"]
        energy_bundle = request["energy_bundle"]
        required_metadata = {
            "software",
            "software_version",
            "calculation_type",
            "functional",
            "basis_or_pseudopotential",
            "dispersion",
            "spin_polarization",
            "total_charge",
            "spin_multiplicity",
            "convergence",
            "total_energy",
            "energy_unit",
        }
        structure = self._require_valid_structure(request["optimized_structure_id"], owner_user_id) if request.get("optimized_structure_id") else None
        missing = self._missing_dft_metadata(metadata, required_metadata)
        warnings = [f"缺少 DFT 元数据：{', '.join(missing)}。"] if missing else []
        if structure is not None:
            self._validate_imported_dft_geometry(adsorption_model, structure, owner_user_id)
        elif "优化后结构" not in warnings:
            warnings.append("缺少优化后结构，不能标记为 dft_optimized。")
        status = "dft_optimized" if structure is not None and not missing else "metadata_incomplete"
        geometry_artifact_path = None
        geometry_optimization_id = None
        if status == "dft_optimized":
            geometry_artifact_path = self._write_json_artifact(
                self._new_id("dft_geometry"),
                {"source_type": "imported_dft_result", "atomic_sites": structure.atomic_sites, "calculation_metadata": metadata},
            )
            geometry_record = self.repository.create_geometry_optimization(
                {
                    "geometry_optimization_id": self._new_id("go"),
                    "adsorption_model_id": adsorption_model_id,
                    "owner_user_id": owner_user_id,
                    "calculation_mode": "dft_optimized",
                    "source_type": "imported_dft_result",
                    "method_name": f"{metadata['software']} {metadata['functional']}",
                    "status": "completed",
                    "geometry_artifact_path": str(geometry_artifact_path),
                    "imported_structure_id": structure.structure_id,
                    "warnings": ["外部 DFT 导入结果，未由平台直接执行。"],
                    "completed_at": datetime.utcnow(),
                }
            )
            geometry_optimization_id = geometry_record.geometry_optimization_id
        if status != "dft_optimized":
            adsorption_energy = None
            comparability_warnings = warnings + ["DFT 导入元数据或优化结构不完整；仅归档，不生成可比较的吸附能。"]
        else:
            adsorption_energy, comparability_warnings = self._validate_adsorption_energy_bundle(energy_bundle)
        dft_import_id = self._new_id("dft")
        source_artifact_path = self._write_json_artifact(
            dft_import_id,
            {
                "source_type": "external_dft_import",
                "calculation_metadata": metadata,
                "energy_bundle": energy_bundle,
                "optimized_structure_id": structure.structure_id if structure else None,
            },
        )
        record = self.repository.create_dft_import(
            {
                "dft_import_id": dft_import_id,
                "adsorption_model_id": adsorption_model_id,
                "owner_user_id": owner_user_id,
                "optimized_structure_id": structure.structure_id if structure else None,
                "status": status,
                "calculation_metadata": metadata,
                "energy_bundle": energy_bundle,
                "adsorption_energy_hartree": adsorption_energy,
                "comparability_warnings": comparability_warnings,
                "geometry_artifact_path": str(geometry_artifact_path) if geometry_artifact_path else None,
                "source_artifact_path": str(source_artifact_path),
            }
        )
        return {**self.serialize_dft_import(record), "geometry_optimization_id": geometry_optimization_id}

    def generate_classical_reference(self, hamiltonian_id: str, owner_user_id: int) -> dict:
        """Generate a real PySCF FCI reference only when the confirmed active space is small and closed-shell."""
        hamiltonian = self.repository.get_fermionic_hamiltonian(hamiltonian_id, owner_user_id)
        if hamiltonian is None:
            raise StructureModelingError("hamiltonian_not_found", "未找到费米子 Hamiltonian 或无权访问。", 404)
        active_space = self.repository.get_active_space(hamiltonian.active_space_id, owner_user_id)
        region = self.repository.get_quantum_region(active_space.quantum_region_id, owner_user_id)
        artifact = self._read_json_artifact(region.geometry_artifact_path)
        try:
            result = self.electronic_structure_adapter.calculate_classical_reference(
                {
                    "atomic_sites": artifact["atomic_sites"],
                    "total_charge": region.total_charge,
                    "spin_multiplicity": region.spin_multiplicity,
                    "basis_set": hamiltonian.basis_set,
                    "active_electrons": active_space.active_electrons,
                    "orbital_indices": active_space.orbital_indices,
                }
            )
        except ElectronicStructureRuntimeError as exc:
            raise StructureModelingError("classical_reference_failed", f"经典 FCI 参考计算失败：{exc}", 503) from exc
        reference_id = self._new_id("classical_ref")
        artifact_path = self._write_json_artifact(reference_id, result)
        record = self.repository.create_classical_reference(
            {
                "reference_id": reference_id,
                "fermionic_hamiltonian_id": hamiltonian_id,
                "owner_user_id": owner_user_id,
                "method": result.get("method", "PySCF_FCI_active_space"),
                "energy_hartree": result.get("energy_hartree"),
                "status": result["status"],
                "artifact_path": str(artifact_path),
            }
        )
        return self.serialize_classical_reference(record, result.get("message"))

    def get_dft_import(self, dft_import_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_dft_import(dft_import_id, owner_user_id)
        if record is None:
            raise StructureModelingError("dft_import_not_found", "未找到 DFT 导入记录或无权访问。", 404)
        return self.serialize_dft_import(record)

    def import_materials_cloud_benchmark(self, owner_user_id: int, request: dict) -> dict:
        """Import the published FeN4C66-Li2S4 source verbatim after checksum validation."""
        if request["dataset_url"].rstrip("/") != MATERIALS_CLOUD_DATASET_URL:
            raise StructureModelingError("unsupported_dataset_source", "仅允许导入已审核的 Materials Cloud 文献数据集。", 422)
        if self.repository.get_research_benchmark_by_key(request["benchmark_key"]):
            raise StructureModelingError("research_benchmark_exists", "该文献基准已导入，不能覆盖原始 Artifact。", 409)
        benchmark_root = RESEARCH_BENCHMARK_ROOT / request["benchmark_key"]
        raw_root = benchmark_root / "raw"
        raw_root.mkdir(parents=True, exist_ok=True)
        downloaded: dict[str, Path] = {}
        try:
            for filename, expected_md5 in MATERIALS_CLOUD_FILES.items():
                target = raw_root / filename
                self._download_materials_cloud_file(filename, target)
                actual_md5 = self._hash_file(target, "md5")
                if actual_md5.lower() != expected_md5:
                    raise StructureModelingError(
                        "research_benchmark_checksum_mismatch",
                        f"{filename} 的 MD5 校验失败，已拒绝导入。",
                        422,
                    )
                downloaded[filename] = target
        except StructureModelingError:
            shutil.rmtree(benchmark_root, ignore_errors=True)
            raise
        except (OSError, URLError) as exc:
            shutil.rmtree(benchmark_root, ignore_errors=True)
            raise StructureModelingError("research_benchmark_download_failed", "无法下载 Materials Cloud 官方数据包。", 503) from exc

        param_metadata = self._parse_castep_param(downloaded["fe1n4c66-li2s.param"])
        cell_metadata = self._parse_castep_cell(downloaded["fe1n4c66-li2s.cell"])
        benchmark = self.repository.create_research_benchmark(
            {
                "benchmark_id": self._new_id("research_benchmark"),
                "benchmark_key": request["benchmark_key"],
                "imported_by_user_id": owner_user_id,
                "title": "FeN4C66-Li2S4 Materials Cloud literature reproduction baseline",
                "source_url": MATERIALS_CLOUD_DATASET_URL,
                "source_doi": "10.1002/qua.26956",
                "source_license": request["source_license"],
                "source_dataset_version": "materialscloud:2022.48 v2",
                "material_model": "periodic_fe_n4_c66",
                "adsorbate": request["adsorbate"],
                "scientific_validation_level": "reproduction_baseline_only",
                "status": "imported",
                "dft_metadata": {**param_metadata, **cell_metadata},
            }
        )
        if request["retain_raw_artifacts"]:
            for filename, path in downloaded.items():
                self.repository.create_research_benchmark_artifact(
                    {
                        "artifact_id": self._new_id("research_artifact"),
                        "benchmark_id": benchmark.benchmark_id,
                        "artifact_role": "raw_dataset_file",
                        "original_filename": filename,
                        "checksum_md5": self._hash_file(path, "md5"),
                        "checksum_sha256": self._hash_file(path, "sha256"),
                        "storage_path": str(path),
                        "artifact_metadata": {"source_url": f"{MATERIALS_CLOUD_FILES_URL}/{filename}?download=1"},
                    }
                )
        candidates = self._extract_literature_candidates(downloaded["FeLIPS_data.tar.gz"], benchmark_root)
        if not candidates:
            raise StructureModelingError("research_benchmark_candidates_missing", "公开数据包中未找到 FeN4C66-Li2S4 候选构型。", 422)
        ranked_candidates = sorted(candidates, key=lambda item: item["source_energy"])
        for rank, candidate in enumerate(ranked_candidates, start=1):
            artifact_path = self._write_json_artifact(
                self._new_id("literature_candidate"),
                candidate,
            )
            self.repository.create_research_benchmark_candidate(
                {
                    "candidate_id": self._new_id("literature_candidate"),
                    "benchmark_id": benchmark.benchmark_id,
                    "source_candidate_id": candidate["source_candidate_id"],
                    "source_energy": candidate["source_energy"],
                    "source_energy_unit": "dataset_native_unit_not_confirmed",
                    "coordinate_artifact_path": str(artifact_path),
                    "source_metadata": candidate["source_metadata"],
                    "priority_rank": rank,
                    "status": "literature_candidate",
                }
            )
        if not request["retain_raw_artifacts"]:
            # The database still retains checksum and source URL; only local raw copies are removed by explicit request.
            shutil.rmtree(raw_root, ignore_errors=True)
        return self.serialize_research_benchmark(benchmark, len(ranked_candidates))

    def get_research_benchmark(self, benchmark_id: str) -> dict:
        benchmark = self.repository.get_research_benchmark(benchmark_id)
        if benchmark is None:
            raise StructureModelingError("research_benchmark_not_found", "未找到文献基准。", 404)
        candidate_count = len(self.repository.list_research_benchmark_candidates(benchmark_id))
        return self.serialize_research_benchmark(benchmark, candidate_count)

    def list_research_benchmarks(self, benchmark_key: str | None = None) -> dict:
        """Discover imported immutable benchmarks without exposing storage locations."""
        records = self.repository.list_research_benchmarks(benchmark_key)
        return {
            "items": [
                self.serialize_research_benchmark(
                    record,
                    len(self.repository.list_research_benchmark_candidates(record.benchmark_id)),
                )
                for record in records
            ]
        }

    def list_research_benchmark_candidates(self, benchmark_id: str) -> dict:
        if self.repository.get_research_benchmark(benchmark_id) is None:
            raise StructureModelingError("research_benchmark_not_found", "未找到文献基准。", 404)
        return {
            "benchmark_id": benchmark_id,
            "items": [self.serialize_research_benchmark_candidate(item) for item in self.repository.list_research_benchmark_candidates(benchmark_id)],
        }

    def get_research_benchmark_candidate_artifact_metadata(self, benchmark_id: str, candidate_id: str) -> dict:
        """Expose coordinate Artifact metadata for an imported public candidate, never its storage path or bytes."""
        candidate = self.repository.get_research_benchmark_candidate(benchmark_id, candidate_id)
        if candidate is None:
            raise StructureModelingError("research_benchmark_candidate_not_found", "未找到文献基准候选。", 404)
        artifact_path = Path(candidate.coordinate_artifact_path).resolve()
        if not self._is_path_within(artifact_path, STRUCTURE_ARTIFACT_ROOT.resolve()) or not artifact_path.is_file():
            raise StructureModelingError("research_benchmark_artifact_unavailable", "候选坐标 Artifact 不可读取。", 404)
        return {
            "artifact_id": Path(candidate.coordinate_artifact_path).stem,
            "artifact_role": "literature_candidate_geometry",
            "resource_type": "research_benchmark_candidate",
            "resource_id": candidate.candidate_id,
            "filename": artifact_path.name,
            "media_type": "application/json",
            "size_bytes": artifact_path.stat().st_size,
            "checksum_sha256": self._hash_file(artifact_path, "sha256"),
            "download_available_after_workflow_selection": True,
        }

    def select_research_benchmark_candidate(self, benchmark_id: str, candidate_id: str, owner_user_id: int) -> dict:
        """Copy an immutable literature frame into the caller's normal structure workflow with provenance retained."""
        benchmark = self.repository.get_research_benchmark(benchmark_id)
        candidate = self.repository.get_research_benchmark_candidate(benchmark_id, candidate_id)
        if benchmark is None or candidate is None:
            raise StructureModelingError("research_benchmark_candidate_not_found", "未找到文献基准候选。", 404)
        payload = self._read_json_artifact(candidate.coordinate_artifact_path)
        all_sites = payload["atomic_sites"]
        host_sites = [site for site in all_sites if site["element"] not in {"Li", "S"}]
        adsorbate_sites = [site for site in all_sites if site["element"] in {"Li", "S"}]
        if Counter(site["element"] for site in adsorbate_sites) != Counter({"Li": 2, "S": 4}):
            raise StructureModelingError("literature_adsorbate_invalid", "文献候选不包含完整 Li2S4，不能建立复现工作流。", 422)
        host_sites = [
            {"index": index, "element": site["element"], "position_angstrom": site["position_angstrom"]}
            for index, site in enumerate(host_sites)
        ]
        adsorbate_sites = [
            {"index": index, "element": site["element"], "position_angstrom": site["position_angstrom"]}
            for index, site in enumerate(adsorbate_sites)
        ]
        xyz_content = self._to_extxyz(host_sites, payload["source_metadata"].get("lattice_matrix_angstrom"), None)
        file_result = self.upload_structure_file(
            owner_user_id=owner_user_id,
            material_name="FeN4C66-Li2S4 literature reproduction input",
            material_family="literature_open_dataset",
            description=f"不可变文献候选 {candidate.source_candidate_id}，来源 {benchmark.source_doi}。",
            original_filename=f"{benchmark.benchmark_key}-{candidate.source_candidate_id}.xyz",
            content=xyz_content.encode("utf-8"),
        )
        parsed = self.parse_structure_file(file_result["file_id"], owner_user_id)
        suggested_sites = self.suggest_active_sites(parsed["structure_id"], owner_user_id)["suggestions"]
        fe_site = next((site for site in suggested_sites if site["site_type"] == "transition_metal_center"), None)
        if fe_site is None:
            raise StructureModelingError("literature_active_site_missing", "文献宿主中未找到 Fe-N4 活性位点。", 422)
        confirmed_site = self.confirm_active_site(
            parsed["structure_id"],
            owner_user_id,
            {
                "site_source": "suggested",
                "site_id": fe_site["active_site_id"],
                "center_atom_indices": fe_site["center_atom_indices"],
                "neighbor_atom_indices": fe_site["neighbor_atom_indices"],
                "site_label": "Fe-N4 literature reproduction site",
                "user_note": f"从文献候选 {candidate.source_candidate_id} 创建。",
            },
        )
        adsorption_model_id = self._new_id("literature_adsorption")
        adsorption_artifact_path = self._write_json_artifact(
            adsorption_model_id,
            {
                "source_type": "literature_open_dataset",
                "research_benchmark_id": benchmark_id,
                "research_benchmark_candidate_id": candidate_id,
                "atomic_sites": adsorbate_sites,
            },
        )
        adsorption_model = self.repository.create_adsorption_model(
            {
                "adsorption_model_id": adsorption_model_id,
                "active_site_id": confirmed_site["active_site_id"],
                "owner_user_id": owner_user_id,
                "polysulfide_species": "Li2S4",
                "placement_strategy": "literature_optimized_candidate",
                "initial_distance_angstrom": self._minimum_cross_distance(
                    np.asarray([site["position_angstrom"] for site in host_sites], dtype=float),
                    np.asarray([site["position_angstrom"] for site in adsorbate_sites], dtype=float),
                ),
                "geometry_quality_score": 1.0,
                "geometry_artifact_path": str(adsorption_artifact_path),
                "status": "literature_selected",
                "warnings": ["文献优化候选，仅用于复现基准，不等同于化学负责人批准的最终构型。"],
            }
        )
        geometry_optimization_id = self._new_id("literature_geometry")
        geometry_artifact_path = self._write_json_artifact(
            geometry_optimization_id,
            {
                "source_type": "literature_open_dataset",
                "research_benchmark_id": benchmark_id,
                "research_benchmark_candidate_id": candidate_id,
                "source_energy": candidate.source_energy,
                "source_energy_unit": candidate.source_energy_unit,
                "atomic_sites": [
                    *host_sites,
                    *[
                        {
                            "index": len(host_sites) + site["index"],
                            "element": site["element"],
                            "position_angstrom": site["position_angstrom"],
                        }
                        for site in adsorbate_sites
                    ],
                ],
            },
        )
        geometry_record = self.repository.create_geometry_optimization(
            {
                "geometry_optimization_id": geometry_optimization_id,
                "adsorption_model_id": adsorption_model.adsorption_model_id,
                "owner_user_id": owner_user_id,
                "calculation_mode": "literature_optimized_candidate",
                "source_type": "literature_open_dataset",
                "method_name": "CASTEP PBE D2/G06 literature candidate",
                "status": "completed",
                "geometry_artifact_path": str(geometry_artifact_path),
                "warnings": ["SPIN_FIX 和初始磁矩保留为文献原始设置，未解释为局部团簇最终自旋。"],
                "completed_at": datetime.utcnow(),
            }
        )
        workflow = self.repository.get_workflow(parsed["workflow_id"], owner_user_id)
        workflow_payload = dict(workflow.payload or {})
        workflow_payload.update(
            {
                "data_source": "literature_open_dataset",
                "research_benchmark_id": benchmark_id,
                "research_benchmark_candidate_id": candidate_id,
                "scientific_validation_level": "reproduction_baseline_only",
                "source_doi": benchmark.source_doi,
            }
        )
        self.repository.update_workflow(
            workflow.workflow_id,
            owner_user_id,
            status="literature_reproduction_geometry_ready",
            payload=workflow_payload,
        )
        selection = self.repository.create_research_benchmark_selection(
            {
                "selection_id": self._new_id("research_selection"),
                "benchmark_id": benchmark_id,
                "candidate_id": candidate_id,
                "owner_user_id": owner_user_id,
                "structure_id": parsed["structure_id"],
                "workflow_id": parsed["workflow_id"],
                "status": "literature_reproduction_input_selected",
            }
        )
        return {
            "selection_id": selection.selection_id,
            "benchmark_id": benchmark_id,
            "candidate_id": candidate_id,
            "structure_id": selection.structure_id,
            "workflow_id": selection.workflow_id,
            "adsorption_model_id": adsorption_model.adsorption_model_id,
            "geometry_optimization_id": geometry_record.geometry_optimization_id,
            "data_source": "literature_open_dataset",
            "scientific_validation_level": "reproduction_baseline_only",
            "status": selection.status,
        }

    def submit_direct_dft_calculation(self, adsorption_model_id: str, owner_user_id: int, request: dict) -> dict:
        """Queue a bounded direct DFT calculation through an engine adapter, never a shell command from the API."""
        adsorption_model = self._get_adsorption_model_or_raise(adsorption_model_id, owner_user_id)
        if request["engine_name"] not in self.dft_adapters:
            raise StructureModelingError("unsupported_dft_engine", "当前不支持该 DFT 引擎。")
        if request["calculation_type"] == "neb":
            raise StructureModelingError("neb_not_implemented", "当前未实现真实 NEB 多图像计算，已拒绝提交。", 422)
        required_metadata = {
            "software_version",
            "functional",
            "basis_or_pseudopotential",
            "dispersion",
            "spin_polarization",
            "total_charge",
            "spin_multiplicity",
            "convergence",
        }
        missing = self._missing_dft_metadata(request["calculation_metadata"], required_metadata)
        if missing:
            raise StructureModelingError("dft_metadata_required", f"直接 DFT 任务缺少元数据：{', '.join(missing)}。")
        atomic_sites = self._direct_dft_atomic_sites(adsorption_model, owner_user_id)
        self._validate_direct_dft_electronic_state(request, atomic_sites)
        adapter = self.dft_adapters[request["engine_name"]]
        runtime_status = adapter.runtime_status() if hasattr(adapter, "runtime_status") else {"ready": True}
        if not runtime_status["ready"]:
            raise StructureModelingError(
                "dft_engine_unavailable",
                f"{request['engine_name']} 可执行环境未就绪，请部署经化学负责人确认的引擎与科学参数。",
                503,
            )
        if request["timeout_seconds"] > settings.DFT_MAX_TIMEOUT_SECONDS:
            raise StructureModelingError("dft_timeout_exceeds_limit", "请求超时上限超过服务端配置。")
        calculation_id = self._new_id("dft_calc")
        record = self.repository.create_dft_calculation(
            {
                "dft_calculation_id": calculation_id,
                "adsorption_model_id": adsorption_model_id,
                "owner_user_id": owner_user_id,
                "engine_name": request["engine_name"],
                "calculation_type": request["calculation_type"],
                "calculation_metadata": request["calculation_metadata"],
                "engine_settings": request["engine_settings"],
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": request["max_attempts"],
                "timeout_seconds": request["timeout_seconds"],
            }
        )
        task_id = task_manager.submit_cancellable(self._run_direct_dft_calculation, calculation_id, owner_user_id)
        record = self.repository.update_dft_calculation(calculation_id, owner_user_id, task_id=task_id)
        return self.serialize_dft_calculation(record)

    def get_dft_runtime_status(self) -> dict:
        engines = {}
        for engine_name, adapter in self.dft_adapters.items():
            status = adapter.runtime_status() if hasattr(adapter, "runtime_status") else {"ready": True}
            engines[engine_name] = {
                **status,
                "scientific_configuration_status": "requires_chemistry_lead_approval",
            }
        return {
            "direct_dft_available": any(status["ready"] for status in engines.values()),
            "supported_calculation_types": ["geometry_optimization", "single_point", "adsorption_energy"],
            "neb_supported": False,
            "engines": engines,
            "message": "引擎可执行文件就绪不代表科学参数已获批准；赝势、泛函和自旋设置仍需化学负责人确认。",
        }

    @staticmethod
    def _validate_direct_dft_electronic_state(request: dict, atomic_sites: list[dict]) -> None:
        metadata = request["calculation_metadata"]
        spin_multiplicity = metadata["spin_multiplicity"]
        spin_polarization = metadata["spin_polarization"]
        if spin_multiplicity > 1 and not spin_polarization:
            raise StructureModelingError(
                "dft_spin_configuration_invalid",
                "开壳层 DFT 任务必须启用 spin_polarization。",
            )
        if request["engine_name"] != "quantum_espresso" or not spin_polarization:
            return
        magnetization = metadata.get("initial_magnetization_by_element") or {}
        elements = {site["element"] for site in atomic_sites}
        missing_elements = sorted(elements - set(magnetization))
        if missing_elements:
            raise StructureModelingError(
                "dft_initial_magnetization_required",
                f"Quantum ESPRESSO 缺少元素初始磁化：{', '.join(missing_elements)}。",
            )
        invalid_elements = sorted(
            element
            for element in elements
            if isinstance(magnetization[element], bool)
            or not isinstance(magnetization[element], (int, float))
            or not math.isfinite(float(magnetization[element]))
        )
        if invalid_elements:
            raise StructureModelingError(
                "dft_initial_magnetization_invalid",
                f"Quantum ESPRESSO 元素初始磁化必须是有限数值：{', '.join(invalid_elements)}。",
            )
        if not any(abs(float(magnetization[element])) > 0 for element in elements):
            raise StructureModelingError(
                "dft_initial_magnetization_required",
                "Quantum ESPRESSO 自旋极化任务至少需要一个非零元素初始磁化。",
            )

    def get_direct_dft_calculation(self, dft_calculation_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_dft_calculation(dft_calculation_id, owner_user_id)
        if record is None:
            raise StructureModelingError("dft_calculation_not_found", "未找到 DFT 计算任务或无权访问。", 404)
        return self.serialize_dft_calculation(record)

    def cancel_direct_dft_calculation(self, dft_calculation_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_dft_calculation(dft_calculation_id, owner_user_id)
        if record is None:
            raise StructureModelingError("dft_calculation_not_found", "未找到 DFT 计算任务或无权访问。", 404)
        if record.status in {"completed", "failed", "cancelled"}:
            raise StructureModelingError("dft_calculation_not_cancellable", "已结束的 DFT 任务不能取消。", 409)
        task_manager.cancel(record.task_id) if record.task_id else None
        updated = self.repository.update_dft_calculation(
            dft_calculation_id,
            owner_user_id,
            cancellation_requested=1,
            status="cancelling",
        )
        return self.serialize_dft_calculation(updated)

    def retry_direct_dft_calculation(self, dft_calculation_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_dft_calculation(dft_calculation_id, owner_user_id)
        if record is None:
            raise StructureModelingError("dft_calculation_not_found", "未找到 DFT 计算任务或无权访问。", 404)
        if record.status not in {"failed", "cancelled"}:
            raise StructureModelingError("dft_calculation_not_retryable", "只有失败或已取消的 DFT 任务可以重试。", 409)
        if record.attempt_count >= record.max_attempts:
            raise StructureModelingError("dft_retry_limit_reached", "已达到该任务的最大重试次数。", 409)
        if record.calculation_type == "neb":
            raise StructureModelingError("neb_not_implemented", "当前未实现真实 NEB 多图像计算，已拒绝重试。", 422)
        adapter = self.dft_adapters[record.engine_name]
        runtime_status = adapter.runtime_status() if hasattr(adapter, "runtime_status") else {"ready": True}
        if not runtime_status["ready"]:
            raise StructureModelingError(
                "dft_engine_unavailable",
                f"{record.engine_name} 可执行环境未就绪，不能重试。",
                503,
            )
        adsorption_model = self._get_adsorption_model_or_raise(record.adsorption_model_id, owner_user_id)
        atomic_sites = self._direct_dft_atomic_sites(adsorption_model, owner_user_id)
        self._validate_direct_dft_electronic_state(
            {
                "engine_name": record.engine_name,
                "calculation_metadata": record.calculation_metadata,
            },
            atomic_sites,
        )
        task_id = task_manager.submit_cancellable(self._run_direct_dft_calculation, dft_calculation_id, owner_user_id)
        updated = self.repository.update_dft_calculation(
            dft_calculation_id,
            owner_user_id,
            task_id=task_id,
            cancellation_requested=0,
            status="queued",
            error_message=None,
        )
        return self.serialize_dft_calculation(updated)

    def _run_direct_dft_calculation(self, is_cancel_requested, dft_calculation_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_dft_calculation(dft_calculation_id, owner_user_id)
        if record is None:
            raise StructureModelingError("dft_calculation_not_found", "后台任务未找到 DFT 计算记录。", 404)
        if record.cancellation_requested or is_cancel_requested():
            updated = self.repository.update_dft_calculation(
                dft_calculation_id,
                owner_user_id,
                status="cancelled",
                completed_at=datetime.utcnow(),
            )
            return self.serialize_dft_calculation(updated)
        adsorption_model = self._get_adsorption_model_or_raise(record.adsorption_model_id, owner_user_id)
        atomic_sites = self._direct_dft_atomic_sites(adsorption_model, owner_user_id)
        adapter = self.dft_adapters[record.engine_name]
        next_attempt = record.attempt_count + 1
        updated = self.repository.update_dft_calculation(
            dft_calculation_id,
            owner_user_id,
            status="running",
            attempt_count=next_attempt,
        )
        try:
            result = adapter.run(
                {
                    "atomic_sites": atomic_sites,
                    "calculation_type": record.calculation_type,
                    "calculation_metadata": record.calculation_metadata,
                    "engine_settings": record.engine_settings,
                },
                DFT_RUN_ROOT / dft_calculation_id / f"attempt_{next_attempt}",
                record.timeout_seconds,
                is_cancel_requested,
            )
        except DftExecutionCancelled as exc:
            updated = self.repository.update_dft_calculation(
                dft_calculation_id,
                owner_user_id,
                status="cancelled",
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
            return self.serialize_dft_calculation(updated)
        except DftEngineError as exc:
            updated = self.repository.update_dft_calculation(
                dft_calculation_id,
                owner_user_id,
                status="failed",
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
            return self.serialize_dft_calculation(updated)
        metadata = {
            **record.calculation_metadata,
            "software": record.engine_name,
            "total_energy": result["parsed_result"].get("total_energy_hartree"),
            "energy_unit": result["parsed_result"].get("energy_unit", "Hartree"),
        }
        parsed_result = dict(result["parsed_result"])
        if record.calculation_type == "geometry_optimization" and parsed_result.get("optimized_atomic_sites"):
            geometry_artifact_path = self._write_json_artifact(
                self._new_id("direct_dft_geometry"),
                {
                    "source_type": "direct_dft_engine",
                    "engine_name": record.engine_name,
                    "calculation_metadata": metadata,
                    "atomic_sites": parsed_result["optimized_atomic_sites"],
                },
            )
            geometry_record = self.repository.create_geometry_optimization(
                {
                    "geometry_optimization_id": self._new_id("go"),
                    "adsorption_model_id": record.adsorption_model_id,
                    "owner_user_id": owner_user_id,
                    "calculation_mode": "dft_optimized",
                    "source_type": "direct_dft_engine",
                    "method_name": f"{record.engine_name} {metadata['functional']}",
                    "status": "completed",
                    "geometry_artifact_path": str(geometry_artifact_path),
                    "warnings": [],
                    "completed_at": datetime.utcnow(),
                }
            )
            parsed_result["geometry_optimization_id"] = geometry_record.geometry_optimization_id
        updated = self.repository.update_dft_calculation(
            dft_calculation_id,
            owner_user_id,
            status="completed" if parsed_result.get("converged") else "needs_model_review",
            calculation_metadata=metadata,
            input_artifact_path=result["input_artifact_path"],
            output_artifact_path=result["output_artifact_path"],
            parsed_result=parsed_result,
            completed_at=datetime.utcnow(),
        )
        return self.serialize_dft_calculation(updated)

    def _generate_electronic_structure_candidates(self, quantum_region_id: str, owner_user_id: int, request: dict) -> dict:
        """Evaluate every requested charge/spin candidate and preserve failures as scientific evidence."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None:
            raise StructureModelingError("quantum_region_not_found", "后台任务执行时未找到量子区。", 404)
        atomic_sites = self._read_json_artifact(region.geometry_artifact_path)["atomic_sites"]
        spin_multiplicities = self._resolve_spin_multiplicities(
            request["spin_strategy"],
            request.get("spin_multiplicities", []),
            atomic_sites,
        )
        candidates: list[dict] = []
        for total_charge in request["charge_candidates"]:
            for spin_multiplicity in spin_multiplicities:
                result: dict
                try:
                    result = self.electronic_structure_adapter.generate_active_space_candidates(
                        {
                            "atomic_sites": atomic_sites,
                            "total_charge": total_charge,
                            "spin_multiplicity": spin_multiplicity,
                            "basis_set": request["basis_set"],
                            "requested_methods": request["requested_methods"],
                            "max_scf_attempts": request["max_scf_attempts"],
                            "spin_contamination_threshold": request["spin_contamination_threshold"],
                        },
                        timeout_seconds=BACKGROUND_ELECTRONIC_STRUCTURE_TIMEOUT_SECONDS,
                    )
                except ElectronicStructureRuntimeError as exc:
                    result = {
                        "status": "failed",
                        "message": f"PySCF 运行失败：{exc}",
                        "basis_set": request["basis_set"],
                        "scf_attempts": [],
                    }
                artifact_path = self._write_json_artifact(self._new_id("electronic_structure"), result)
                contamination = result.get("spin_contamination")
                is_converged = result.get("status") != "needs_model_review" and result.get("status") != "failed"
                exceeds_threshold = contamination is not None and contamination > request["spin_contamination_threshold"]
                quality_status = "eligible_for_confirmation" if is_converged and not exceeds_threshold else "needs_model_review"
                if result.get("status") == "failed":
                    quality_status = "failed"
                warnings = []
                if result.get("message"):
                    warnings.append(result["message"])
                if exceeds_threshold:
                    warnings.append(
                        f"自旋污染 {contamination:.6f} 超过案例阈值 {request['spin_contamination_threshold']:.6f}。"
                    )
                record = self.repository.create_electronic_structure_candidate(
                    {
                        "candidate_id": self._new_id("esc"),
                        "quantum_region_id": quantum_region_id,
                        "benchmark_case_id": request.get("benchmark_case_id"),
                        "owner_user_id": owner_user_id,
                        "total_charge": total_charge,
                        "spin_multiplicity": spin_multiplicity,
                        "scf_method": result.get("method_name"),
                        "basis_set": result.get("basis_set", request["basis_set"]),
                        "converged": int(is_converged),
                        "scf_iterations": result.get("scf_attempts", []),
                        "total_energy_hartree": result.get("hf_total_energy_hartree"),
                        "spin_square_s2": result.get("spin_square"),
                        "expected_spin_square_s2": result.get("expected_spin_square"),
                        "spin_contamination_delta": contamination,
                        "spin_contamination_threshold": request["spin_contamination_threshold"],
                        "quality_status": quality_status,
                        "warnings": warnings,
                        "log_artifact_path": str(artifact_path),
                        "result_artifact_path": str(artifact_path),
                    }
                )
                candidates.append(self.serialize_electronic_structure_candidate(record))
        eligible = [candidate for candidate in candidates if candidate["quality_status"] == "eligible_for_confirmation"]
        if not eligible:
            self._mark_region_for_model_review(region, owner_user_id, "没有通过收敛和自旋污染阈值的电子结构候选。")
        return {
            "quantum_region_id": quantum_region_id,
            "status": "completed" if eligible else "needs_model_review",
            "candidate_count": len(candidates),
            "eligible_candidate_count": len(eligible),
            "candidates": candidates,
        }

    def generate_active_space_candidates(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        timeout_seconds: int | None = None,
    ) -> dict:
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None:
            raise StructureModelingError("quantum_region_not_found", "未找到量子区或无权访问。", 404)
        if region.status != "quantum_region_built":
            raise StructureModelingError("quantum_region_not_ready", "请先确认量子区的电荷和自旋多重度。", 409)
        artifact = self._read_json_artifact(region.geometry_artifact_path)
        try:
            basis_set = "def2-svp" if any(site["element"] in TRANSITION_METALS for site in artifact["atomic_sites"]) else "sto-3g"
            result = self.electronic_structure_adapter.generate_active_space_candidates(
                {
                    "atomic_sites": artifact["atomic_sites"],
                    "total_charge": region.total_charge,
                    "spin_multiplicity": region.spin_multiplicity,
                    "basis_set": basis_set,
                },
                timeout_seconds=timeout_seconds,
            )
        except ElectronicStructureRuntimeError as exc:
            self._mark_region_for_model_review(region, owner_user_id, str(exc))
            raise StructureModelingError("electronic_structure_failed", f"PySCF 计算失败：{exc}", 503) from exc
        hf_artifact_path = self._write_json_artifact(self._new_id("hf"), result)
        if result.get("status") == "needs_model_review":
            self._mark_region_for_model_review(region, owner_user_id, result["message"])
            return {
                "quantum_region_id": quantum_region_id,
                "status": "needs_model_review",
                "message": result["message"],
                "method_name": None,
                "scf_log_artifact_id": hf_artifact_path.stem,
                "candidates": [],
            }
        candidates = []
        for candidate in result["active_space_candidates"]:
            requires_model_review = result["spin_contamination_warning"] or not result["open_shell_hamiltonian_supported"]
            record = self.repository.create_active_space({"active_space_id": self._new_id("aspace"), "quantum_region_id": quantum_region_id, "owner_user_id": owner_user_id, "active_electrons": candidate["active_electrons"], "active_orbitals": candidate["active_orbitals"], "orbital_indices": candidate["orbital_indices"], "orbital_metadata": {"energies_hartree": candidate["orbital_energies_hartree"], "orbital_details": candidate.get("orbital_details", []), "hf_total_energy_hartree": result["hf_total_energy_hartree"], "method_name": result["method_name"], "basis_set": result["basis_set"], "debug_basis_only": result["basis_set"].lower() == "sto-3g", "spin_square": result["spin_square"], "expected_spin_square": result["expected_spin_square"], "spin_contamination": result["spin_contamination"], "spin_contamination_warning": result["spin_contamination_warning"], "scf_log_artifact_id": hf_artifact_path.stem, "open_shell_hamiltonian_supported": result["open_shell_hamiltonian_supported"]}, "selection_reason": candidate["selection_reason"], "status": "needs_model_review" if requires_model_review else "suggested"})
            candidates.append(self.serialize_active_space(record))
        if result["spin_contamination_warning"]:
            self._mark_region_for_model_review(region, owner_user_id, "SCF 自旋污染超过阈值，需要人工复核。")
        return {"quantum_region_id": quantum_region_id, "method_name": result["method_name"], "candidates": candidates}

    def submit_active_space_candidates(self, quantum_region_id: str, owner_user_id: int) -> dict:
        if self.repository.get_quantum_region(quantum_region_id, owner_user_id) is None:
            raise StructureModelingError("quantum_region_not_found", "未找到量子区或无权访问。", 404)
        task_id = task_manager.submit(
            self.generate_active_space_candidates,
            quantum_region_id,
            owner_user_id,
            BACKGROUND_ELECTRONIC_STRUCTURE_TIMEOUT_SECONDS,
        )
        return {"task_id": task_id, "status": "queued", "message": "电子结构计算已提交后台执行。"}

    @staticmethod
    def get_background_task(task_id: str) -> dict:
        status = task_manager.get_status(task_id)
        if status is None:
            raise StructureModelingError("task_not_found", "未找到后台任务。", 404)
        return {"task_id": task_id, "status": status["status"], "progress": status["progress"], "message": status["message"], "result": task_manager.get_result(task_id) if status["status"] == "completed" else None}

    def confirm_active_space(self, quantum_region_id: str, active_space_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_active_space(active_space_id, owner_user_id)
        if record is None or record.quantum_region_id != quantum_region_id:
            raise StructureModelingError("active_space_not_found", "未找到活性空间候选或无权访问。", 404)
        if record.status == "needs_model_review":
            raise StructureModelingError("active_space_needs_review", "该活性空间存在自旋污染或资源限制，需人工复核后才能确认。", 409)
        confirmed = self.repository.update_active_space(active_space_id, owner_user_id, status="confirmed")
        return self.serialize_active_space(confirmed)

    def build_fermionic_hamiltonian(self, active_space_id: str, owner_user_id: int) -> dict:
        active_space = self.repository.get_active_space(active_space_id, owner_user_id)
        if active_space is None or active_space.status != "confirmed":
            raise StructureModelingError("active_space_not_confirmed", "请先确认活性空间。", 409)
        region = self.repository.get_quantum_region(active_space.quantum_region_id, owner_user_id)
        artifact = self._read_json_artifact(region.geometry_artifact_path)
        try:
            basis_set = active_space.orbital_metadata["basis_set"]
            result = self.electronic_structure_adapter.build_hamiltonian({"atomic_sites": artifact["atomic_sites"], "total_charge": region.total_charge, "spin_multiplicity": region.spin_multiplicity, "basis_set": basis_set, "active_electrons": active_space.active_electrons, "orbital_indices": active_space.orbital_indices})
        except ElectronicStructureRuntimeError as exc:
            raise StructureModelingError("hamiltonian_build_failed", f"积分计算失败：{exc}", 503) from exc
        hamiltonian_id = self._new_id("fh")
        payload = {"method_name": result["method_name"], "basis_set": result["basis_set"], "core_energy_hartree": result["core_energy_hartree"], "one_body_integrals": result.get("one_body_integrals"), "two_body_integrals": result.get("two_body_integrals"), "spin_orbital_one_body_integrals": result.get("spin_orbital_one_body_integrals"), "spin_orbital_two_body_integrals": result.get("spin_orbital_two_body_integrals"), "integral_convention": "chemist_(pq|rs)"}
        path = self._write_json_artifact(hamiltonian_id, payload)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        record = self.repository.create_fermionic_hamiltonian({"hamiltonian_id": hamiltonian_id, "active_space_id": active_space_id, "owner_user_id": owner_user_id, "method_name": result["method_name"], "basis_set": result["basis_set"], "core_energy": result["core_energy_hartree"], "spin_orbital_count": result.get("spin_orbital_count", active_space.active_orbitals * 2), "electron_count": active_space.active_electrons, "artifact_path": str(path), "artifact_hash": digest, "status": "built"})
        return {"hamiltonian_id": record.hamiltonian_id, "method_name": record.method_name, "basis_set": record.basis_set, "core_energy_hartree": record.core_energy, "spin_orbital_count": record.spin_orbital_count, "electron_count": record.electron_count, "artifact_hash": record.artifact_hash, "status": record.status}

    def map_fermionic_hamiltonian(self, hamiltonian_id: str, owner_user_id: int, request: dict) -> dict:
        hamiltonian = self.repository.get_fermionic_hamiltonian(hamiltonian_id, owner_user_id)
        if hamiltonian is None:
            raise StructureModelingError("hamiltonian_not_found", "未找到费米子 Hamiltonian 或无权访问。", 404)
        payload = self._read_json_artifact(hamiltonian.artifact_path)
        try:
            mapping_request = {
                    "one_body_integrals": payload.get("one_body_integrals"),
                    "two_body_integrals": payload.get("two_body_integrals"),
                    "spin_orbital_one_body_integrals": payload.get("spin_orbital_one_body_integrals"),
                    "spin_orbital_two_body_integrals": payload.get("spin_orbital_two_body_integrals"),
                    "core_energy_hartree": payload["core_energy_hartree"],
                    "mapping_method": request["mapping_method"],
                    "coefficient_cutoff": request["pauli_coefficient_cutoff"],
                    "enable_z2_tapering": request["enable_z2_tapering"],
                    "z2_tapering_sectors": request.get("z2_tapering_sectors"),
                }
            result = self.electronic_structure_adapter.map_hamiltonian(
                {key: value for key, value in mapping_request.items() if value is not None}
            )
        except ElectronicStructureRuntimeError as exc:
            raise StructureModelingError("qubit_mapping_failed", f"量子比特映射失败：{exc}", 503) from exc
        qubit_id = self._new_id("qh")
        path = self._write_json_artifact(
            qubit_id,
            {
                "pauli_terms": result["pauli_terms"],
                "z2_tapering_requested": request["enable_z2_tapering"],
                "z2_tapering_applied": result["z2_tapering_applied"],
                "tapered_symmetries": result["tapered_symmetries"],
                "available_z2_symmetries": result["available_z2_symmetries"],
                "tapering_reason": result["tapering_reason"],
                "qubit_count_before_tapering": result["qubit_count_before_tapering"],
                "qubit_count_after_tapering": result["qubit_count"],
                "coefficient_cutoff": request["pauli_coefficient_cutoff"],
                "truncation_error_estimate": result["truncation_error_estimate"],
            },
        )
        record = self.repository.create_qubit_hamiltonian(
            {
                "qubit_hamiltonian_id": qubit_id,
                "fermionic_hamiltonian_id": hamiltonian_id,
                "owner_user_id": owner_user_id,
                "mapping_method": result["mapping_method"],
                "fallback_reason": result["fallback_reason"],
                "qubit_count": result["qubit_count"],
                "qubit_count_before_tapering": result["qubit_count_before_tapering"],
                "symmetry_tapering_applied": int(result["z2_tapering_applied"]),
                "tapered_symmetries": result["tapered_symmetries"],
                "tapering_reason": result["tapering_reason"],
                "truncation_error_estimate": result["truncation_error_estimate"],
                "pauli_term_count": len(result["pauli_terms"]),
                "coefficient_cutoff": request["pauli_coefficient_cutoff"],
                "pauli_artifact_path": str(path),
                "status": "built",
            }
        )
        return {
            "qubit_hamiltonian_id": record.qubit_hamiltonian_id,
            "mapping_method": record.mapping_method,
            "fallback_reason": record.fallback_reason,
            "qubit_count": record.qubit_count,
            "qubit_count_before_tapering": record.qubit_count_before_tapering,
            "z2_tapering_applied": bool(record.symmetry_tapering_applied),
            "tapered_symmetries": record.tapered_symmetries,
            "tapering_reason": record.tapering_reason,
            "pauli_term_count": record.pauli_term_count,
            "truncation_error_estimate": record.truncation_error_estimate,
            "pauli_artifact_id": path.stem,
            "status": record.status,
        }

    def compile_vqe_circuit(self, qubit_hamiltonian_id: str, owner_user_id: int, request: dict) -> dict:
        qubit_hamiltonian = self.repository.get_qubit_hamiltonian(qubit_hamiltonian_id, owner_user_id)
        if qubit_hamiltonian is None: raise StructureModelingError("qubit_hamiltonian_not_found", "未找到量子比特 Hamiltonian。", 404)
        terms = self._read_json_artifact(qubit_hamiltonian.pauli_artifact_path)["pauli_terms"]
        compiled = self.vqe_service.compile(qubit_hamiltonian.qubit_count, terms, request)
        circuit_id = self._new_id("vqe")
        provenance = self._vqe_provenance(qubit_hamiltonian, owner_user_id)
        qasm_path = self._write_json_artifact(circuit_id, {"openqasm_version":"2.0","qasm_content":compiled["qasm_content"],"provenance":provenance})
        plan_path = self._write_json_artifact(self._new_id("measurement"), compiled["measurement_plan"])
        record = self.repository.create_vqe_circuit({"vqe_circuit_id":circuit_id,"qubit_hamiltonian_id":qubit_hamiltonian_id,"owner_user_id":owner_user_id,"ansatz":request["ansatz"],"ansatz_layers":request["ansatz_layers"],"parameter_count":compiled["parameter_count"],"optimizer":request["optimizer"],"max_iterations":request["max_iterations"],"convergence_tolerance":request["convergence_tolerance"],"shots":request["shots"],"measurement_grouping":request["measurement_grouping"],"qasm_artifact_path":str(qasm_path),"measurement_plan_artifact_path":str(plan_path),"status":"compiled"})
        return {"vqe_circuit_id":record.vqe_circuit_id,"openqasm_version":"2.0","qubit_count":qubit_hamiltonian.qubit_count,"parameter_count":record.parameter_count,"qasm_artifact_id":qasm_path.stem,"measurement_plan_artifact_id":plan_path.stem,"provenance":provenance,"status":record.status}

    def execute_vqe_circuit(self, vqe_circuit_id: str, owner_user_id: int) -> dict:
        circuit = self.repository.get_vqe_circuit(vqe_circuit_id, owner_user_id)
        if circuit is None: raise StructureModelingError("vqe_circuit_not_found", "未找到 VQE 线路。", 404)
        qubit_hamiltonian = self.repository.get_qubit_hamiltonian(circuit.qubit_hamiltonian_id, owner_user_id)
        terms = self._read_json_artifact(qubit_hamiltonian.pauli_artifact_path)["pauli_terms"]
        result = self.vqe_service.execute(qubit_hamiltonian.qubit_count, terms, {"ansatz_layers":circuit.ansatz_layers,"max_iterations":circuit.max_iterations,"convergence_tolerance":circuit.convergence_tolerance,"shots":circuit.shots})
        result["provenance"] = self._vqe_provenance(qubit_hamiltonian, owner_user_id)
        result["distributed_execution"] = self._partition_vqe_qasm(result["qasm_content"], qubit_hamiltonian.qubit_count)
        lookup_reference = getattr(self.repository, "get_latest_classical_reference", None)
        classical_reference = (
            lookup_reference(qubit_hamiltonian.fermionic_hamiltonian_id, owner_user_id)
            if lookup_reference is not None
            else None
        )
        if classical_reference and classical_reference.energy_hartree is not None:
            absolute_error = abs(result["final_energy_hartree"] - classical_reference.energy_hartree)
            reference_magnitude = max(abs(classical_reference.energy_hartree), 1e-12)
            result["benchmark_comparison"] = {
                "classical_reference_method": classical_reference.method,
                "classical_reference_energy_hartree": classical_reference.energy_hartree,
                "vqe_energy_hartree": result["final_energy_hartree"],
                "absolute_energy_error_hartree": absolute_error,
                "relative_energy_error": absolute_error / reference_magnitude,
                "vqe_converged": result["converged"],
                "execution_backend_type": "simulator",
                "result_qualification": "benchmark_validated_simulator_vqe",
            }
        else:
            result["benchmark_comparison"] = {
                "classical_reference_method": None,
                "classical_reference_energy_hartree": None,
                "vqe_energy_hartree": result["final_energy_hartree"],
                "absolute_energy_error_hartree": None,
                "relative_energy_error": None,
                "vqe_converged": result["converged"],
                "execution_backend_type": "simulator",
                "result_qualification": "exploratory_simulator_vqe",
            }
        history_path = self._write_json_artifact(self._new_id("vqe_history"), result)
        record = self.repository.create_vqe_execution({"execution_id":self._new_id("vqe_exec"),"vqe_circuit_id":vqe_circuit_id,"owner_user_id":owner_user_id,"execution_backend_type":"simulator","execution_backend_detail":"qiskit_statevector_exact","shots_total":circuit.shots * len(result["history"]),"converged":int(result["converged"]),"final_energy_hartree":result["final_energy_hartree"],"energy_uncertainty_hartree":result["energy_uncertainty_hartree"],"energy_uncertainty_method":result["energy_uncertainty_method"],"iteration_artifact_path":str(history_path),"status":"completed"})
        return self._serialize_vqe_execution(record, result)

    def get_vqe_execution(self, execution_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_vqe_execution(execution_id, owner_user_id)
        if record is None:
            raise StructureModelingError("vqe_execution_not_found", "未找到 VQE 执行记录。", 404)
        artifact = self._read_json_artifact(record.iteration_artifact_path)
        return self._serialize_vqe_execution(record, artifact)

    @classmethod
    def _serialize_vqe_execution(cls, record, artifact: dict) -> dict:
        return {
            "execution_id": record.execution_id,
            "execution_backend_type": record.execution_backend_type,
            "execution_backend_detail": record.execution_backend_detail,
            "shots_total": record.shots_total,
            "final_energy_hartree": record.final_energy_hartree,
            "energy_uncertainty_hartree": record.energy_uncertainty_hartree,
            "energy_uncertainty_method": record.energy_uncertainty_method,
            "converged": bool(record.converged),
            "provenance": artifact.get("provenance"),
            "benchmark_comparison": artifact.get("benchmark_comparison"),
            "history": cls._summarize_vqe_history(artifact.get("history", [])),
            "distributed_execution": artifact.get("distributed_execution"),
            "iteration_artifact_id": Path(record.iteration_artifact_path).stem,
            "status": record.status,
        }

    @staticmethod
    def _summarize_vqe_history(history: list[dict]) -> list[dict]:
        return [
            {
                "iteration": item.get("iteration"),
                "energy_hartree": item.get("energy_hartree"),
                "energy_uncertainty_hartree": item.get("energy_uncertainty_hartree"),
                "shots": item.get("shots"),
            }
            for item in history
        ]

    @staticmethod
    def _partition_vqe_qasm(qasm_content: str, qubit_count: int) -> dict:
        if qubit_count < 2:
            return {
                "partition_method": "not_required",
                "capability_level": "no_partition_required",
                "actual_distributed_execution": False,
                "subcircuit_execution_performed": False,
                "measurement_recomposition_performed": False,
                "result_source": "single_statevector_simulator",
                "execution_backend_type": "simulator",
                "subcircuits": [],
                "teleportations": 0,
                "global_gates": [],
                "recomposition": "单量子比特线路无需分区，直接在状态向量模拟器执行。",
                "reason": "单量子比特线路无需分区。",
            }
        try:
            load_qasm_string, remove_single_qubit_gates, extract_qubits = load_circuit_runtime()
            _, gates = load_qasm_string(qasm_content)
            multi_gates = remove_single_qubit_gates(gates)
            scheme, _, _ = load_partition_pipeline()(gates=multi_gates, qubits=extract_qubits(gates), num_partitions=2, max_imbalance=1)
            if scheme is None:
                return {
                    "partition_method": "unavailable",
                    "capability_level": "partition_planning_unavailable",
                    "actual_distributed_execution": False,
                    "subcircuit_execution_performed": False,
                    "measurement_recomposition_performed": False,
                    "result_source": "single_statevector_simulator",
                    "execution_backend_type": "simulator",
                    "subcircuits": [],
                    "teleportations": None,
                    "global_gates": [],
                    "recomposition": "未执行分区重组。",
                    "reason": "未找到有效分区方案。",
                }
            return {
                "partition_method": "existing_partitioning_pipeline",
                "capability_level": "partition_planning_validation",
                "actual_distributed_execution": False,
                "subcircuit_execution_performed": False,
                "measurement_recomposition_performed": False,
                "result_source": "single_statevector_simulator",
                "execution_backend_type": "simulator",
                "subcircuits": [
                    {
                        "index": index,
                        "qubits": partition,
                        "assignment": "qiskit_statevector_exact",
                        "assignment_status": "planned_not_executed",
                        "execution_backend_type": "simulator",
                    }
                    for index, partition in enumerate(scheme.partitions)
                ],
                "teleportations": scheme.teleportations,
                "global_gates": scheme.global_gates,
                "recomposition": "未执行分区后测量重组；主 VQE 能量来自单个状态向量模拟器，分区结果仅用于规划验证。",
            }
        except Exception as exc:
            return {
                "partition_method": "unavailable",
                "capability_level": "partition_planning_unavailable",
                "actual_distributed_execution": False,
                "subcircuit_execution_performed": False,
                "measurement_recomposition_performed": False,
                "result_source": "single_statevector_simulator",
                "execution_backend_type": "simulator",
                "subcircuits": [],
                "teleportations": None,
                "global_gates": [],
                "recomposition": "分区失败，未执行重组。",
                "reason": str(exc),
            }

    @staticmethod
    def serialize_file(record) -> dict:
        return {"file_id": record.file_id, "material_name": record.material_name, "material_family": record.material_family, "description": record.description, "original_filename": record.original_filename, "file_type": record.file_type, "file_size_bytes": record.file_size_bytes, "file_hash": record.file_hash, "parse_status": record.parse_status, "parse_error": {"code": record.parse_error_code, "message": record.parse_error_message} if record.parse_error_code else None, "structure_id": record.structure_id, "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat()}

    def serialize_parse_result(self, file_record, structure) -> dict:
        return {"file_id": file_record.file_id, "structure_id": structure.structure_id, "workflow_id": structure.workflow_id, "parse_status": file_record.parse_status, "validation_status": structure.validation_status, "formula": structure.formula, "elements": structure.elements, "atom_count": structure.atom_count, "structure_type": structure.structure_type, "warnings": structure.parse_warnings + structure.validation_warnings}

    @staticmethod
    def serialize_structure(structure, file_record, include_atomic_sites: bool) -> dict:
        result = {"structure_id": structure.structure_id, "workflow_id": structure.workflow_id, "file_id": structure.file_id, "data_source": "user_uploaded_structure", "material_name": file_record.material_name, "material_family": file_record.material_family, "formula": structure.formula, "elements": structure.elements, "element_counts": structure.element_counts, "atom_count": structure.atom_count, "structure_type": structure.structure_type, "lattice": structure.lattice, "charge": structure.charge, "spin_multiplicity": structure.spin_multiplicity, "dimensionality": structure.dimensionality, "parse_warnings": structure.parse_warnings, "validation": {"status": structure.validation_status, "is_valid": structure.validation_status in {"valid", "valid_with_warnings"}, "errors": structure.validation_errors, "warnings": structure.validation_warnings, "suggestions": structure.validation_suggestions}}
        if include_atomic_sites:
            result["atomic_sites"] = structure.atomic_sites
        return result

    @staticmethod
    def serialize_active_site(site, structure=None) -> dict:
        center_elements: list[str] = []
        neighbor_elements: list[str] = []
        if structure is not None:
            elements_by_index = {
                atomic_site["index"]: atomic_site["element"]
                for atomic_site in structure.atomic_sites
            }
            center_elements = [elements_by_index[index] for index in site.center_atom_indices]
            neighbor_elements = [elements_by_index[index] for index in site.neighbor_atom_indices]
        coordination_number = len(site.neighbor_atom_indices)
        if center_elements:
            center_label = "/".join(center_elements)
            neighbor_label = ", ".join(neighbor_elements) if neighbor_elements else "无近邻原子"
            recommendation_reason = (
                f"以 {center_label} 为中心，在 2.8 Å 配位半径内识别到 "
                f"{coordination_number} 个近邻原子（{neighbor_label}）。"
            )
        else:
            recommendation_reason = "基于 2.8 Å 邻域配位规则识别的候选活性位点。"
        return {
            "active_site_id": site.active_site_id,
            "structure_id": site.structure_id,
            "center_atom_indices": site.center_atom_indices,
            "neighbor_atom_indices": site.neighbor_atom_indices,
            "site_label": site.site_label,
            "site_type": site.site_type,
            "detection_method": site.detection_method,
            "confidence": site.confidence,
            "recommendation_reason": recommendation_reason,
            "center_elements": center_elements,
            "neighbor_elements": neighbor_elements,
            "coordination_number": coordination_number,
            "status": site.status,
            "confirmed_at": site.confirmed_at.isoformat() if site.confirmed_at else None,
            "confirmed_by_user_id": site.selected_by_user_id,
            "user_note": site.user_note,
            "created_at": site.created_at.isoformat(),
        }

    @staticmethod
    def serialize_geometry_optimization(record) -> dict:
        return {"geometry_optimization_id": record.geometry_optimization_id, "adsorption_model_id": record.adsorption_model_id, "calculation_mode": record.calculation_mode, "source_type": record.source_type, "method_name": record.method_name, "status": record.status, "geometry_artifact_id": Path(record.geometry_artifact_path).stem if record.geometry_artifact_path else None, "warnings": record.warnings, "error_message": record.error_message, "completed_at": record.completed_at.isoformat() if record.completed_at else None}

    @staticmethod
    def serialize_active_space(record) -> dict:
        return {"active_space_id": record.active_space_id, "active_electrons": record.active_electrons, "active_orbitals": record.active_orbitals, "orbital_indices": record.orbital_indices, "orbital_metadata": record.orbital_metadata, "selection_reason": record.selection_reason, "status": record.status}

    @staticmethod
    def serialize_quantum_region(region) -> dict:
        return {"quantum_region_id": region.quantum_region_id, "adsorption_model_id": region.adsorption_model_id, "region_atom_indices": region.region_atom_indices, "frozen_environment_atom_indices": region.frozen_environment_atom_indices, "embedding_method": region.embedding_method, "total_charge": region.total_charge, "spin_multiplicity": region.spin_multiplicity, "geometry_source_type": region.geometry_source_type, "geometry_method": region.geometry_method, "geometry_artifact_id": Path(region.geometry_artifact_path).stem, "status": region.status, "warnings": region.warnings}

    @staticmethod
    def serialize_benchmark_case(record) -> dict:
        return {
            "benchmark_case_id": record.benchmark_case_id,
            "title": record.title,
            "catalyst_model_type": record.catalyst_model_type,
            "adsorbate_species": record.adsorbate_species,
            "structure_artifact_id": Path(record.structure_artifact_path).stem,
            "structure_origin": record.structure_origin,
            "geometry_status": record.geometry_status,
            "total_charge": record.total_charge,
            "spin_candidate_definitions": record.spin_candidate_definitions,
            "dft_metadata": record.dft_metadata,
            "accepted_reference_id": record.accepted_reference_id,
            "version": record.version,
            "status": record.status,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    @staticmethod
    def serialize_electronic_structure_candidate(record) -> dict:
        return {
            "candidate_id": record.candidate_id,
            "quantum_region_id": record.quantum_region_id,
            "benchmark_case_id": record.benchmark_case_id,
            "total_charge": record.total_charge,
            "spin_multiplicity": record.spin_multiplicity,
            "scf_method": record.scf_method,
            "basis_set": record.basis_set,
            "converged": bool(record.converged),
            "scf_iterations": record.scf_iterations,
            "total_energy_hartree": record.total_energy_hartree,
            "spin_square_s2": record.spin_square_s2,
            "expected_spin_square_s2": record.expected_spin_square_s2,
            "spin_contamination_delta": record.spin_contamination_delta,
            "spin_contamination_threshold": record.spin_contamination_threshold,
            "quality_status": record.quality_status,
            "warnings": record.warnings,
            "log_artifact_id": Path(record.log_artifact_path).stem if record.log_artifact_path else None,
            "result_artifact_id": Path(record.result_artifact_path).stem if record.result_artifact_path else None,
            "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def serialize_dft_import(record) -> dict:
        return {
            "dft_import_id": record.dft_import_id,
            "adsorption_model_id": record.adsorption_model_id,
            "optimized_structure_id": record.optimized_structure_id,
            "status": record.status,
            "calculation_metadata": record.calculation_metadata,
            "energy_bundle": record.energy_bundle,
            "adsorption_energy_hartree": record.adsorption_energy_hartree,
            "comparability_warnings": record.comparability_warnings,
            "geometry_artifact_id": Path(record.geometry_artifact_path).stem if record.geometry_artifact_path else None,
            "source_artifact_id": Path(record.source_artifact_path).stem if record.source_artifact_path else None,
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def serialize_dft_calculation(record) -> dict:
        return {
            "dft_calculation_id": record.dft_calculation_id,
            "adsorption_model_id": record.adsorption_model_id,
            "engine_name": record.engine_name,
            "calculation_type": record.calculation_type,
            "status": record.status,
            "task_id": record.task_id,
            "attempt_count": record.attempt_count,
            "max_attempts": record.max_attempts,
            "timeout_seconds": record.timeout_seconds,
            "cancellation_requested": bool(record.cancellation_requested),
            "calculation_metadata": record.calculation_metadata,
            "parsed_result": record.parsed_result,
            "input_artifact_id": Path(record.input_artifact_path).stem if record.input_artifact_path else None,
            "output_artifact_id": Path(record.output_artifact_path).stem if record.output_artifact_path else None,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat(),
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

    @staticmethod
    def serialize_research_benchmark(record, candidate_count: int) -> dict:
        return {
            "benchmark_id": record.benchmark_id,
            "benchmark_key": record.benchmark_key,
            "title": record.title,
            "source_url": record.source_url,
            "source_doi": record.source_doi,
            "source_license": record.source_license,
            "source_dataset_version": record.source_dataset_version,
            "material_model": record.material_model,
            "adsorbate": record.adsorbate,
            "scientific_validation_level": record.scientific_validation_level,
            "status": record.status,
            "dft_metadata": record.dft_metadata,
            "candidate_count": candidate_count,
            "created_at": record.created_at.isoformat(),
        }

    def serialize_research_benchmark_candidate(self, record) -> dict:
        source_metadata = dict(record.source_metadata or {})
        if "composition_validation" not in source_metadata:
            try:
                coordinate_payload = self._read_json_artifact(record.coordinate_artifact_path)
                element_counts = Counter(site["element"] for site in coordinate_payload.get("atomic_sites", []))
                expected_counts = {"C": 66, "Fe": 1, "N": 4, "Li": 2, "S": 4}
                source_metadata["element_counts"] = dict(element_counts)
                source_metadata["composition_validation"] = (
                    "passed" if dict(element_counts) == expected_counts else "failed"
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning(
                    "Could not derive composition metadata for research benchmark candidate %s: %s",
                    record.candidate_id,
                    exc,
                )
                source_metadata["composition_validation"] = "unavailable"
        return {
            "candidate_id": record.candidate_id,
            "source_candidate_id": record.source_candidate_id,
            "source_energy": record.source_energy,
            "source_energy_unit": record.source_energy_unit,
            "priority_rank": record.priority_rank,
            "status": record.status,
            "coordinate_artifact_id": Path(record.coordinate_artifact_path).stem,
            "source_metadata": source_metadata,
        }

    @staticmethod
    def serialize_classical_reference(record, message: str | None = None) -> dict:
        return {
            "reference_id": record.reference_id,
            "fermionic_hamiltonian_id": record.fermionic_hamiltonian_id,
            "classical_reference_method": record.method,
            "classical_reference_energy_hartree": record.energy_hartree,
            "status": record.status,
            "artifact_id": Path(record.artifact_path).stem if record.artifact_path else None,
            "message": message,
            "created_at": record.created_at.isoformat(),
        }

    def _relax_initial_geometry(self, structure, adsorption_model) -> list[dict]:
        adsorption_geometry = self._read_json_artifact(adsorption_model.geometry_artifact_path)
        host_sites = structure.atomic_sites
        adsorbate_sites = adsorption_geometry["atomic_sites"]
        atoms = Atoms(
            symbols=[site["element"] for site in host_sites + adsorbate_sites],
            positions=[site["position_angstrom"] for site in host_sites + adsorbate_sites],
        )
        atoms.set_constraint(FixAtoms(indices=list(range(structure.atom_count))))
        atoms.calc = LennardJones()
        try:
            BFGS(atoms, logfile=None).run(
                fmax=GEOMETRY_FORCE_TOLERANCE_EV_PER_ANGSTROM,
                steps=MAX_GEOMETRY_RELAXATION_STEPS,
            )
        except Exception as exc:
            logger.exception("Geometry-only relaxation failed for adsorption_model_id=%s", adsorption_model.adsorption_model_id)
            raise StructureModelingError("geometry_optimization_failed", "几何预优化失败，请导入已优化结构或检查初始构型。") from exc
        positions = atoms.get_positions()
        return [{"index": index, "element": atom.symbol, "position_angstrom": [float(value) for value in positions[index]]} for index, atom in enumerate(atoms)]

    @staticmethod
    def _hash_file(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _download_materials_cloud_file(filename: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"{MATERIALS_CLOUD_FILES_URL}/{filename}?download=1"
        with urlopen(url, timeout=60) as response, target.open("wb") as destination:
            total_size = 0
            while chunk := response.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > MAX_RESEARCH_BENCHMARK_DOWNLOAD_BYTES:
                    raise StructureModelingError("research_benchmark_too_large", "文献数据包超过导入大小限制。", 413)
                destination.write(chunk)

    @staticmethod
    def _parse_castep_param(path: Path) -> dict:
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
        return {
            "software": "CASTEP",
            "calculation_type": values.get("task"),
            "xc_functional": values.get("xc_functional"),
            "plane_wave_cutoff": values.get("cut_off_energy"),
            "dispersion": {"sedc_apply": values.get("sedc_apply"), "sedc_scheme": values.get("sedc_scheme")},
            "spin_polarized": values.get("spin_polarized"),
            "spin_fix_raw": values.get("spin_fix"),
            "max_scf_cycles": values.get("max_scf_cycles"),
            "electronic_energy_tolerance": values.get("elec_energy_tol"),
            "force_tolerance": values.get("geom_force_tol"),
            "geometry_method": values.get("geom_method"),
        }

    @staticmethod
    def _parse_castep_cell(path: Path) -> dict:
        content = path.read_text(encoding="utf-8", errors="replace")
        lattice_match = re.search(r"%BLOCK\s+LATTICE_CART\s*(.*?)%ENDBLOCK", content, re.IGNORECASE | re.DOTALL)
        lattice = []
        if lattice_match:
            lattice = [[float(value) for value in line.split()[:3]] for line in lattice_match.group(1).strip().splitlines()]
        kpoint_match = re.search(r"KPOINTS_MP_GRID\s+(\d+)\s+(\d+)\s+(\d+)", content, re.IGNORECASE)
        spin_match = re.search(r"Fe\s+[^\n]*SPIN=([+-]?[0-9.]+)", content, re.IGNORECASE)
        return {
            "lattice_matrix_angstrom": lattice,
            "vacuum_layer_z_angstrom": lattice[2][2] if len(lattice) == 3 else None,
            "k_points": [int(value) for value in kpoint_match.groups()] if kpoint_match else None,
            "fe_initial_magnetic_moment": float(spin_match.group(1)) if spin_match else None,
            "material_model": "periodic_fe_n4_c66",
        }

    def _extract_literature_candidates(self, archive_path: Path, benchmark_root: Path) -> list[dict]:
        prefix = "FeN4C66-Li2S4/"
        with tarfile.open(archive_path, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers() if member.isfile() and member.name.startswith(prefix) and "/._" not in member.name}
            structure_member = next((member for name, member in members.items() if name.endswith("str.xyz")), None)
            energy_member = next((member for name, member in members.items() if name.endswith("energies.dat")), None)
            if structure_member is None or energy_member is None:
                return []
            structure_data = archive.extractfile(structure_member).read().decode("utf-8", errors="replace")
            energy_data = archive.extractfile(energy_member).read().decode("utf-8", errors="replace")
        energy_by_id = {
            tokens[0]: float(tokens[1])
            for line in energy_data.splitlines()
            if len(tokens := line.split()) >= 2
        }
        return self._parse_extxyz_candidates(structure_data, energy_by_id)

    @staticmethod
    def _parse_extxyz_candidates(content: str, energy_by_id: dict[str, float]) -> list[dict]:
        lines = content.splitlines()
        index = 0
        candidates: list[dict] = []
        while index < len(lines):
            try:
                atom_count = int(lines[index].strip())
            except ValueError:
                break
            if index + atom_count + 1 >= len(lines):
                break
            comment = lines[index + 1]
            sites = []
            for site_index, line in enumerate(lines[index + 2 : index + 2 + atom_count]):
                tokens = line.split()
                if len(tokens) < 4:
                    raise StructureModelingError("research_benchmark_structure_invalid", "文献候选坐标格式无效。", 422)
                sites.append({"index": site_index, "element": tokens[0], "position_angstrom": [float(tokens[1]), float(tokens[2]), float(tokens[3])]})
            source_id_match = re.search(r"Time=([^\s]+)", comment)
            source_candidate_id = source_id_match.group(1) if source_id_match else str(len(candidates))
            energy_match = re.search(r"energy=\s*([+-]?[0-9.]+)", comment)
            lattice_match = re.search(r'Lattice="([^"]+)"', comment)
            lattice_values = [float(value) for value in lattice_match.group(1).split()] if lattice_match else []
            lattice = [lattice_values[offset : offset + 3] for offset in range(0, len(lattice_values), 3)]
            candidates.append(
                {
                    "source_candidate_id": source_candidate_id,
                    "source_energy": energy_by_id.get(source_candidate_id, float(energy_match.group(1)) if energy_match else None),
                    "atomic_sites": sites,
                    "source_metadata": {
                        "raw_comment": comment,
                        "lattice_matrix_angstrom": lattice,
                        "source_energy_semantics": "Materials Cloud dataset-native candidate energy; not a project adsorption energy.",
                    },
                }
            )
            index += atom_count + 2
        return candidates

    @staticmethod
    def _to_extxyz(atomic_sites: list[dict], lattice: list[list[float]] | None, source_energy: float | None) -> str:
        flattened_lattice = " ".join(str(value) for row in lattice or [] for value in row)
        comment_parts = ["Properties=species:S:1:pos:R:3"]
        if flattened_lattice:
            comment_parts.append(f'Lattice="{flattened_lattice}"')
        if source_energy is not None:
            comment_parts.append(f"source_energy={source_energy}")
        lines = [str(len(atomic_sites)), " ".join(comment_parts)]
        lines.extend(
            f"{site['element']} {' '.join(f'{float(value):.10f}' for value in site['position_angstrom'])}"
            for site in atomic_sites
        )
        return "\n".join(lines) + "\n"

    def _load_imported_optimized_geometry(self, structure, adsorption_model, owner_user_id: int, request: dict) -> tuple[list[dict], str]:
        imported_structure_id = request.get("imported_structure_id")
        method_name = request.get("method_name")
        if not imported_structure_id or not method_name:
            raise StructureModelingError("optimized_geometry_details_required", "导入优化几何时必须提供结构 ID 和计算方法说明。")
        if request["calculation_mode"] == "dft_optimized":
            required_fields = {"software", "functional", "basis_or_pseudopotential", "dispersion", "convergence"}
            if not required_fields.issubset(request.get("calculation_metadata", {})):
                raise StructureModelingError("dft_metadata_required", "导入 DFT 优化结果时必须提供软件、泛函、基组或赝势、色散修正和收敛阈值。")
        imported = self._require_valid_structure(imported_structure_id, owner_user_id)
        adsorption_geometry = self._read_json_artifact(adsorption_model.geometry_artifact_path)
        expected_elements = Counter(site["element"] for site in structure.atomic_sites + adsorption_geometry["atomic_sites"])
        if Counter(site["element"] for site in imported.atomic_sites) != expected_elements:
            raise StructureModelingError("optimized_geometry_mismatch", "导入优化结构的元素组成必须与材料骨架和 Li2Sx 吸附物一致。")
        if imported.atom_count < structure.atom_count:
            raise StructureModelingError("optimized_geometry_mismatch", "导入优化结构缺少材料骨架原子。")
        return imported.atomic_sites, method_name

    @staticmethod
    def _resolve_spin_multiplicities(strategy: str, requested: list[int], atomic_sites: list[dict]) -> list[int]:
        if strategy == "explicit":
            return sorted(set(requested))
        if any(site["element"] in TRANSITION_METALS for site in atomic_sites):
            return sorted(set(requested or [1, 3, 5]))
        return sorted(set(requested or [1]))

    @staticmethod
    def _missing_dft_metadata(metadata: dict, required_fields: set[str]) -> list[str]:
        return sorted(
            field
            for field in required_fields
            if field not in metadata or metadata[field] is None or metadata[field] == ""
        )

    def _validate_imported_dft_geometry(self, adsorption_model, imported_structure, owner_user_id: int) -> None:
        active_site = self._get_active_site_or_raise(adsorption_model.active_site_id, owner_user_id)
        host_structure = self._require_valid_structure(active_site.structure_id, owner_user_id)
        adsorption_geometry = self._read_json_artifact(adsorption_model.geometry_artifact_path)
        expected_elements = Counter(
            site["element"] for site in host_structure.atomic_sites + adsorption_geometry["atomic_sites"]
        )
        actual_elements = Counter(site["element"] for site in imported_structure.atomic_sites)
        if actual_elements != expected_elements:
            raise StructureModelingError(
                "optimized_geometry_mismatch",
                "DFT 导入结构的元素组成必须与材料骨架和 Li2Sx 吸附物一致。",
            )

    def _direct_dft_atomic_sites(self, adsorption_model, owner_user_id: int) -> list[dict]:
        active_site = self._get_active_site_or_raise(adsorption_model.active_site_id, owner_user_id)
        host_structure = self._require_valid_structure(active_site.structure_id, owner_user_id)
        adsorbate_geometry = self._read_json_artifact(adsorption_model.geometry_artifact_path)
        return host_structure.atomic_sites + adsorbate_geometry["atomic_sites"]

    @staticmethod
    def _validate_adsorption_energy_bundle(energy_bundle: dict) -> tuple[float | None, list[str]]:
        required_entries = ("adsorbed_system", "host", "adsorbate")
        missing_entries = [entry for entry in required_entries if not isinstance(energy_bundle.get(entry), dict)]
        if missing_entries:
            return None, [f"缺少吸附能所需能量项：{', '.join(missing_entries)}；仅归档，不计算吸附能。"]

        entries = [energy_bundle[name] for name in required_entries]
        missing_values = [
            name
            for name, entry in zip(required_entries, entries)
            if not isinstance(entry.get("energy_hartree"), (int, float))
        ]
        if missing_values:
            return None, [f"以下能量项缺少 energy_hartree：{', '.join(missing_values)}；仅归档，不计算吸附能。"]

        signatures = []
        for entry in entries:
            signature = entry.get("calculation_signature") or entry.get("calculation_settings")
            if not isinstance(signature, dict) or not signature:
                return None, ["每个能量项必须提供 calculation_signature 或 calculation_settings，才能验证可比性。"]
            missing_signature_fields = [
                field
                for field, aliases in {
                    "software": ("software",),
                    "functional": ("functional",),
                    "basis_or_pseudopotential": ("basis_or_pseudopotential", "basis", "pseudopotential"),
                    "dispersion": ("dispersion",),
                    "k_points": ("k_points",),
                    "spin_setting": ("spin_polarization", "spin"),
                }.items()
                if not any(signature.get(alias) is not None and signature.get(alias) != "" for alias in aliases)
            ]
            if missing_signature_fields:
                return None, [
                    f"能量项 calculation_signature 缺少 {', '.join(missing_signature_fields)}；仅归档，不计算吸附能。"
                ]
            signatures.append(json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        if len(set(signatures)) != 1:
            return None, ["吸附态、宿主和 Li2S4 的计算设置不一致；仅归档，不生成可比较的吸附能。"]

        adsorption_energy = (
            float(energy_bundle["adsorbed_system"]["energy_hartree"])
            - float(energy_bundle["host"]["energy_hartree"])
            - float(energy_bundle["adsorbate"]["energy_hartree"])
        )
        return adsorption_energy, []

    @staticmethod
    def _read_json_artifact(artifact_path: str) -> dict:
        try:
            return json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StructureModelingError("artifact_unavailable", "结构 Artifact 不可读取，无法继续建模。", 409) from exc

    def _parse_file(self, storage_path: str, file_type: str) -> dict:
        try:
            atoms = ase_read(storage_path, format=ASE_FORMATS[file_type], index=0)
        except Exception as exc:
            raise StructureModelingError("parse_failed", "文件格式或内容无法解析，请检查结构文件后重新上传。") from exc
        symbols = atoms.get_chemical_symbols()
        positions = np.asarray(atoms.get_positions(), dtype=float)
        atomic_sites = [{"index": index, "element": symbol, "position_angstrom": [float(value) for value in positions[index]]} for index, symbol in enumerate(symbols)]
        is_periodic = bool(np.any(atoms.pbc))
        lattice = None
        if is_periodic:
            cell = np.asarray(atoms.cell.array, dtype=float)
            lattice = {"matrix_angstrom": [[float(value) for value in row] for row in cell], "parameters": [float(value) for value in atoms.cell.cellpar()]}
        structure_type = "crystal" if file_type in {"cif", "poscar", "contcar"} else ("cluster" if file_type == "xyz" else "molecule")
        return {"formula": atoms.get_chemical_formula(mode="hill"), "elements": sorted(set(symbols)), "element_counts": dict(sorted(Counter(symbols).items())), "atom_count": len(symbols), "atomic_sites": atomic_sites, "lattice": lattice, "structure_type": structure_type, "charge": None, "spin_multiplicity": None, "dimensionality": "periodic" if is_periodic else "non_periodic", "parse_warnings": []}

    def _validate_structure(self, parsed: dict) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        suggestions: list[str] = []
        if not 0 < parsed["atom_count"] <= MAX_ATOM_COUNT:
            errors.append(f"原子数量必须在 1 到 {MAX_ATOM_COUNT} 之间。")
        positions = np.asarray([site["position_angstrom"] for site in parsed["atomic_sites"]], dtype=float)
        if positions.size and not np.isfinite(positions).all():
            errors.append("原子坐标包含 NaN 或无穷大。")
        if parsed["dimensionality"] == "periodic":
            lattice = parsed["lattice"]
            if lattice is None or abs(float(np.linalg.det(np.asarray(lattice["matrix_angstrom"], dtype=float)))) <= 0:
                errors.append("晶胞参数缺失或无效，无法按晶体结构处理。")
        if len(positions) > 1 and np.isfinite(positions).all():
            pairs = cKDTree(positions).query_pairs(MIN_INTERATOMIC_DISTANCE_ANGSTROM)
            if pairs:
                errors.append("存在明显过近或重复的原子坐标，无法建立可靠结构模型。")
        if parsed["dimensionality"] == "non_periodic":
            warnings.append("该结构为非周期模型，后续仅能作为局部团簇近似处理。")
            suggestions.append("进入量子化学阶段前请确认总电荷和自旋多重度。")
        status = "validation_failed" if errors else ("valid_with_warnings" if warnings else "valid")
        return {"validation_status": status, "validation_errors": errors, "validation_warnings": warnings, "validation_suggestions": suggestions}

    def _build_active_site_candidates(self, structure) -> list[dict]:
        sites = structure.atomic_sites
        positions = np.asarray([site["position_angstrom"] for site in sites], dtype=float)
        metal_indices = [site["index"] for site in sites if site["element"] in TRANSITION_METALS]
        candidates = metal_indices[:3]
        if not candidates:
            neighbor_counts = [len(cKDTree(positions).query_ball_point(position, 2.8)) - 1 for position in positions]
            candidates = sorted(range(structure.atom_count), key=lambda index: (neighbor_counts[index], index))[: min(3, structure.atom_count)]
        result = []
        for index in candidates:
            neighbors = [neighbor for neighbor in cKDTree(positions).query_ball_point(positions[index], 2.8) if neighbor != index][:6]
            element = sites[index]["element"]
            is_metal = element in TRANSITION_METALS
            result.append({"center_atom_indices": [index], "neighbor_atom_indices": sorted(neighbors), "site_label": f"{element}-site-{index}", "site_type": "transition_metal_center" if is_metal else "low_coordination_site", "detection_method": "rule_based_v1", "confidence": 0.8 if is_metal else 0.5, "status": "suggested"})
        return result

    def _generate_species_models(self, *, structure, active_site, species: str, center: np.ndarray, initial_distance: float, max_conformations: int) -> list[dict]:
        template_symbols, template_positions = self._polysulfide_template(species)
        host_positions = np.asarray([site["position_angstrom"] for site in structure.atomic_sites], dtype=float)
        generated: list[dict] = []
        for conformation_index in range(max_conformations):
            orientation_index = conformation_index % len(ADSORPTION_ORIENTATIONS)
            strategy = ADSORPTION_ORIENTATIONS[orientation_index]
            distance_offset = CONFORMATION_DISTANCE_OFFSETS_ANGSTROM[
                conformation_index // len(ADSORPTION_ORIENTATIONS)
            ]
            conformation_distance = initial_distance + distance_offset
            if not MIN_ADSORPTION_DISTANCE_ANGSTROM <= conformation_distance <= MAX_ADSORPTION_DISTANCE_ANGSTROM:
                continue
            positions = self._orient_template(template_positions, orientation_index, center, conformation_distance)
            min_distance = self._minimum_cross_distance(host_positions, positions)
            if min_distance < MIN_INTERATOMIC_DISTANCE_ANGSTROM:
                continue
            adsorption_model_id = self._new_id("am")
            artifact_path = self._write_json_artifact(
                adsorption_model_id,
                {"structure_id": structure.structure_id, "active_site_id": active_site.active_site_id, "polysulfide_species": species, "placement_strategy": strategy, "source_type": "geometry_only", "initial_distance_angstrom": conformation_distance, "atomic_sites": [{"index": index, "element": symbol, "position_angstrom": [float(value) for value in positions[index]]} for index, symbol in enumerate(template_symbols)]},
            )
            quality_score = min(1.0, min_distance / MIN_ADSORPTION_DISTANCE_ANGSTROM)
            record = self.repository.create_adsorption_model({"adsorption_model_id": adsorption_model_id, "active_site_id": active_site.active_site_id, "owner_user_id": active_site.owner_user_id, "polysulfide_species": species, "placement_strategy": strategy, "initial_distance_angstrom": conformation_distance, "geometry_quality_score": quality_score, "geometry_artifact_path": str(artifact_path), "status": "generated", "warnings": ["仅生成初始几何构型，未计算吸附能或 DFT 能量。"]})
            generated.append({"adsorption_model_id": record.adsorption_model_id, "polysulfide_species": record.polysulfide_species, "placement_strategy": record.placement_strategy, "initial_distance_angstrom": record.initial_distance_angstrom, "geometry_quality_score": record.geometry_quality_score, "geometry_artifact_id": artifact_path.stem, "status": record.status, "warnings": record.warnings})
        return generated

    @staticmethod
    def _polysulfide_template(species: str) -> tuple[list[str], np.ndarray]:
        sulfur_count = {"Li2S4": 4, "Li2S6": 6}[species]
        sulfur_spacing = 2.05
        sulfur_positions = [[index * sulfur_spacing, 0.0, 0.0] for index in range(sulfur_count)]
        lithium_offset = 1.9
        positions = [[-lithium_offset, 0.0, 0.0], [((sulfur_count - 1) * sulfur_spacing) + lithium_offset, 0.0, 0.0], *sulfur_positions]
        return ["Li", "Li", *(["S"] * sulfur_count)], np.asarray(positions, dtype=float)

    @staticmethod
    def _orient_template(template_positions: np.ndarray, orientation_index: int, center: np.ndarray, distance: float) -> np.ndarray:
        transforms = (
            np.identity(3),
            np.asarray([[-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        )
        anchor_indices = (0, 2, len(template_positions) // 2)
        displacement = np.asarray([0.0, 0.0, distance])
        transformed = template_positions @ transforms[orientation_index].T
        return transformed - transformed[anchor_indices[orientation_index]] + center + displacement

    @staticmethod
    def _minimum_cross_distance(host_positions: np.ndarray, adsorbate_positions: np.ndarray) -> float:
        if not len(host_positions) or not len(adsorbate_positions):
            return math.inf
        distances, _ = cKDTree(host_positions).query(adsorbate_positions, k=1)
        return float(np.min(distances))

    @staticmethod
    def _site_center(atomic_sites: list[dict], center_atom_indices: list[int]) -> np.ndarray:
        return np.mean([atomic_sites[index]["position_angstrom"] for index in center_atom_indices], axis=0)

    @staticmethod
    def _validate_atom_indices(atom_count: int, indices: list[int], label: str) -> None:
        if not indices or len(indices) != len(set(indices)) or any(index < 0 or index >= atom_count for index in indices):
            raise StructureModelingError("invalid_active_site", f"{label}索引不合法。")

    def _detect_file_type(self, original_filename: str, content: bytes) -> str:
        filename = Path(original_filename).name
        if not filename or filename in {".", ""}:
            raise StructureModelingError("unsupported_format", "缺少有效的结构文件名。", 400)
        lower_name = filename.lower()
        if lower_name in {"poscar", "contcar"}:
            file_type = lower_name
        else:
            file_type = Path(lower_name).suffix.removeprefix(".")
        if file_type not in SUPPORTED_FILE_TYPES:
            raise StructureModelingError("unsupported_format", "当前仅支持 xyz、mol、sdf、cif、POSCAR、CONTCAR 格式。", 415)
        if not content:
            raise StructureModelingError("invalid_structure_file", "结构文件不能为空。", 400)
        return file_type

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    def _write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _write_json_artifact(artifact_id: str, payload: dict) -> Path:
        STRUCTURE_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        artifact_path = STRUCTURE_ARTIFACT_ROOT / f"{artifact_id}.json"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return artifact_path

    def _get_file_or_raise(self, file_id: str, owner_user_id: int):
        record = self.repository.get_file(file_id, owner_user_id)
        if record is None:
            raise StructureModelingError("structure_file_not_found", "未找到结构文件或无权访问。", 404)
        return record

    def _get_structure_or_raise(self, structure_id: str, owner_user_id: int):
        record = self.repository.get_structure(structure_id, owner_user_id)
        if record is None:
            raise StructureModelingError("structure_not_found", "未找到结构或无权访问。", 404)
        return record

    def _require_valid_structure(self, structure_id: str, owner_user_id: int):
        structure = self._get_structure_or_raise(structure_id, owner_user_id)
        if structure.validation_status not in {"valid", "valid_with_warnings"}:
            raise StructureModelingError("invalid_structure", "结构校验未通过，不能创建化学建模任务。", 409)
        return structure

    def _get_active_site_or_raise(self, active_site_id: str, owner_user_id: int):
        record = self.repository.get_active_site(active_site_id, owner_user_id)
        if record is None:
            raise StructureModelingError("active_site_not_found", "未找到活性位点或无权访问。", 404)
        return record

    def _get_adsorption_model_or_raise(self, adsorption_model_id: str, owner_user_id: int):
        record = self.repository.get_adsorption_model(adsorption_model_id, owner_user_id)
        if record is None:
            raise StructureModelingError("adsorption_model_not_found", "未找到吸附模型或无权访问。", 404)
        return record

    def _get_geometry_optimization_or_raise(self, geometry_optimization_id: str, owner_user_id: int):
        record = self.repository.get_geometry_optimization(geometry_optimization_id, owner_user_id)
        if record is None:
            raise StructureModelingError("geometry_optimization_not_found", "未找到几何优化记录或无权访问。", 404)
        return record

    def _mark_region_for_model_review(self, region, owner_user_id: int, reason: str) -> None:
        """Preserve the scientific failure state instead of allowing an unsafe downstream calculation."""
        warnings = list(region.warnings or [])
        if reason not in warnings:
            warnings.append(reason)
        self.repository.update_quantum_region(
            region.quantum_region_id,
            owner_user_id,
            status="needs_model_review",
            warnings=warnings,
        )
        adsorption_model = self.repository.get_adsorption_model(region.adsorption_model_id, owner_user_id)
        if adsorption_model is None:
            return
        active_site = self.repository.get_active_site(adsorption_model.active_site_id, owner_user_id)
        if active_site is None:
            return
        structure = self.repository.get_structure(active_site.structure_id, owner_user_id)
        if structure is not None:
            self._set_workflow_status(
                structure.workflow_id,
                owner_user_id,
                "needs_model_review",
                "electronic_structure_needs_review",
                {"quantum_region_id": region.quantum_region_id, "reason": reason},
            )

    def _vqe_provenance(self, qubit_hamiltonian, owner_user_id: int) -> dict:
        """Trace every VQE artifact back to its user structure and approximation limits."""
        fermionic_hamiltonian = self.repository.get_fermionic_hamiltonian(
            qubit_hamiltonian.fermionic_hamiltonian_id,
            owner_user_id,
        )
        active_space = self.repository.get_active_space(fermionic_hamiltonian.active_space_id, owner_user_id)
        region = self.repository.get_quantum_region(active_space.quantum_region_id, owner_user_id)
        adsorption_model = self.repository.get_adsorption_model(region.adsorption_model_id, owner_user_id)
        active_site = self.repository.get_active_site(adsorption_model.active_site_id, owner_user_id)
        get_structure = getattr(self.repository, "get_structure", None)
        get_workflow = getattr(self.repository, "get_workflow", None)
        structure = get_structure(active_site.structure_id, owner_user_id) if callable(get_structure) else None
        workflow = get_workflow(structure.workflow_id, owner_user_id) if structure is not None and callable(get_workflow) else None
        workflow_payload = workflow.payload if workflow is not None and workflow.payload else {}
        return {
            "source_type": workflow_payload.get("data_source", "user_uploaded_structure"),
            "scientific_validation_level": workflow_payload.get("scientific_validation_level"),
            "method_name": fermionic_hamiltonian.method_name,
            "execution_backend_type": "simulator",
            "confidence": "research_prototype",
            "model_limitations": [
                "hardware_efficient_ry_cx 是近似 ansatz，不等同于严格基态求解。",
                "当前执行为精确 statevector 模拟，未调用真实 QPU。",
                "线路分区仅用于规划验证，未执行子线路协同计算或分区测量结果重组。",
                f"几何来源：{region.geometry_source_type}。",
            ],
            "input_structure_id": active_site.structure_id,
            "active_site_id": active_site.active_site_id,
            "adsorption_model_id": adsorption_model.adsorption_model_id,
        }

    @staticmethod
    def _serialize_workflow_list_item(workflow) -> dict:
        payload = workflow.payload or {}
        return {
            "workflow_id": workflow.workflow_id,
            "structure_id": workflow.structure_id,
            "status": workflow.status,
            "data_source": payload.get("data_source", "user_uploaded_structure"),
            "scientific_validation_level": payload.get("scientific_validation_level"),
            "geometry_status": payload.get("geometry_status"),
            "event_count": len(payload.get("events", [])),
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
        }

    def _build_workflow_stages(self, resources: dict) -> list[dict]:
        structure = resources["structure"]
        source_file = resources["source_file"]
        artifacts = self._workflow_artifact_entries(resources)
        artifacts_by_stage: dict[str, list[dict]] = {}
        for artifact in artifacts:
            artifacts_by_stage.setdefault(artifact["stage_name"], []).append(
                {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_role": artifact["artifact_role"],
                    "resource_type": artifact["resource_type"],
                    "resource_id": artifact["resource_id"],
                }
            )

        stages: list[dict] = []

        def add_stage(
            stage_name: str,
            objects: list[dict],
            confirmations: list[dict] | None = None,
        ) -> None:
            stage_status = "confirmed" if confirmations else (objects[-1]["status"] if objects else "not_started")
            stages.append(
                {
                    "stage_name": stage_name,
                    "status": stage_status,
                    "objects": objects,
                    "artifacts": artifacts_by_stage.get(stage_name, []),
                    "confirmations": confirmations or [],
                }
            )

        structure_objects = []
        if source_file is not None:
            structure_objects.append(
                self._stage_object("structure_file", source_file.file_id, None, source_file.parse_status)
            )
        if structure is not None:
            structure_objects.append(
                self._stage_object(
                    "parsed_structure",
                    structure.structure_id,
                    source_file.file_id if source_file is not None else None,
                    structure.validation_status,
                )
            )
        structure_objects.extend(
            self._stage_object(
                "benchmark_case",
                record.benchmark_case_id,
                structure.structure_id if structure is not None else None,
                record.status,
            )
            for record in self._linked_benchmark_cases(resources)
        )
        add_stage("structure", structure_objects)

        active_site_objects = [
            self._stage_object(
                "active_site",
                record.active_site_id,
                record.structure_id,
                record.status,
            )
            for record in resources["active_sites"]
        ]
        active_site_confirmations = [
            {
                "confirmation_type": "active_site",
                "object_id": record.active_site_id,
                "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
                "confirmed_by_user_id": record.selected_by_user_id,
            }
            for record in resources["active_sites"]
            if record.status == "confirmed"
        ]
        add_stage("active_site", active_site_objects, active_site_confirmations)

        add_stage(
            "adsorption_model",
            [
                self._stage_object(
                    "adsorption_model",
                    record.adsorption_model_id,
                    record.active_site_id,
                    record.status,
                )
                for record in resources["adsorption_models"]
            ],
        )
        geometry_objects = [
            self._stage_object(
                "geometry_optimization",
                record.geometry_optimization_id,
                record.adsorption_model_id,
                record.status,
            )
            for record in resources["geometry_optimizations"]
        ]
        geometry_objects.extend(
            self._stage_object(
                "dft_import",
                record.dft_import_id,
                record.adsorption_model_id,
                record.status,
            )
            for record in resources["dft_imports"]
        )
        geometry_objects.extend(
            self._stage_object(
                "dft_calculation",
                record.dft_calculation_id,
                record.adsorption_model_id,
                record.status,
            )
            for record in resources["dft_calculations"]
        )
        add_stage("geometry_and_dft", geometry_objects)

        quantum_region_objects = [
            self._stage_object(
                "quantum_region",
                record.quantum_region_id,
                record.adsorption_model_id,
                record.status,
            )
            for record in resources["quantum_regions"]
        ]
        electronic_confirmations = [
            {
                "confirmation_type": "electronic_structure_candidate",
                "object_id": record.candidate_id,
                "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
                "confirmed_by_user_id": record.confirmed_by_user_id,
            }
            for record in resources["electronic_candidates"]
            if record.confirmed_at is not None
        ]
        quantum_region_objects.extend(
            self._stage_object(
                "electronic_structure_candidate",
                record.candidate_id,
                record.quantum_region_id,
                record.quality_status,
            )
            for record in resources["electronic_candidates"]
        )
        add_stage("quantum_region", quantum_region_objects, electronic_confirmations)

        add_stage(
            "active_space",
            [
                self._stage_object(
                    "active_space",
                    record.active_space_id,
                    record.quantum_region_id,
                    record.status,
                )
                for record in resources["active_spaces"]
            ],
        )
        hamiltonian_objects = [
            self._stage_object(
                "fermionic_hamiltonian",
                record.hamiltonian_id,
                record.active_space_id,
                record.status,
            )
            for record in resources["fermionic_hamiltonians"]
        ]
        hamiltonian_objects.extend(
            self._stage_object(
                "qubit_hamiltonian",
                record.qubit_hamiltonian_id,
                record.fermionic_hamiltonian_id,
                record.status,
            )
            for record in resources["qubit_hamiltonians"]
        )
        hamiltonian_objects.extend(
            self._stage_object(
                "classical_reference",
                record.reference_id,
                record.fermionic_hamiltonian_id,
                record.status,
            )
            for record in resources["classical_references"]
        )
        add_stage("hamiltonian", hamiltonian_objects)

        vqe_objects = [
            self._stage_object(
                "vqe_circuit",
                record.vqe_circuit_id,
                record.qubit_hamiltonian_id,
                record.status,
            )
            for record in resources["vqe_circuits"]
        ]
        vqe_objects.extend(
            self._stage_object(
                "vqe_execution",
                record.execution_id,
                record.vqe_circuit_id,
                record.status,
            )
            for record in resources["vqe_executions"]
        )
        add_stage("vqe", vqe_objects)
        self._enrich_workflow_stage_metadata(stages, resources)
        return stages

    @staticmethod
    def _enrich_workflow_stage_metadata(stages: list[dict], resources: dict) -> None:
        """Attach auditable timestamps and warnings without making the client infer missing research evidence."""
        metadata_by_object: dict[tuple[str, str], dict] = {}

        def register(object_type: str, object_id: str | None, record) -> None:
            if not object_id:
                return
            created_at = getattr(record, "created_at", None)
            warnings = getattr(record, "warnings", []) or []
            metadata_by_object[(object_type, object_id)] = {
                "created_at": created_at.isoformat() if created_at else None,
                "warnings": warnings if isinstance(warnings, list) else [],
            }

        register("structure_file", getattr(resources.get("source_file"), "file_id", None), resources.get("source_file"))
        register("parsed_structure", getattr(resources.get("structure"), "structure_id", None), resources.get("structure"))
        record_groups = (
            ("benchmark_case", "benchmark_case_id", resources["benchmark_cases"]),
            ("active_site", "active_site_id", resources["active_sites"]),
            ("adsorption_model", "adsorption_model_id", resources["adsorption_models"]),
            ("geometry_optimization", "geometry_optimization_id", resources["geometry_optimizations"]),
            ("dft_import", "dft_import_id", resources["dft_imports"]),
            ("dft_calculation", "dft_calculation_id", resources["dft_calculations"]),
            ("quantum_region", "quantum_region_id", resources["quantum_regions"]),
            ("electronic_structure_candidate", "candidate_id", resources["electronic_candidates"]),
            ("active_space", "active_space_id", resources["active_spaces"]),
            ("fermionic_hamiltonian", "hamiltonian_id", resources["fermionic_hamiltonians"]),
            ("qubit_hamiltonian", "qubit_hamiltonian_id", resources["qubit_hamiltonians"]),
            ("classical_reference", "reference_id", resources["classical_references"]),
            ("vqe_circuit", "vqe_circuit_id", resources["vqe_circuits"]),
            ("vqe_execution", "execution_id", resources["vqe_executions"]),
        )
        for object_type, identifier, records in record_groups:
            for record in records:
                register(object_type, getattr(record, identifier, None), record)

        for stage in stages:
            for stage_object in stage["objects"]:
                stage_object.update(metadata_by_object.get((stage_object["object_type"], stage_object["object_id"]), {}))
            warnings = list(dict.fromkeys(
                warning
                for stage_object in stage["objects"]
                for warning in stage_object.get("warnings", [])
                if isinstance(warning, str)
            ))
            stage["warnings"] = warnings
            stage["created_at"] = next(
                (stage_object["created_at"] for stage_object in reversed(stage["objects"]) if stage_object.get("created_at")),
                None,
            )

    @staticmethod
    def _stage_object(
        object_type: str,
        object_id: str,
        parent_object_id: str | None,
        status: str,
    ) -> dict:
        return {
            "object_type": object_type,
            "object_id": object_id,
            "parent_object_id": parent_object_id,
            "status": status,
        }

    def _resolve_workflow_artifact(
        self,
        workflow_id: str,
        artifact_id: str,
        owner_user_id: int,
    ) -> dict:
        resources = self.repository.get_workflow_resources(workflow_id, owner_user_id)
        if resources is None:
            raise StructureModelingError("workflow_not_found", "未找到结构建模工作流。", 404)
        artifact = next(
            (
                item
                for item in self._workflow_artifact_entries(resources)
                if item["artifact_id"] == artifact_id
            ),
            None,
        )
        if artifact is None:
            raise StructureModelingError("artifact_not_found", "未找到该工作流的 Artifact。", 404)
        artifact_path = Path(artifact["path"]).resolve()
        allowed_roots = (
            STRUCTURE_UPLOAD_ROOT.resolve(),
            STRUCTURE_ARTIFACT_ROOT.resolve(),
            DFT_RUN_ROOT.resolve(),
            RESEARCH_BENCHMARK_ROOT.resolve(),
        )
        if not any(self._is_path_within(artifact_path, root) for root in allowed_roots):
            raise StructureModelingError("artifact_path_invalid", "Artifact 存储路径不受信任。", 409)
        if not artifact_path.is_file():
            raise StructureModelingError("artifact_unavailable", "Artifact 文件不存在或不可读取。", 404)
        media_type = mimetypes.guess_type(artifact["filename"])[0] or "application/octet-stream"
        return {
            **artifact,
            "path": artifact_path,
            "workflow_id": workflow_id,
            "media_type": media_type,
            "size_bytes": artifact_path.stat().st_size,
            "checksum_sha256": self._hash_file(artifact_path, "sha256"),
            "download_url": (
                f"/api/platform/structure-screening-workflows/{workflow_id}/artifacts/"
                f"{artifact_id}/download"
            ),
        }

    @staticmethod
    def _is_path_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _workflow_artifact_entries(self, resources: dict) -> list[dict]:
        entries: list[dict] = []

        def add(
            record,
            path_value: str | None,
            role: str,
            resource_type: str,
            resource_id: str,
            stage_name: str,
            artifact_id: str | None = None,
            filename: str | None = None,
        ) -> None:
            if not path_value:
                return
            path = Path(path_value)
            entries.append(
                {
                    "artifact_id": artifact_id or path.stem,
                    "artifact_role": role,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "stage_name": stage_name,
                    "filename": filename or path.name,
                    "path": path,
                }
            )

        source_file = resources["source_file"]
        if source_file is not None:
            add(
                source_file,
                source_file.storage_path,
                "source_structure",
                "structure_file",
                source_file.file_id,
                "structure",
                artifact_id=source_file.file_id,
                filename=source_file.original_filename,
            )
        for record in self._linked_benchmark_cases(resources):
            add(
                record,
                record.structure_artifact_path,
                "benchmark_structure",
                "benchmark_case",
                record.benchmark_case_id,
                "structure",
            )
        for record in resources["literature_candidates"]:
            add(
                record,
                record.coordinate_artifact_path,
                "literature_candidate_geometry",
                "research_benchmark_candidate",
                record.candidate_id,
                "structure",
            )
        for record in resources["adsorption_models"]:
            add(record, record.geometry_artifact_path, "initial_geometry", "adsorption_model", record.adsorption_model_id, "adsorption_model")
        for record in resources["geometry_optimizations"]:
            add(record, record.geometry_artifact_path, "optimized_geometry", "geometry_optimization", record.geometry_optimization_id, "geometry_and_dft")
        for record in resources["dft_imports"]:
            add(record, record.geometry_artifact_path, "dft_geometry", "dft_import", record.dft_import_id, "geometry_and_dft")
            add(record, record.source_artifact_path, "dft_source", "dft_import", record.dft_import_id, "geometry_and_dft")
        for record in resources["dft_calculations"]:
            add(record, record.input_artifact_path, "dft_input", "dft_calculation", record.dft_calculation_id, "geometry_and_dft")
            add(record, record.output_artifact_path, "dft_output", "dft_calculation", record.dft_calculation_id, "geometry_and_dft")
        for record in resources["quantum_regions"]:
            add(record, record.geometry_artifact_path, "quantum_region_geometry", "quantum_region", record.quantum_region_id, "quantum_region")
        for record in resources["electronic_candidates"]:
            add(record, record.log_artifact_path, "scf_log", "electronic_structure_candidate", record.candidate_id, "quantum_region")
            add(record, record.result_artifact_path, "scf_result", "electronic_structure_candidate", record.candidate_id, "quantum_region")
        for record in resources["fermionic_hamiltonians"]:
            add(record, record.artifact_path, "fermionic_hamiltonian", "fermionic_hamiltonian", record.hamiltonian_id, "hamiltonian")
        for record in resources["classical_references"]:
            add(record, record.artifact_path, "classical_reference", "classical_reference", record.reference_id, "hamiltonian")
        for record in resources["qubit_hamiltonians"]:
            add(record, record.pauli_artifact_path, "pauli_hamiltonian", "qubit_hamiltonian", record.qubit_hamiltonian_id, "hamiltonian")
        for record in resources["vqe_circuits"]:
            add(record, record.qasm_artifact_path, "qasm", "vqe_circuit", record.vqe_circuit_id, "vqe")
            add(record, record.measurement_plan_artifact_path, "measurement_plan", "vqe_circuit", record.vqe_circuit_id, "vqe")
        for record in resources["vqe_executions"]:
            add(record, record.iteration_artifact_path, "vqe_iterations", "vqe_execution", record.execution_id, "vqe")
        unique_entries: dict[str, dict] = {}
        for entry in entries:
            unique_entries.setdefault(entry["artifact_id"], entry)
        return list(unique_entries.values())

    def _linked_benchmark_cases(self, resources: dict) -> list:
        """Associate benchmark artifacts through confirmed candidates or their immutable structure payload."""
        structure = resources["structure"]
        if structure is None:
            return []
        candidate_benchmark_ids = {
            record.benchmark_case_id
            for record in resources["electronic_candidates"]
            if record.benchmark_case_id
        }
        linked = []
        for record in resources["benchmark_cases"]:
            if record.benchmark_case_id in candidate_benchmark_ids:
                linked.append(record)
                continue
            try:
                artifact = self._read_json_artifact(record.structure_artifact_path)
            except StructureModelingError:
                logger.warning(
                    "Skipping unreadable benchmark Artifact while resolving workflow_id=%s benchmark_case_id=%s",
                    resources["workflow"].workflow_id,
                    record.benchmark_case_id,
                )
                continue
            if artifact.get("structure_id") == structure.structure_id:
                linked.append(record)
        return linked

    def _set_workflow_status(self, workflow_id: str, owner_user_id: int, status: str, event_type: str, event_payload: dict) -> None:
        workflow = self.repository.get_workflow(workflow_id, owner_user_id)
        if workflow is None:
            return
        payload = dict(workflow.payload or {})
        events = list(payload.get("events", []))
        events.append({"event_type": event_type, "payload": event_payload})
        payload["events"] = events
        self.repository.update_workflow(workflow_id, owner_user_id, status=status, payload=payload)
