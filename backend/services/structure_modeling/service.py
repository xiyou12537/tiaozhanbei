from __future__ import annotations

import hashlib
import json
import logging
import math
import mimetypes
import os
import re
import shutil
import subprocess
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
from ase.data import atomic_numbers, covalent_radii
from ase.io import read as ase_read
from ase.optimize import BFGS
from scipy.spatial import cKDTree
from sqlalchemy.exc import IntegrityError

from backend.database import SessionLocal
from backend.db.repositories.structure_modeling_repository import StructureModelingRepository
from backend.core.config import settings
from backend.services.dft_engine import Cp2kAdapter, DftEngineError, DftExecutionCancelled, QuantumEspressoAdapter
from backend.services.electronic_structure.docker_adapter import DockerPySCFAdapter, ElectronicStructureRuntimeError
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService
from backend.services.runtime_status import load_circuit_runtime, load_partition_pipeline
from backend.services.task_manager import task_manager
from backend.models_db import MolecularIdempotencyRecord

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
H_CAPPED_PREFLIGHT_TIMEOUT_SECONDS = 120
H_CAPPED_SERIAL_PREFLIGHT_TIMEOUT_SECONDS = 900
H_CAPPED_SERIAL_PREFLIGHT_CPU_COUNT = 4
H_CAPPED_SERIAL_PREFLIGHT_MEMORY_MB = 8 * 1024
REDUCED_LOCAL_MODEL_LABEL = "reduced_local_algorithm_benchmark"
LOCAL_COMPUTE_EXHAUSTED_STATUS = "local_compute_exhausted"
LITERATURE_FRAGMENT_MODEL_LABEL = "literature_fragment_algorithm_benchmark"
LITERATURE_FRAGMENT_SOURCE_CANDIDATE_ID = "8637"
LITERATURE_FRAGMENT_SOURCE_INDEX_SPACE = "candidate_8637_original"
LITERATURE_FRAGMENT_SOURCE_INDICES = (0, 1, 72, 73, 74, 75)
LITERATURE_FRAGMENT_ELEMENTS = ("Li", "Li", "S", "S", "S", "S")
LITERATURE_FRAGMENT_NEUTRAL_ELECTRON_COUNT = 70
LITERATURE_FRAGMENT_SCF_MULTIPLICITIES = (1, 3)
LITERATURE_FRAGMENT_SCF_TIMEOUT_SECONDS = 900
LITERATURE_FRAGMENT_SCF_CPU_COUNT = 2
LITERATURE_FRAGMENT_SCF_CONTAINER_MEMORY_MB = 2048
LITERATURE_FRAGMENT_SCF_PYSCF_MEMORY_MB = 1024
LITERATURE_FRAGMENT_CAS_REVIEW_ORBITAL_INDICES = tuple(range(31, 40))
LITERATURE_FRAGMENT_CAS_REVIEW_TIMEOUT_SECONDS = 120
REDUCED_LOCAL_CONTAINER_MEMORY_MB = 4000
REDUCED_LOCAL_PYSCF_MEMORY_MB = 3000
REDUCED_LOCAL_HOST_MEMORY_THRESHOLD_BYTES = 7 * 1024 * 1024 * 1024
REDUCED_LOCAL_SCF_TIMEOUT_SECONDS = 900
REDUCED_LOCAL_FULL_SCF_CPU_COUNT = 1
REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB = 2560
REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB = 1024
REDUCED_LOCAL_FULL_SCF_HOST_MEMORY_THRESHOLD_BYTES = 4 * 1024 * 1024 * 1024
REDUCED_LOCAL_FULL_SCF_MIN_DISK_FREE_BYTES = 10 * 1024 * 1024 * 1024
REDUCED_LOCAL_FULL_SCF_PEAK_STOP_RATIO = 0.85
REDUCED_LOCAL_NEWTON_MAX_CYCLES = 50
REDUCED_LOCAL_NEWTON_STAGNATION_WINDOW = 5
REDUCED_LOCAL_UKS_CPU_COUNT = 2
REDUCED_LOCAL_UKS_MAX_CYCLES = 100
REDUCED_LOCAL_UKS_OSCILLATION_MINIMUM_CYCLES = 12
REDUCED_LOCAL_UKS_OSCILLATION_WINDOW = 6
REDUCED_LOCAL_UKS_OSCILLATION_REVERSALS = 3
REDUCED_LOCAL_UKS_OSCILLATION_MINIMUM_GRADIENT = 1e-3
REDUCED_LOCAL_UKS_RAPID_GROWTH_MULTIPLIER = 10.0
REDUCED_LOCAL_CALIBRATION_TIMEOUT_SECONDS = 300
REDUCED_LOCAL_CALIBRATION_CPU_COUNT = 1
REDUCED_LOCAL_CALIBRATION_CONTAINER_MEMORY_MB = 2048
REDUCED_LOCAL_CALIBRATION_PYSCF_MEMORY_MB = 1024
REDUCED_LOCAL_CALIBRATION_HOST_MEMORY_THRESHOLD_BYTES = int(3.5 * 1024 * 1024 * 1024)
REDUCED_LOCAL_CALIBRATION_HOST_MEMORY_RESERVE_BYTES = int(1.5 * 1024 * 1024 * 1024)
REDUCED_LOCAL_CALIBRATION_MIN_DISK_FREE_BYTES = 10 * 1024 * 1024 * 1024
REDUCED_LOCAL_CALIBRATION_PEAK_STOP_RATIO = 0.85
DEF2_SVP_SPHERICAL_AO_ESTIMATES = {"H": 5, "Li": 5, "C": 14, "N": 14, "S": 18, "Fe": 31}
H_CAPPED_INNER_GRAPH_SHELLS = 1
H_CAPPED_OUTER_GRAPH_SHELLS = 2
H_CAPPED_ADSORBATE_CONTACT_DISTANCE_ANGSTROM = 3.2
H_CAPPED_COVALENT_BOND_TOLERANCE_ANGSTROM = 0.25
H_CAPPED_CARBON_HYDROGEN_BOND_LENGTH_ANGSTROM = 1.09
SUPPORTED_FILE_TYPES = {"xyz", "cif", "mol", "sdf", "poscar", "contcar"}
ASE_FORMATS = {"xyz": "xyz", "cif": "cif", "mol": "mol", "sdf": "sdf", "poscar": "vasp", "contcar": "vasp"}
TRANSITION_METALS = {"Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Mo", "W", "Nb", "Ta"}
ADSORPTION_ORIENTATIONS = ("li_end_toward_site", "s_chain_toward_site", "side_on_adsorption")
CONFORMATION_DISTANCE_OFFSETS_ANGSTROM = (0.0, -0.25, 0.25)
DATA_ROOT = Path(
    os.environ.get(
        "PLATFORM_DATA_ROOT",
        Path(__file__).resolve().parents[3] / "data",
    )
).resolve()
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
QUANTUM_CLOSURE_BENCHMARK_KEY = "fe-n4-c66-li2s4-literature-v1"
QUANTUM_CLOSURE_MAX_ACTIVE_ORBITALS = 4
QUANTUM_CLOSURE_MAX_QUBITS = 8
QUANTUM_CLOSURE_MAX_FCI_DETERMINANTS = 50_000
QUANTUM_CLOSURE_VARIATIONAL_TOLERANCE_HARTREE = 1e-8
QUANTUM_CLOSURE_PAULI_COEFFICIENT_CUTOFF = 1e-12


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
        input_purpose: str,
        idempotency_key: str | None = None,
    ) -> dict:
        if input_purpose not in {
            "legacy_screening",
            "molecular_logical_circuit",
        }:
            raise StructureModelingError(
                "input_purpose_invalid",
                "input_purpose 必须显式为 legacy_screening 或 molecular_logical_circuit。",
                422,
            )
        file_type = self._detect_file_type(original_filename, content)
        if input_purpose == "molecular_logical_circuit" and file_type != "xyz":
            raise StructureModelingError(
                "molecular_xyz_required",
                "M-B 分子逻辑线路入口仅接受 XYZ。",
                422,
            )
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise StructureModelingError("file_too_large", "文件超过 20 MB 限制。", 413)
        request_sha256 = None
        idempotency_key_hash = None
        if idempotency_key is not None:
            from backend.services.molecular_workflow.canonical import (
                rfc8785_jcs_sha256_v1,
            )

            if not 1 <= len(idempotency_key.encode("utf-8")) <= 128:
                raise StructureModelingError(
                    "idempotency_key_invalid",
                    "Idempotency-Key 必须为 1–128 UTF-8 bytes。",
                    422,
                )
            idempotency_key_hash = hashlib.sha256(
                idempotency_key.encode("utf-8")
            ).hexdigest()
            request_sha256 = rfc8785_jcs_sha256_v1(
                {
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                    "description": description,
                    "input_purpose": input_purpose,
                    "material_family": material_family,
                    "material_name": material_name,
                    "original_filename": original_filename,
                    "route_schema": "structure_file_upload_v1",
                }
            )[1]
            replay = self._reserve_structure_upload_idempotency(
                owner_user_id,
                idempotency_key_hash,
                request_sha256,
            )
            if replay is not None:
                return replay

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
                "input_purpose": input_purpose,
                "file_size_bytes": len(content),
                "file_hash": hashlib.sha256(content).hexdigest(),
                "storage_path": str(storage_path),
                "parse_status": "uploaded",
            }
        )
        response = self.serialize_file(record)
        if idempotency_key_hash and request_sha256:
            self._complete_structure_upload_idempotency(
                owner_user_id,
                idempotency_key_hash,
                request_sha256,
                response,
            )
        return response

    @staticmethod
    def _reserve_structure_upload_idempotency(
        owner_user_id: int,
        key_hash: str,
        request_sha256: str,
    ) -> dict | None:
        route_scope = "structure_file_upload"
        session = SessionLocal()
        try:
            existing = (
                session.query(MolecularIdempotencyRecord)
                .filter_by(
                    owner_user_id=owner_user_id,
                    route_scope=route_scope,
                    idempotency_key_hash=key_hash,
                )
                .first()
            )
            if existing is not None:
                if existing.request_sha256 != request_sha256:
                    raise StructureModelingError(
                        "idempotency_conflict",
                        "同一 Idempotency-Key 已绑定不同上传请求。",
                        409,
                    )
                if not existing.terminal:
                    raise StructureModelingError(
                        "idempotency_request_in_progress",
                        "同一上传请求仍在处理中。",
                        409,
                    )
                return dict(existing.response_payload or {})
            session.add(
                MolecularIdempotencyRecord(
                    idempotency_id=f"mid_{uuid4().hex}",
                    owner_user_id=owner_user_id,
                    route_scope=route_scope,
                    parent_resource_id="structure_file_upload",
                    idempotency_key_hash=key_hash,
                    request_sha256=request_sha256,
                    terminal=0,
                )
            )
            session.commit()
            return None
        except IntegrityError as exc:
            session.rollback()
            raise StructureModelingError(
                "idempotency_request_in_progress",
                "并发上传已占用该 Idempotency-Key。",
                409,
            ) from exc
        finally:
            session.close()

    @staticmethod
    def _complete_structure_upload_idempotency(
        owner_user_id: int,
        key_hash: str,
        request_sha256: str,
        response: dict,
    ) -> None:
        session = SessionLocal()
        try:
            record = (
                session.query(MolecularIdempotencyRecord)
                .filter_by(
                    owner_user_id=owner_user_id,
                    route_scope="structure_file_upload",
                    idempotency_key_hash=key_hash,
                    request_sha256=request_sha256,
                )
                .one()
            )
            record.response_resource_type = "structure_file"
            record.response_resource_id = response["file_id"]
            record.response_status_code = 201
            record.response_payload = response
            record.terminal = 1
            record.completed_at = datetime.utcnow()
            session.commit()
        finally:
            session.close()

    def parse_structure_file(self, file_id: str, owner_user_id: int) -> dict:
        file_record = self._get_file_or_raise(file_id, owner_user_id)
        if file_record.structure_id:
            structure = self.repository.get_structure(file_record.structure_id, owner_user_id)
            if structure is not None:
                return self.serialize_parse_result(file_record, structure)

        self.repository.update_file(file_id, owner_user_id, parse_status="parsing", parse_error_code=None, parse_error_message=None)
        try:
            if file_record.input_purpose == "molecular_logical_circuit":
                from backend.services.molecular_workflow.canonical import (
                    StrictXyzError,
                    parse_strict_xyz_file,
                )

                try:
                    parsed = parse_strict_xyz_file(
                        file_record.storage_path
                    ).parsed_structure
                except StrictXyzError as exc:
                    raise StructureModelingError(
                        exc.code,
                        str(exc),
                        422,
                    ) from exc
            else:
                parsed = self._parse_file(file_record.storage_path, file_record.file_type)
            validation = self._validate_structure(parsed)
            structure_id = self._new_id("st")
            is_legacy = file_record.input_purpose == "legacy_screening"
            workflow_id = self._new_id("ssw") if is_legacy else None
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
            if is_legacy:
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
            {"quantum_region_id": quantum_region_id, "source_type": "adsorption_model", "adsorption_model_id": adsorption_model_id, "geometry_optimization_id": optimization.geometry_optimization_id, "owner_user_id": owner_user_id, "region_atom_indices": region_indices, "frozen_environment_atom_indices": frozen_indices, "embedding_method": "frozen_atoms", "total_charge": request.get("total_charge"), "spin_multiplicity": request.get("spin_multiplicity"), "geometry_source_type": optimization.source_type, "geometry_method": optimization.method_name, "geometry_artifact_path": str(artifact_path), "status": status, "warnings": warnings}
        )
        self._set_workflow_status(structure.workflow_id, owner_user_id, status, "quantum_region_built", {"quantum_region_id": region.quantum_region_id})
        return self.serialize_quantum_region(region)

    def build_h_capped_quantum_region_candidates(self, workflow_id: str, owner_user_id: int) -> dict:
        """Create two graph-boundary H-capped clusters without assigning a scientific electronic state."""
        resources = self.repository.get_workflow_resources(workflow_id, owner_user_id)
        if resources is None:
            raise StructureModelingError("workflow_not_found", "未找到结构工作流或无权访问。", 404)
        selections = resources.get("literature_selections", [])
        if len(selections) != 1:
            raise StructureModelingError("literature_selection_required", "H 封端预检要求工作流关联唯一的文献候选。", 409)
        selection = selections[0]
        candidate = next((item for item in resources["literature_candidates"] if item.candidate_id == selection.candidate_id), None)
        if candidate is None:
            raise StructureModelingError("literature_candidate_not_found", "无法回溯冻结的文献候选。", 409)
        structure = resources["structure"]
        active_site = next((item for item in resources["active_sites"] if item.status == "confirmed"), None)
        if active_site is None:
            raise StructureModelingError("active_site_not_confirmed", "必须先确认 Fe-N4 活性位点。", 409)
        adsorption_model = next(
            (item for item in resources["adsorption_models"] if item.active_site_id == active_site.active_site_id),
            None,
        )
        if adsorption_model is None:
            raise StructureModelingError("adsorption_model_not_found", "未找到与 Fe-N4 位点关联的 Li2S4 构型。", 409)
        geometry = next(
            (
                item
                for item in resources["geometry_optimizations"]
                if item.adsorption_model_id == adsorption_model.adsorption_model_id and item.status == "completed"
            ),
            None,
        )
        if geometry is None:
            raise StructureModelingError("geometry_not_ready", "未找到已完成的文献几何。", 409)
        full_geometry = self._read_json_artifact(geometry.geometry_artifact_path)
        full_sites = full_geometry["atomic_sites"]
        host_atom_count = structure.atom_count
        if len(full_sites) <= host_atom_count:
            raise StructureModelingError("adsorbate_geometry_missing", "文献几何中缺少 Li2S4，不能建立封端簇。", 422)
        source_sha256 = self._hash_file(Path(candidate.coordinate_artifact_path), "sha256")
        geometry_sha256 = self._hash_file(Path(geometry.geometry_artifact_path), "sha256")
        variants = (
            ("cluster_inner", H_CAPPED_INNER_GRAPH_SHELLS),
            ("cluster_outer", H_CAPPED_OUTER_GRAPH_SHELLS),
        )
        records = []
        for label, expansion_shells in variants:
            cluster = self._build_h_capped_cluster(
                full_sites=full_sites,
                host_atom_count=host_atom_count,
                active_site=active_site,
                expansion_shells=expansion_shells,
                label=label,
            )
            quantum_region_id = self._new_id("qr_hcap")
            artifact_path = self._write_json_artifact(
                quantum_region_id,
                {
                    "source_type": "literature_open_dataset",
                    "research_benchmark_id": selection.benchmark_id,
                    "research_benchmark_candidate_id": candidate.candidate_id,
                    "source_candidate_id": candidate.source_candidate_id,
                    "source_candidate_sha256": source_sha256,
                    "geometry_optimization_id": geometry.geometry_optimization_id,
                    "geometry_sha256": geometry_sha256,
                    "workflow_id": workflow_id,
                    "active_site_id": active_site.active_site_id,
                    "boundary_label": label,
                    **cluster,
                    "model_limitations": [
                        "有限 H 封端簇仅用于局部 Hamiltonian 敏感性预检，不等同于周期性材料模型。",
                        "电荷、自旋和 CAS 均未在此阶段确认。",
                    ],
                },
            )
            record = self.repository.create_quantum_region(
                {
                    "quantum_region_id": quantum_region_id,
                    "source_type": "adsorption_model",
                    "adsorption_model_id": adsorption_model.adsorption_model_id,
                    "geometry_optimization_id": geometry.geometry_optimization_id,
                    "owner_user_id": owner_user_id,
                    "region_atom_indices": cluster["region_atom_indices"],
                    "frozen_environment_atom_indices": cluster["frozen_environment_atom_indices"],
                    "embedding_method": "h_link_atoms_graph_cut",
                    "total_charge": None,
                    "spin_multiplicity": None,
                    "geometry_source_type": geometry.source_type,
                    "geometry_method": geometry.method_name,
                    "geometry_artifact_path": str(artifact_path),
                    "preflight_artifact_path": None,
                    "status": "needs_model_review",
                    "warnings": [
                        "H 封端有限簇候选，等待短时 SCF/CAS 敏感性预检。",
                        "不应用于声明周期性 DFT 或催化性能结论。",
                    ],
                }
            )
            records.append(self.serialize_quantum_region(record))
        self._set_workflow_status(
            workflow_id,
            owner_user_id,
            "needs_model_review",
            "h_capped_quantum_regions_created",
            {"quantum_region_ids": [record["quantum_region_id"] for record in records]},
        )
        return {"workflow_id": workflow_id, "status": "needs_model_review", "candidates": records}

    def build_reduced_local_algorithm_benchmark(
        self,
        parent_quantum_region_id: str,
        owner_user_id: int,
    ) -> dict:
        """Build the minimal Fe-N4/Li2S4 local cluster without relabelling it as a material model."""
        parent = self.repository.get_quantum_region(parent_quantum_region_id, owner_user_id)
        if parent is None or parent.embedding_method != "h_link_atoms_graph_cut":
            raise StructureModelingError("h_capped_reference_not_found", "缩减模型必须从冻结的内层 H 封端参考模型创建。", 409)
        parent_payload = self._read_json_artifact(parent.geometry_artifact_path)
        active_site = self.repository.get_active_site(parent_payload["active_site_id"], owner_user_id)
        geometry = self.repository.get_geometry_optimization(parent.geometry_optimization_id, owner_user_id)
        if active_site is None or geometry is None:
            raise StructureModelingError("reduced_model_provenance_missing", "缩减模型缺少已确认 Fe-N4 位点或源几何。", 409)
        source_payload = self._read_json_artifact(geometry.geometry_artifact_path)
        cluster = self._build_reduced_local_cluster(source_payload["atomic_sites"], active_site)
        parent_indices = set(parent.region_atom_indices or [])
        required_indices = set(cluster["region_atom_indices"])
        if not required_indices.issubset(parent_indices):
            raise StructureModelingError("reduced_model_outside_parent", "缩减模型包含不在冻结内层参考模型中的原子。", 409)
        quantum_region_id = self._new_id("qr_reduced")
        artifact_path = self._write_json_artifact(
            quantum_region_id,
            {
                "model_label": REDUCED_LOCAL_MODEL_LABEL,
                "parent_quantum_region_id": parent_quantum_region_id,
                "source_type": parent.geometry_source_type,
                "geometry_optimization_id": parent.geometry_optimization_id,
                "source_candidate_sha256": parent_payload["source_candidate_sha256"],
                "active_site_id": active_site.active_site_id,
                "boundary_label": REDUCED_LOCAL_MODEL_LABEL,
                **cluster,
                "model_limitations": [
                    "该缩减局部模型仅用于局部 Hamiltonian、Pauli 映射和 simulator VQE 一致性算法基准。",
                    "不得标注为文献体系复现、论文结果验证通过或真实催化性能验证。",
                    "47 原子内层 H 封端模型继续保留为正式参考模型，未被替换。",
                ],
            },
        )
        record = self.repository.create_quantum_region(
            {
                "quantum_region_id": quantum_region_id,
                "source_type": "adsorption_model",
                "adsorption_model_id": parent.adsorption_model_id,
                "geometry_optimization_id": parent.geometry_optimization_id,
                "owner_user_id": owner_user_id,
                "region_atom_indices": cluster["region_atom_indices"],
                "frozen_environment_atom_indices": cluster["deleted_atom_indices"],
                "embedding_method": "h_link_atoms_reduced_local_algorithm_benchmark",
                "total_charge": None,
                "spin_multiplicity": None,
                "geometry_source_type": parent.geometry_source_type,
                "geometry_method": REDUCED_LOCAL_MODEL_LABEL,
                "geometry_artifact_path": str(artifact_path),
                "preflight_artifact_path": None,
                "status": "needs_model_review",
                "warnings": [
                    "仅限局部算法基准；不代表周期性文献体系。",
                    "电荷、自旋和 CAS 尚未确认。",
                ],
            }
        )
        return {**self.serialize_quantum_region(record), **self._reduced_cluster_summary(cluster)}

    def freeze_reduced_local_compute_branch(self, quantum_region_id: str, owner_user_id: int) -> dict:
        """Freeze a reduced-local SCF route while retaining its numerical diagnostics."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_reduced_local_algorithm_benchmark":
            raise StructureModelingError("reduced_local_model_not_found", "Reduced local model was not found.", 404)
        if region.status == LOCAL_COMPUTE_EXHAUSTED_STATUS and region.preflight_artifact_path:
            report = self._read_json_artifact(region.preflight_artifact_path)
            return {**report, "preflight_artifact_id": Path(region.preflight_artifact_path).stem}

        previous_report = self._read_json_artifact(region.preflight_artifact_path) if region.preflight_artifact_path else {}
        checkpoint_directory = previous_report.get("checkpoint_directory")
        evidence_paths = [
            Path(region.geometry_artifact_path),
            Path(region.preflight_artifact_path) if region.preflight_artifact_path else None,
            STRUCTURE_ARTIFACT_ROOT / f"{previous_report['result_artifact_id']}.json"
            if previous_report.get("result_artifact_id")
            else None,
        ]
        if checkpoint_directory:
            checkpoint_root = Path(checkpoint_directory)
            evidence_paths.extend(
                checkpoint_root / name
                for name in ("source_uhf.chk", "scf.chk", "scf_progress.jsonl", "checkpoint_validation.json")
            )
        retained_evidence = []
        for path in evidence_paths:
            if path is None:
                continue
            retained_evidence.append(
                {
                    "path": str(path),
                    "exists": path.is_file(),
                    "size_bytes": path.stat().st_size if path.is_file() else None,
                    "sha256": self._file_sha256(path) if path.is_file() else None,
                }
            )
        report = {
            "report_type": "reduced_local_compute_freeze",
            "quantum_region_id": quantum_region_id,
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "status": LOCAL_COMPUTE_EXHAUSTED_STATUS,
            "automatic_scf_parameter_search_disabled": True,
            "retained_failure_evidence": retained_evidence,
            "previous_preflight_status": previous_report.get("status"),
            "uks_preconditioner_interpretation": "Current UKS/PBE density preconditioner did not converge; this does not invalidate the frozen model.",
            "model_validity": "not_assessed",
            "electronic_structure_candidate_created": False,
            "cas_hamiltonian_fci_pauli_vqe_created": False,
            "scientific_validation": False,
        }
        report_path = self._write_json_artifact(self._new_id("reduced_local_compute_freeze"), report)
        warnings = list(region.warnings or [])
        warnings.append("Local SCF parameter route is frozen after retained numerical diagnostics; model validity is not assessed.")
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status=LOCAL_COMPUTE_EXHAUSTED_STATUS,
            warnings=warnings,
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    @staticmethod
    def _assert_reduced_local_compute_not_exhausted(region) -> None:
        if region.status == LOCAL_COMPUTE_EXHAUSTED_STATUS:
            raise StructureModelingError(
                "local_compute_exhausted",
                "This reduced-local compute branch is frozen and cannot start another automatic SCF strategy.",
                409,
            )

    def create_literature_fragment_algorithm_benchmark(
        self,
        parent_quantum_region_id: str,
        owner_user_id: int,
    ) -> dict:
        """Create an immutable Li2S4 algorithm benchmark from candidate 8637 coordinates."""
        parent_region = self.repository.get_quantum_region(parent_quantum_region_id, owner_user_id)
        if parent_region is None:
            raise StructureModelingError("parent_quantum_region_not_found", "Parent quantum region was not found.", 404)
        source_candidate = self.repository.get_selected_research_benchmark_candidate_by_source_id(
            owner_user_id,
            LITERATURE_FRAGMENT_SOURCE_CANDIDATE_ID,
        )
        if source_candidate is None:
            raise StructureModelingError("literature_source_candidate_not_selected", "Candidate 8637 is not selected for this owner.", 409)

        source_path = Path(source_candidate.coordinate_artifact_path)
        source_payload = self._read_json_artifact(str(source_path))
        source_sites = self._extract_literature_fragment_source_sites(source_payload)
        fragment_atomic_sites = [
            {
                "index": local_index,
                "element": source_site["element"],
                "position_angstrom": list(source_site["position_angstrom"]),
                "source_original_index": source_site["index"],
            }
            for local_index, source_site in enumerate(source_sites)
        ]
        neutral_electron_count = sum(atomic_numbers[site["element"]] for site in source_sites)
        if neutral_electron_count != LITERATURE_FRAGMENT_NEUTRAL_ELECTRON_COUNT:
            raise StructureModelingError("literature_fragment_electron_count_invalid", "Li2S4 neutral electron audit failed.", 409)
        mapping = self._reordered_local_geometry_mapping(parent_region.geometry_artifact_path, source_sites)
        source_candidate_sha256 = self._file_sha256(source_path)
        fragment_sha256 = self._structure_sha256(source_sites)
        engine_structure_sha256 = self._structure_sha256(fragment_atomic_sites)
        quantum_region_id = self._new_id("qr_literature_fragment")
        artifact_path = self._write_json_artifact(
            quantum_region_id,
            {
                "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
                "source_index_space": LITERATURE_FRAGMENT_SOURCE_INDEX_SPACE,
                "source_candidate_id": LITERATURE_FRAGMENT_SOURCE_CANDIDATE_ID,
                "research_benchmark_candidate_id": source_candidate.candidate_id,
                "source_candidate_artifact_path": str(source_path),
                "source_candidate_sha256": source_candidate_sha256,
                "source_original_atom_indices": list(LITERATURE_FRAGMENT_SOURCE_INDICES),
                "source_original_atomic_sites": source_sites,
                "atomic_sites": fragment_atomic_sites,
                "element_sequence": list(LITERATURE_FRAGMENT_ELEMENTS),
                "chemical_formula": "Li2S4",
                "chemical_formula_valid": True,
                "neutral_electron_count": neutral_electron_count,
                "neutral_electron_count_expected": LITERATURE_FRAGMENT_NEUTRAL_ELECTRON_COUNT,
                "fragment_sha256": fragment_sha256,
                "engine_structure_sha256": engine_structure_sha256,
                "geometry_optimization_performed": False,
                "coordinates_moved": False,
                "scientific_adsorption_validation": False,
                "reordered_local_geometry_mapping": mapping,
                "coordinate_source_rule": "Only candidate_8637_original coordinates are calculation input.",
                "allowed_stage": "charge_spin_scf_preflight",
                "cas_hamiltonian_fci_pauli_vqe_created": False,
            },
        )
        record = self.repository.create_quantum_region(
            {
                "quantum_region_id": quantum_region_id,
                "source_type": "adsorption_model",
                "adsorption_model_id": parent_region.adsorption_model_id,
                "geometry_optimization_id": parent_region.geometry_optimization_id,
                "owner_user_id": owner_user_id,
                "region_atom_indices": list(LITERATURE_FRAGMENT_SOURCE_INDICES),
                "frozen_environment_atom_indices": [],
                "embedding_method": "isolated_literature_fragment",
                "total_charge": 0,
                "spin_multiplicity": None,
                "geometry_source_type": LITERATURE_FRAGMENT_SOURCE_INDEX_SPACE,
                "geometry_method": LITERATURE_FRAGMENT_MODEL_LABEL,
                "geometry_artifact_path": str(artifact_path),
                "preflight_artifact_path": None,
                "status": "fragment_scf_preflight_ready",
                "warnings": [
                    "Algorithm benchmark only; this is not an Fe-N4/Li2S4 adsorption validation.",
                    "Singlet and triplet remain unconfirmed comparison candidates.",
                    "No CAS, Hamiltonian, FCI, Pauli, or VQE may be created before independent review.",
                ],
            }
        )
        return {
            **self.serialize_quantum_region(record),
            "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
            "source_candidate_sha256": source_candidate_sha256,
            "fragment_sha256": fragment_sha256,
            "neutral_electron_count": neutral_electron_count,
            "scientific_adsorption_validation": False,
        }

    def run_literature_fragment_scf_preflight(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        timeout_seconds: int = LITERATURE_FRAGMENT_SCF_TIMEOUT_SECONDS,
        spin_multiplicities: tuple[int, ...] | None = None,
    ) -> dict:
        """Run serial singlet/triplet UHF checks without promoting an algorithm fragment."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "isolated_literature_fragment":
            raise StructureModelingError("literature_fragment_not_found", "Literature fragment benchmark was not found.", 404)
        fragment = self._read_json_artifact(region.geometry_artifact_path)
        if fragment.get("model_label") != LITERATURE_FRAGMENT_MODEL_LABEL:
            raise StructureModelingError("literature_fragment_label_invalid", "Literature fragment label does not match.", 409)
        neutral_electron_count = sum(atomic_numbers[site["element"]] for site in fragment["atomic_sites"])
        if neutral_electron_count != LITERATURE_FRAGMENT_NEUTRAL_ELECTRON_COUNT:
            raise StructureModelingError("literature_fragment_electron_count_invalid", "Li2S4 neutral electron audit failed.", 409)

        requested_multiplicities = tuple(spin_multiplicities or LITERATURE_FRAGMENT_SCF_MULTIPLICITIES)
        if not requested_multiplicities or any(
            multiplicity not in LITERATURE_FRAGMENT_SCF_MULTIPLICITIES for multiplicity in requested_multiplicities
        ):
            raise StructureModelingError("literature_fragment_spin_request_invalid", "Only singlet and triplet are allowed.", 422)
        previous_preflight_artifact_path = region.preflight_artifact_path
        candidates = []
        for multiplicity in requested_multiplicities:
            self._validate_fragment_spin_parity(neutral_electron_count, 0, multiplicity)
            checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / self._new_id("literature_fragment_scf")
            checkpoint_directory.mkdir(parents=True, exist_ok=True)
            scf_options = self._literature_fragment_scf_options()
            try:
                result = self.electronic_structure_adapter.generate_active_space_candidates(
                    {
                        "atomic_sites": fragment["atomic_sites"],
                        "total_charge": 0,
                        "spin_multiplicity": multiplicity,
                        "basis_set": "def2-svp",
                        "requested_methods": ["UHF"],
                        "max_scf_attempts": 1,
                        "spin_contamination_threshold": 0.5,
                        "include_active_space_candidates": False,
                        "scf_options": scf_options,
                    },
                    timeout_seconds=timeout_seconds,
                    execution_options={
                        "cpu_count": LITERATURE_FRAGMENT_SCF_CPU_COUNT,
                        "memory_limit_mb": LITERATURE_FRAGMENT_SCF_CONTAINER_MEMORY_MB,
                        "checkpoint_directory": str(checkpoint_directory),
                        "monitor_resources": True,
                        "terminate_at_memory_bytes": int(
                            LITERATURE_FRAGMENT_SCF_CONTAINER_MEMORY_MB * 1024 * 1024 * 0.85
                        ),
                    },
                )
            except ElectronicStructureRuntimeError as exc:
                result = {
                    "status": "failed",
                    "message": f"Literature fragment SCF failed: {exc}",
                    "basis_set": "def2-svp",
                    "scf_attempts": [],
                    "diagnostic": exc.diagnostic,
                }
            result.update(
                {
                    "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
                    "scientific_adsorption_validation": False,
                    "cas_hamiltonian_fci_pauli_vqe_created": False,
                    "preflight_only": True,
                }
            )
            result_path = self._write_json_artifact(self._new_id("literature_fragment_scf_result"), result)
            is_converged, exceeds_threshold, _ = self._electronic_structure_result_quality(result, 0.5)
            warnings = ["SCF preflight requires independent CAS review before candidate confirmation."]
            if result.get("message"):
                warnings.append(result["message"])
            if exceeds_threshold:
                warnings.append("Spin contamination exceeds the preflight threshold.")
            record = self.repository.create_electronic_structure_candidate(
                {
                    "candidate_id": self._new_id("esc_fragment"),
                    "quantum_region_id": quantum_region_id,
                    "benchmark_case_id": None,
                    "owner_user_id": owner_user_id,
                    "total_charge": 0,
                    "spin_multiplicity": multiplicity,
                    "scf_method": result.get("method_name"),
                    "basis_set": result.get("basis_set", "def2-svp"),
                    "converged": int(is_converged),
                    "scf_iterations": result.get("scf_attempts", []),
                    "total_energy_hartree": result.get("hf_total_energy_hartree"),
                    "spin_square_s2": result.get("spin_square"),
                    "expected_spin_square_s2": result.get("expected_spin_square"),
                    "spin_contamination_delta": result.get("spin_contamination"),
                    "spin_contamination_threshold": 0.5,
                    "quality_status": "needs_model_review",
                    "warnings": warnings,
                    "log_artifact_path": str(result_path),
                    "result_artifact_path": str(result_path),
                }
            )
            candidates.append(
                {
                    **self.serialize_electronic_structure_candidate(record),
                    "result_artifact_id": result_path.stem,
                    "checkpoint_directory": str(checkpoint_directory),
                    "orbital_evidence_available": bool(result.get("orbital_details")),
                }
            )

        report = {
            "report_type": "literature_fragment_charge_spin_scf_preflight",
            "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
            "quantum_region_id": quantum_region_id,
            "source_index_space": fragment["source_index_space"],
            "source_candidate_id": fragment["source_candidate_id"],
            "source_candidate_sha256": fragment["source_candidate_sha256"],
            "fragment_sha256": fragment["fragment_sha256"],
            "total_charge": 0,
            "neutral_electron_count": neutral_electron_count,
            "spin_multiplicities_compared": list(requested_multiplicities),
            "candidates": candidates,
            "previous_preflight_artifact_path": previous_preflight_artifact_path,
            "scientific_adsorption_validation": False,
            "cas_candidates_created": False,
            "cas_review_requirement": "Review Li-S/S-S frontier orbitals and S 3p projections before proposing CAS(2,2) or CAS(4,4).",
            "hamiltonian_fci_pauli_vqe_created": False,
        }
        report_path = self._write_json_artifact(self._new_id("literature_fragment_scf_preflight"), report)
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def generate_literature_fragment_cas_review(
        self,
        quantum_region_id: str,
        owner_user_id: int,
    ) -> dict:
        """Produce a checkpoint-backed CAS review without creating an active-space record or downstream artifacts."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "isolated_literature_fragment":
            raise StructureModelingError("literature_fragment_not_found", "Literature fragment benchmark was not found.", 404)
        fragment = self._read_json_artifact(region.geometry_artifact_path)
        if fragment.get("model_label") != LITERATURE_FRAGMENT_MODEL_LABEL:
            raise StructureModelingError("literature_fragment_label_invalid", "Literature fragment label does not match.", 409)
        if fragment.get("neutral_electron_count") != LITERATURE_FRAGMENT_NEUTRAL_ELECTRON_COUNT:
            raise StructureModelingError("literature_fragment_electron_count_invalid", "Li2S4 neutral electron audit failed.", 409)

        singlet_candidate, singlet_result = self._get_literature_fragment_singlet_reference(
            quantum_region_id,
            owner_user_id,
        )
        checkpoint_sha256 = singlet_result.get("execution_metadata", {}).get("checkpoint_sha256")
        if not checkpoint_sha256:
            raise StructureModelingError("literature_fragment_checkpoint_missing", "Singlet result has no checkpoint hash.", 409)
        checkpoint_path = self._find_checkpoint_by_sha256(checkpoint_sha256)
        structure_sha256 = self._structure_sha256(fragment["atomic_sites"])
        expected_checkpoint_metadata = {
            "checkpoint_sha256": checkpoint_sha256,
            "structure_sha256": structure_sha256,
            "basis_set": "def2-svp",
            "total_charge": 0,
            "spin_multiplicity": 1,
            "structure_basis_sha256": self._structure_basis_sha256(structure_sha256, "def2-svp"),
        }
        try:
            projection_result = self.electronic_structure_adapter.analyze_orbital_projections(
                {
                    "atomic_sites": fragment["atomic_sites"],
                    "total_charge": 0,
                    "spin_multiplicity": 1,
                    "basis_set": "def2-svp",
                    "orbital_indices": list(LITERATURE_FRAGMENT_CAS_REVIEW_ORBITAL_INDICES),
                    "expected_checkpoint_metadata": expected_checkpoint_metadata,
                    "scf_options": {"checkpoint_validation_source_path": "/inputs/scf.chk"},
                },
                timeout_seconds=LITERATURE_FRAGMENT_CAS_REVIEW_TIMEOUT_SECONDS,
                execution_options={
                    "cpu_count": 1,
                    "memory_limit_mb": 512,
                    "read_only_mounts": [{"source": str(checkpoint_path), "target": "/inputs/scf.chk"}],
                },
            )
        except ElectronicStructureRuntimeError as exc:
            failure_report = {
                "report_type": "literature_fragment_cas_candidate_review",
                "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
                "status": "failed",
                "confirmed_for_algorithm_benchmark": True,
                "ground_state_assessed": False,
                "scientific_adsorption_validation": False,
                "independent_cas_review_required": True,
                "checkpoint_sha256": checkpoint_sha256,
                "failure_diagnostic": exc.diagnostic,
                "cas_hamiltonian_fci_pauli_vqe_created": False,
            }
            failure_path = self._write_json_artifact(self._new_id("literature_fragment_cas_review"), failure_report)
            raise StructureModelingError(
                "literature_fragment_orbital_analysis_failed",
                f"Read-only singlet checkpoint orbital analysis failed; Artifact: {failure_path.name}",
                503,
            ) from exc

        if projection_result.get("checkpoint_validation", {}).get("status") != "passed":
            raise StructureModelingError("literature_fragment_checkpoint_validation_failed", "Singlet checkpoint validation failed.", 409)
        candidates = self._build_literature_fragment_cas_review_candidates(projection_result)
        recommended, sensitivity = self._recommend_literature_fragment_cas_candidates(candidates)
        triplet_candidates = [
            candidate.candidate_id
            for candidate in self.repository.list_electronic_structure_candidates(quantum_region_id, owner_user_id)
            if candidate.spin_multiplicity == 3
        ]
        report = {
            "report_type": "literature_fragment_cas_candidate_review",
            "status": "completed_pending_independent_review",
            "model_label": LITERATURE_FRAGMENT_MODEL_LABEL,
            "quantum_region_id": quantum_region_id,
            "source_candidate_id": fragment["source_candidate_id"],
            "source_index_space": fragment["source_index_space"],
            "fragment_sha256": fragment["fragment_sha256"],
            "confirmed_for_algorithm_benchmark": True,
            "ground_state_assessed": False,
            "scientific_adsorption_validation": False,
            "independent_cas_review_required": True,
            "reference_input": {
                "singlet_candidate_id": singlet_candidate.candidate_id,
                "scf_method": singlet_candidate.scf_method,
                "basis_set": singlet_candidate.basis_set,
                "total_charge": singlet_candidate.total_charge,
                "spin_multiplicity": singlet_candidate.spin_multiplicity,
                "checkpoint_path_role": "read_only_source",
                "checkpoint_sha256": checkpoint_sha256,
                "expected_checkpoint_metadata": expected_checkpoint_metadata,
                "checkpoint_validation": projection_result["checkpoint_validation"],
            },
            "triplet_handling": {
                "candidate_ids": triplet_candidates,
                "status": "not_converged_not_used_for_energy_comparison",
            },
            "orbital_analysis": projection_result,
            "cas_candidates": candidates,
            "recommendation_policy": {
                "defined_before_any_quantum_execution": True,
                "selection_rule": "Among the two CAS(4,4) candidates, prefer larger mean S-p Lowdin projection across included orbitals; break ties in favor of the contiguous-energy candidate.",
                "vqe_results_consulted": False,
            },
            "recommended_primary_candidate": recommended,
            "recommended_sensitivity_candidate": sensitivity,
            "review_scope": "This Artifact proposes no active space and creates no ActiveSpaceRecord, Hamiltonian, FCI, Pauli mapping, or VQE execution.",
            "cas_hamiltonian_fci_pauli_vqe_created": False,
        }
        report_path = self._write_json_artifact(self._new_id("literature_fragment_cas_review"), report)
        warnings = list(region.warnings or [])
        warnings.append("CAS candidate report is ready for independent review; no active space or quantum closure artifact was created.")
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
            warnings=warnings,
        )
        return {**report, "cas_review_artifact_id": report_path.stem}

    def _get_literature_fragment_singlet_reference(self, quantum_region_id: str, owner_user_id: int):
        """Locate the only converged singlet result eligible as a benchmark input, not a ground-state claim."""
        matching: list[tuple[object, dict]] = []
        for candidate in self.repository.list_electronic_structure_candidates(quantum_region_id, owner_user_id):
            if candidate.spin_multiplicity != 1 or not candidate.converged or candidate.total_charge != 0:
                continue
            if str(candidate.basis_set).lower() != "def2-svp" or not candidate.result_artifact_path:
                continue
            result = self._read_json_artifact(candidate.result_artifact_path)
            if (
                result.get("status") in {None, "completed"}
                and result.get("hf_total_energy_hartree") is not None
                and result.get("model_label") == LITERATURE_FRAGMENT_MODEL_LABEL
                and result.get("scientific_adsorption_validation") is False
            ):
                matching.append((candidate, result))
        if len(matching) != 1:
            raise StructureModelingError(
                "literature_fragment_singlet_reference_ambiguous",
                "Exactly one converged neutral def2-SVP Li2S4 singlet result is required for CAS review.",
                409,
            )
        return matching[0]

    @staticmethod
    def _find_checkpoint_by_sha256(expected_sha256: str) -> Path:
        """Resolve a retained checkpoint by content hash rather than relying on a transient container path."""
        checkpoint_root = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints"
        for checkpoint_path in checkpoint_root.glob("*/scf.chk"):
            if checkpoint_path.is_file() and StructureModelingService._file_sha256(checkpoint_path) == expected_sha256:
                return checkpoint_path
        raise StructureModelingError("literature_fragment_checkpoint_missing", "Audited singlet checkpoint was not retained on disk.", 409)

    @staticmethod
    def _structure_basis_sha256(structure_sha256: str, basis_set: str) -> str:
        """Match the adapter's checkpoint structure-and-basis fingerprint."""
        payload = {"structure_sha256": structure_sha256, "basis_set": basis_set.strip().lower()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _build_literature_fragment_cas_review_candidates(self, projection_result: dict) -> list[dict]:
        """Audit fixed user-approved CAS candidates without persisting a formal active-space choice."""
        spatial_orbitals = {item["orbital_index"]: item for item in projection_result["spatial_orbitals"]}
        candidate_definitions = [
            {
                "candidate_label": "cas_2_2_homo_lumo",
                "cas": [2, 2],
                "orbital_indices": [34, 35],
                "inclusion_reason": "Minimal HOMO/LUMO comparison space; includes occupied S-p frontier orbital 34 and the first virtual orbital 35.",
                "exclusion_reason": "Excludes adjacent occupied and virtual frontier orbitals to preserve a deliberately minimal sensitivity baseline.",
            },
            {
                "candidate_label": "cas_4_4_contiguous_energy",
                "cas": [4, 4],
                "orbital_indices": [33, 34, 35, 36],
                "inclusion_reason": "Continuous energy-window alternative spanning two occupied and two immediately following virtual orbitals.",
                "exclusion_reason": "Excludes orbital 37 because this option tests energy continuity rather than chemical projection selection.",
            },
            {
                "candidate_label": "cas_4_4_chemical_projection",
                "cas": [4, 4],
                "orbital_indices": [33, 34, 35, 37],
                "inclusion_reason": "Retains S-p projected occupied frontier orbitals and substitutes S-p projected virtual orbital 37 for the more Li-s-like orbital 36.",
                "exclusion_reason": "Excludes orbital 36 specifically as a chemical-projection sensitivity choice, not because its energy is invalid.",
            },
        ]
        candidates: list[dict] = []
        for definition in candidate_definitions:
            orbital_indices = definition["orbital_indices"]
            orbitals = [spatial_orbitals[index] for index in orbital_indices]
            active_electron_float = sum(orbital["occupation"] for orbital in orbitals)
            active_electrons = int(round(active_electron_float))
            active_orbitals = len(orbital_indices)
            valid_electron_count = abs(active_electron_float - active_electrons) < 1e-6 and 0 <= active_electrons <= 2 * active_orbitals
            fci_dimension = self._estimate_fci_determinant_dimension(active_electrons, active_orbitals, 1)
            s_p_projection = self._mean_element_angular_momentum_projection(
                projection_result,
                orbital_indices,
                "S",
                "p",
            )
            li_s_projection = self._mean_element_angular_momentum_projection(
                projection_result,
                orbital_indices,
                "Li",
                "s",
            )
            candidates.append(
                {
                    **definition,
                    "active_electrons": active_electrons,
                    "active_electron_count_valid": valid_electron_count,
                    "active_spatial_orbitals": active_orbitals,
                    "mapping_pre_qubit_count": 2 * active_orbitals,
                    "fci_determinant_dimension": fci_dimension,
                    "resource_guardrails": {
                        "mapping_pre_qubits_within_limit": 2 * active_orbitals <= QUANTUM_CLOSURE_MAX_QUBITS,
                        "fci_dimension_within_limit": fci_dimension <= QUANTUM_CLOSURE_MAX_FCI_DETERMINANTS,
                    },
                    "orbitals": orbitals,
                    "mean_s_p_lowdin_projection": s_p_projection,
                    "mean_li_s_lowdin_projection": li_s_projection,
                    "selection_evidence": "Lowdin AO projections from the validated singlet checkpoint only; no Hamiltonian or VQE data were consulted.",
                }
            )
        return candidates

    @staticmethod
    def _mean_element_angular_momentum_projection(
        projection_result: dict,
        orbital_indices: list[int],
        element: str,
        angular_momentum: str,
    ) -> float:
        """Average spin-channel Lowdin weight over a fixed orbital set for a predeclared CAS rule."""
        channel_weights: list[float] = []
        for projections in projection_result["spin_channel_projections"].values():
            by_index = {entry["orbital_index"]: entry for entry in projections}
            for orbital_index in orbital_indices:
                contributions = by_index[orbital_index]["projection_by_element_angular_momentum"]
                channel_weights.append(
                    next(
                        (
                            item["weight"]
                            for item in contributions
                            if item["element"] == element and item["angular_momentum"] == angular_momentum
                        ),
                        0.0,
                    )
                )
        return float(sum(channel_weights) / len(channel_weights)) if channel_weights else 0.0

    @staticmethod
    def _recommend_literature_fragment_cas_candidates(candidates: list[dict]) -> tuple[dict, dict]:
        """Select predeclared CAS(4,4) primary/sensitivity entries solely from projection evidence."""
        four_orbital_candidates = [candidate for candidate in candidates if candidate["cas"] == [4, 4]]
        ordered = sorted(
            four_orbital_candidates,
            key=lambda candidate: (
                -candidate["mean_s_p_lowdin_projection"],
                candidate["candidate_label"] != "cas_4_4_contiguous_energy",
            ),
        )
        return ordered[0], ordered[1]

    @staticmethod
    def _extract_literature_fragment_source_sites(source_payload: dict) -> list[dict]:
        sites_by_index = {site["index"]: site for site in source_payload.get("atomic_sites", [])}
        if source_payload.get("source_candidate_id") != LITERATURE_FRAGMENT_SOURCE_CANDIDATE_ID:
            raise StructureModelingError("literature_fragment_source_mismatch", "Source artifact is not candidate 8637.", 409)
        try:
            sites = [sites_by_index[index] for index in LITERATURE_FRAGMENT_SOURCE_INDICES]
        except KeyError as exc:
            raise StructureModelingError("literature_fragment_index_missing", "Candidate 8637 is missing a required Li2S4 atom.", 409) from exc
        elements = tuple(site["element"] for site in sites)
        if elements != LITERATURE_FRAGMENT_ELEMENTS:
            raise StructureModelingError("literature_fragment_element_mismatch", "Candidate 8637 Li2S4 element sequence does not match.", 409)
        return [
            {
                "index": site["index"],
                "element": site["element"],
                "position_angstrom": [float(value) for value in site["position_angstrom"]],
            }
            for site in sites
        ]

    @staticmethod
    def _validate_fragment_spin_parity(neutral_electron_count: int, total_charge: int, multiplicity: int) -> None:
        electron_count = neutral_electron_count - total_charge
        if electron_count % 2 != (multiplicity - 1) % 2:
            raise StructureModelingError("literature_fragment_spin_parity_invalid", "Electron count and multiplicity parity are inconsistent.", 422)

    def _reordered_local_geometry_mapping(self, parent_geometry_path: str, source_sites: list[dict]) -> list[dict]:
        parent_payload = self._read_json_artifact(parent_geometry_path)
        parent_sites = {site["index"]: site for site in parent_payload.get("atomic_sites", [])}
        mapping = []
        for offset, source_site in enumerate(source_sites):
            reduced_index = 71 + offset
            reduced_site = parent_sites.get(reduced_index)
            if reduced_site is None or reduced_site.get("element") != source_site["element"]:
                raise StructureModelingError("reordered_fragment_mapping_invalid", "Reduced geometry Li2S4 mapping is unavailable.", 409)
            if not np.allclose(reduced_site["position_angstrom"], source_site["position_angstrom"], atol=1e-8, rtol=0.0):
                raise StructureModelingError("reordered_fragment_coordinate_mismatch", "Reduced mapping coordinates differ from candidate 8637.", 409)
            mapping.append(
                {
                    "source_original_index": source_site["index"],
                    "reordered_local_geometry_index": reduced_index,
                    "element": source_site["element"],
                    "coordinates_match": True,
                }
            )
        return mapping

    @staticmethod
    def _literature_fragment_scf_options() -> dict:
        return {
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "df_cderi_path": "/checkpoints/df_cderi.h5",
            "checkpoint_path": "/checkpoints/scf.chk",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_memory_mb": LITERATURE_FRAGMENT_SCF_PYSCF_MEMORY_MB,
            "max_cycle": 100,
            "diis_space": 12,
            "conv_tol": 1e-8,
            "conv_tol_grad": 1e-5,
            "strategies": [
                {"level_shift": 0.2, "initial_guess": "atom", "damping": 0.1, "use_newton": False},
            ],
        }

    def run_reduced_local_neutral_triplet_preflight(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        timeout_seconds: int = REDUCED_LOCAL_SCF_TIMEOUT_SECONDS,
        restart_checkpoint_directory: str | Path | None = None,
        expected_restart_checkpoint_sha256: str | None = None,
    ) -> dict:
        """Run exactly one resource-gated neutral-triplet SCF calculation for the reduced algorithm benchmark."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_reduced_local_algorithm_benchmark":
            raise StructureModelingError("reduced_local_model_not_found", "未找到缩减局部算法基准模型。", 404)
        self._assert_reduced_local_compute_not_exhausted(region)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        if cluster.get("model_label") != REDUCED_LOCAL_MODEL_LABEL:
            raise StructureModelingError("reduced_local_model_label_invalid", "缩减模型标签不匹配，已拒绝执行。", 409)
        restart_checkpoint_path = (
            Path(restart_checkpoint_directory) / "scf.chk" if restart_checkpoint_directory is not None else None
        )
        if restart_checkpoint_path is None or not restart_checkpoint_path.is_file():
            raise StructureModelingError("restart_checkpoint_missing", "未找到获批的标定 checkpoint，已拒绝启动完整 SCF。", 409)
        restart_checkpoint_sha256 = hashlib.sha256(restart_checkpoint_path.read_bytes()).hexdigest()
        if expected_restart_checkpoint_sha256 and restart_checkpoint_sha256 != expected_restart_checkpoint_sha256:
            raise StructureModelingError("restart_checkpoint_hash_mismatch", "标定 checkpoint SHA-256 不匹配，已拒绝启动。", 409)
        resource_diagnostic = self._reduced_local_resource_diagnostic(
            cpu_count=REDUCED_LOCAL_FULL_SCF_CPU_COUNT,
            container_memory_mb=REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
            pyscf_memory_mb=REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            host_memory_threshold_bytes=REDUCED_LOCAL_FULL_SCF_HOST_MEMORY_THRESHOLD_BYTES,
            minimum_disk_free_bytes=REDUCED_LOCAL_FULL_SCF_MIN_DISK_FREE_BYTES,
        )
        if not resource_diagnostic["eligible"]:
            report = {
                "report_type": "reduced_local_algorithm_benchmark_scf_preflight",
                "model_label": REDUCED_LOCAL_MODEL_LABEL,
                "quantum_region_id": quantum_region_id,
                "scf_executed": False,
                "status": "blocked_by_resource_guardrail",
                "resource_diagnostic": resource_diagnostic,
                "restart_checkpoint_sha256": restart_checkpoint_sha256,
                "conclusion": "资源护栏未满足，未启动 SCF；这不构成对化学模型的否定。",
                "cas_hamiltonian_fci_pauli_vqe_created": False,
            }
            report_path = self._write_json_artifact(self._new_id("reduced_scf_resource"), report)
            self.repository.update_quantum_region(
                quantum_region_id, owner_user_id, preflight_artifact_path=str(report_path), status="needs_model_review"
            )
            return {**report, "preflight_artifact_id": report_path.stem}
        checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / self._new_id("reduced_triplet")
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(restart_checkpoint_path, checkpoint_directory / "scf.chk")
        scf_options = self._reduced_local_scf_options()
        scan = self._generate_electronic_structure_candidates(
            quantum_region_id,
            owner_user_id,
            {
                "charge_candidates": [0],
                "spin_strategy": "explicit",
                "spin_multiplicities": [3],
                "requested_methods": ["UHF"],
                "basis_set": "def2-svp",
                "max_scf_attempts": 1,
                "spin_contamination_threshold": 0.5,
                "benchmark_case_id": None,
                "include_active_space_candidates": False,
                "scf_options": scf_options,
            },
            timeout_seconds=timeout_seconds,
            stop_after_resource_timeout=True,
            execution_options={
                "cpu_count": REDUCED_LOCAL_FULL_SCF_CPU_COUNT,
                "memory_limit_mb": REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
                "checkpoint_directory": str(checkpoint_directory),
                "monitor_resources": True,
                "terminate_at_memory_bytes": int(
                    REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB
                    * 1024
                    * 1024
                    * REDUCED_LOCAL_FULL_SCF_PEAK_STOP_RATIO
                ),
            },
        )
        measurement = self._reduced_calibration_measurement(scan)
        report = {
            "report_type": "reduced_local_algorithm_benchmark_scf_preflight",
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "quantum_region_id": quantum_region_id,
            "scf_executed": True,
            "charge": 0,
            "spin_multiplicity": 3,
            "timeout_seconds": timeout_seconds,
            "resource_diagnostic": resource_diagnostic,
            "scf_options": scf_options,
            "checkpoint_directory": str(checkpoint_directory),
            "restart_checkpoint_source": str(restart_checkpoint_path),
            "restart_checkpoint_sha256": restart_checkpoint_sha256,
            "final_checkpoint_sha256": measurement.get("checkpoint_sha256") if measurement else None,
            "measurement": measurement,
            "scan": scan,
            "cas_hamiltonian_fci_pauli_vqe_created": False,
            "conclusion": "仅执行一次中性三重态 SCF；该模型只用于局部算法基准，不代表文献体系复现。",
        }
        report_path = self._write_json_artifact(self._new_id("reduced_scf_preflight"), report)
        self.repository.update_quantum_region(
            quantum_region_id, owner_user_id, preflight_artifact_path=str(report_path), status="needs_model_review"
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def run_reduced_local_newton_rescue(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        *,
        restart_checkpoint_directory: str | Path,
        expected_restart_checkpoint_sha256: str,
        timeout_seconds: int = REDUCED_LOCAL_SCF_TIMEOUT_SECONDS,
    ) -> dict:
        """Run one independently guarded Newton/AH rescue for the frozen reduced model."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_reduced_local_algorithm_benchmark":
            raise StructureModelingError("reduced_local_model_not_found", "未找到缩减局部算法基准模型。", 404)
        self._assert_reduced_local_compute_not_exhausted(region)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        if cluster.get("model_label") != REDUCED_LOCAL_MODEL_LABEL:
            raise StructureModelingError("reduced_local_model_label_invalid", "缩减模型标签不匹配，已拒绝执行。", 409)
        restart_directory = Path(restart_checkpoint_directory)
        restart_checkpoint_path = restart_directory / "scf.chk"
        if not restart_checkpoint_path.is_file():
            raise StructureModelingError("restart_checkpoint_missing", "未找到 Newton/AH 救援 checkpoint。", 409)
        restart_checkpoint_sha256 = self._file_sha256(restart_checkpoint_path)
        if restart_checkpoint_sha256 != expected_restart_checkpoint_sha256:
            raise StructureModelingError("restart_checkpoint_hash_mismatch", "Newton/AH checkpoint SHA-256 不匹配。", 409)

        structure_sha256 = cluster["structure_sha256"]
        basis_set = "def2-svp"
        structure_basis_sha256 = hashlib.sha256(
            json.dumps(
                {"structure_sha256": structure_sha256, "basis_set": basis_set},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        source_cderi_path = restart_directory / "df_cderi.h5"
        source_cderi_sha256 = self._file_sha256(source_cderi_path) if source_cderi_path.is_file() else None
        resource_diagnostic = self._reduced_local_resource_diagnostic(
            cpu_count=REDUCED_LOCAL_FULL_SCF_CPU_COUNT,
            container_memory_mb=REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
            pyscf_memory_mb=REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            host_memory_threshold_bytes=REDUCED_LOCAL_FULL_SCF_HOST_MEMORY_THRESHOLD_BYTES,
            minimum_disk_free_bytes=REDUCED_LOCAL_FULL_SCF_MIN_DISK_FREE_BYTES,
        )
        cderi_provenance = {
            "decision": "regenerate_missing_structure_basis_provenance",
            "source_cderi_path": str(source_cderi_path) if source_cderi_path.is_file() else None,
            "source_cderi_sha256": source_cderi_sha256,
            "structure_basis_sha256": structure_basis_sha256,
            "read_only_reuse": False,
        }
        if not resource_diagnostic["eligible"]:
            report = {
                "report_type": "reduced_local_algorithm_newton_rescue",
                "model_label": REDUCED_LOCAL_MODEL_LABEL,
                "quantum_region_id": quantum_region_id,
                "status": "blocked_by_resource_guardrail",
                "scf_executed": False,
                "resource_diagnostic": resource_diagnostic,
                "restart_checkpoint_sha256": restart_checkpoint_sha256,
                "cderi_provenance": cderi_provenance,
                "cas_hamiltonian_fci_pauli_vqe_created": False,
            }
            report_path = self._write_json_artifact(self._new_id("reduced_newton_rescue"), report)
            return {**report, "preflight_artifact_id": report_path.stem}

        checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / self._new_id("reduced_newton_rescue")
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(restart_checkpoint_path, checkpoint_directory / "scf.chk")
        scf_options = self._reduced_local_newton_rescue_options()
        expected_checkpoint_metadata = {
            "checkpoint_sha256": restart_checkpoint_sha256,
            "structure_sha256": structure_sha256,
            "basis_set": basis_set,
            "total_charge": 0,
            "spin_multiplicity": 3,
            "structure_basis_sha256": structure_basis_sha256,
        }
        scan = self._generate_electronic_structure_candidates(
            quantum_region_id,
            owner_user_id,
            {
                "charge_candidates": [0],
                "spin_strategy": "explicit",
                "spin_multiplicities": [3],
                "requested_methods": ["UHF"],
                "basis_set": basis_set,
                "max_scf_attempts": 1,
                "spin_contamination_threshold": 0.5,
                "benchmark_case_id": None,
                "include_active_space_candidates": False,
                "expected_checkpoint_metadata": expected_checkpoint_metadata,
                "scf_options": scf_options,
            },
            timeout_seconds=timeout_seconds,
            stop_after_resource_timeout=True,
            execution_options={
                "cpu_count": REDUCED_LOCAL_FULL_SCF_CPU_COUNT,
                "memory_limit_mb": REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
                "checkpoint_directory": str(checkpoint_directory),
                "monitor_resources": True,
                "terminate_at_memory_bytes": int(
                    REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB
                    * 1024
                    * 1024
                    * REDUCED_LOCAL_FULL_SCF_PEAK_STOP_RATIO
                ),
            },
        )
        measurement = self._reduced_calibration_measurement(scan)
        candidates = scan.get("candidates") or []
        is_converged = bool(candidates and candidates[0].get("converged"))
        report = {
            "report_type": "reduced_local_algorithm_newton_rescue",
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "quantum_region_id": quantum_region_id,
            "status": "converged_pending_independent_review" if is_converged else "needs_model_review",
            "scf_executed": True,
            "scf_converged": is_converged,
            "charge": 0,
            "spin_multiplicity": 3,
            "basis_set": basis_set,
            "timeout_seconds": timeout_seconds,
            "structure_sha256": structure_sha256,
            "structure_basis_sha256": structure_basis_sha256,
            "resource_diagnostic": resource_diagnostic,
            "scf_options": scf_options,
            "checkpoint_directory": str(checkpoint_directory),
            "restart_checkpoint_source": str(restart_checkpoint_path),
            "restart_checkpoint_sha256": restart_checkpoint_sha256,
            "final_checkpoint_sha256": measurement.get("checkpoint_sha256") if measurement else None,
            "checkpoint_validation": measurement.get("checkpoint_validation") if measurement else None,
            "cderi_provenance": {
                **cderi_provenance,
                "generated_cderi_sha256": measurement.get("df_cderi_sha256") if measurement else None,
            },
            "measurement": measurement,
            "scan": scan,
            "other_spin_states_started": False,
            "cas_hamiltonian_fci_pauli_vqe_created": False,
            "scientific_qualification": (
                "仅供冻结 reduced_local_algorithm_benchmark 局部模型独立评审；不代表 47 原子参考模型或论文体系验证。"
            ),
        }
        report_path = self._write_json_artifact(self._new_id("reduced_newton_rescue"), report)
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def run_reduced_local_uks_preconditioner(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        *,
        source_checkpoint_directory: str | Path,
        expected_source_checkpoint_sha256: str,
        cderi_path: str | Path,
        expected_cderi_sha256: str,
        cderi_provenance_artifact_id: str,
        timeout_seconds: int = REDUCED_LOCAL_SCF_TIMEOUT_SECONDS,
    ) -> dict:
        """Run UKS/PBE strictly as a non-consumable alpha/beta density preconditioner."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_reduced_local_algorithm_benchmark":
            raise StructureModelingError("reduced_local_model_not_found", "未找到缩减局部算法基准模型。", 404)
        self._assert_reduced_local_compute_not_exhausted(region)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        if cluster.get("model_label") != REDUCED_LOCAL_MODEL_LABEL:
            raise StructureModelingError("reduced_local_model_label_invalid", "缩减模型标签不匹配，已拒绝执行。", 409)

        source_directory = Path(source_checkpoint_directory)
        source_checkpoint_path = source_directory / "scf.chk"
        if not source_checkpoint_path.is_file():
            raise StructureModelingError("preconditioner_checkpoint_missing", "未找到 UKS 初始密度 checkpoint。", 409)
        source_checkpoint_sha256 = self._file_sha256(source_checkpoint_path)
        if source_checkpoint_sha256 != expected_source_checkpoint_sha256:
            raise StructureModelingError("preconditioner_checkpoint_hash_mismatch", "UKS 初始 checkpoint SHA-256 不匹配。", 409)

        basis_set = "def2-svp"
        structure_sha256 = cluster["structure_sha256"]
        structure_basis_sha256 = hashlib.sha256(
            json.dumps(
                {"structure_sha256": structure_sha256, "basis_set": basis_set},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        cderi_source_path = Path(cderi_path)
        if not cderi_source_path.is_file() or self._file_sha256(cderi_source_path) != expected_cderi_sha256:
            raise StructureModelingError("preconditioner_cderi_hash_mismatch", "UKS 只读 CDERI 缺失或 SHA-256 不匹配。", 409)
        provenance_path = STRUCTURE_ARTIFACT_ROOT / f"{cderi_provenance_artifact_id}.json"
        provenance = self._read_json_artifact(provenance_path)
        provenance_cderi = provenance.get("cderi_provenance") or {}
        if (
            provenance.get("structure_basis_sha256") != structure_basis_sha256
            or provenance_cderi.get("generated_cderi_sha256") != expected_cderi_sha256
        ):
            raise StructureModelingError(
                "preconditioner_cderi_provenance_mismatch",
                "CDERI provenance 未能证明与当前冻结结构和基组完全一致。",
                409,
            )

        resource_diagnostic = self._reduced_local_resource_diagnostic(
            cpu_count=REDUCED_LOCAL_UKS_CPU_COUNT,
            container_memory_mb=REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
            pyscf_memory_mb=REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            host_memory_threshold_bytes=REDUCED_LOCAL_FULL_SCF_HOST_MEMORY_THRESHOLD_BYTES,
            minimum_disk_free_bytes=REDUCED_LOCAL_FULL_SCF_MIN_DISK_FREE_BYTES,
        )
        if not resource_diagnostic["eligible"]:
            report = {
                "report_type": "reduced_local_uks_density_preconditioner",
                "model_label": REDUCED_LOCAL_MODEL_LABEL,
                "quantum_region_id": quantum_region_id,
                "preconditioner_only": True,
                "downstream_consumable": False,
                "status": "blocked_by_resource_guardrail",
                "scf_executed": False,
                "resource_diagnostic": resource_diagnostic,
                "source_checkpoint_sha256": source_checkpoint_sha256,
                "cas_hamiltonian_fci_pauli_vqe_created": False,
            }
            report_path = self._write_json_artifact(self._new_id("reduced_uks_preconditioner"), report)
            return {**report, "preflight_artifact_id": report_path.stem}

        checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / self._new_id("reduced_uks_preconditioner")
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_checkpoint_path, checkpoint_directory / "source_uhf.chk")
        scf_options = self._reduced_local_uks_preconditioner_options()
        expected_checkpoint_metadata = {
            "checkpoint_sha256": source_checkpoint_sha256,
            "structure_sha256": structure_sha256,
            "basis_set": basis_set,
            "total_charge": 0,
            "spin_multiplicity": 3,
            "structure_basis_sha256": structure_basis_sha256,
        }
        request = {
            "atomic_sites": cluster["atomic_sites"],
            "total_charge": 0,
            "spin_multiplicity": 3,
            "basis_set": basis_set,
            "expected_checkpoint_metadata": expected_checkpoint_metadata,
            "scf_options": scf_options,
        }
        execution_options = {
            "cpu_count": REDUCED_LOCAL_UKS_CPU_COUNT,
            "memory_limit_mb": REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB,
            "checkpoint_directory": str(checkpoint_directory),
            "monitor_resources": True,
            "terminate_at_memory_bytes": int(
                REDUCED_LOCAL_FULL_SCF_CONTAINER_MEMORY_MB
                * 1024
                * 1024
                * REDUCED_LOCAL_FULL_SCF_PEAK_STOP_RATIO
            ),
            "read_only_mounts": [{"source": str(cderi_source_path), "target": "/inputs/df_cderi.h5"}],
        }
        try:
            result = self.electronic_structure_adapter.run_density_preconditioner(
                request,
                timeout_seconds=timeout_seconds,
                execution_options=execution_options,
            )
        except ElectronicStructureRuntimeError as exc:
            result = {
                "status": "timed_out_or_runtime_failed",
                "preconditioner_only": True,
                "downstream_consumable": False,
                "scientific_validation": False,
                "message": f"UKS preconditioner 运行失败：{exc}",
                "diagnostic": exc.diagnostic,
            }
        result_artifact_path = self._write_json_artifact(self._new_id("uks_preconditioner_result"), result)
        measurement = self._uks_preconditioner_measurement(result, result_artifact_path)
        is_converged = result.get("status") == "uks_preconditioner_converged_pending_review" and result.get("converged") is True
        report = {
            "report_type": "reduced_local_uks_density_preconditioner",
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "quantum_region_id": quantum_region_id,
            "preconditioner_only": True,
            "downstream_consumable": False,
            "scientific_validation": False,
            "status": "converged_pending_independent_approval" if is_converged else "needs_model_review",
            "scf_executed": True,
            "uks_converged": is_converged,
            "charge": 0,
            "spin_multiplicity": 3,
            "basis_set": basis_set,
            "xc": "PBE",
            "structure_sha256": structure_sha256,
            "structure_basis_sha256": structure_basis_sha256,
            "source_checkpoint_path": str(source_checkpoint_path),
            "source_checkpoint_sha256": source_checkpoint_sha256,
            "checkpoint_directory": str(checkpoint_directory),
            "cderi_provenance": {
                "access": "read_only_reuse",
                "path": str(cderi_source_path),
                "sha256": expected_cderi_sha256,
                "provenance_artifact_id": cderi_provenance_artifact_id,
                "structure_basis_sha256": structure_basis_sha256,
            },
            "resource_diagnostic": resource_diagnostic,
            "scf_options": scf_options,
            "measurement": measurement,
            "result_artifact_id": result_artifact_path.stem,
            "local_scf_route_status": (
                "awaiting_independent_density_approval" if is_converged else "closed_after_preconditioner_failure"
            ),
            "electronic_structure_candidate_created": False,
            "other_spin_states_started": False,
            "cas_hamiltonian_fci_pauli_vqe_created": False,
            "scientific_qualification": (
                "UKS/PBE 仅用于生成冻结局部模型的 alpha/beta 初始密度；不得作为最终 HF、FCI 或论文复现结果。"
            ),
        }
        report_path = self._write_json_artifact(self._new_id("reduced_uks_preconditioner"), report)
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def run_reduced_local_memory_calibration(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        timeout_seconds: int = REDUCED_LOCAL_CALIBRATION_TIMEOUT_SECONDS,
    ) -> dict:
        """Run one UHF+DF iteration solely to measure local resource demand."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_reduced_local_algorithm_benchmark":
            raise StructureModelingError("reduced_local_model_not_found", "未找到缩减局部算法基准模型。", 404)
        self._assert_reduced_local_compute_not_exhausted(region)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        if cluster.get("model_label") != REDUCED_LOCAL_MODEL_LABEL:
            raise StructureModelingError("reduced_local_model_label_invalid", "缩减模型标签不匹配，已拒绝执行。", 409)
        resource_diagnostic = self._reduced_local_resource_diagnostic(
            cpu_count=REDUCED_LOCAL_CALIBRATION_CPU_COUNT,
            container_memory_mb=REDUCED_LOCAL_CALIBRATION_CONTAINER_MEMORY_MB,
            pyscf_memory_mb=REDUCED_LOCAL_CALIBRATION_PYSCF_MEMORY_MB,
            host_memory_threshold_bytes=REDUCED_LOCAL_CALIBRATION_HOST_MEMORY_THRESHOLD_BYTES,
            host_memory_reserve_bytes=REDUCED_LOCAL_CALIBRATION_HOST_MEMORY_RESERVE_BYTES,
            minimum_disk_free_bytes=REDUCED_LOCAL_CALIBRATION_MIN_DISK_FREE_BYTES,
        )
        if not resource_diagnostic["eligible"]:
            return self._write_reduced_calibration_report(
                region,
                resource_diagnostic,
                scf_executed=False,
                status="blocked_by_resource_guardrail",
                measurement=None,
                scan=None,
                checkpoint_directory=None,
            )
        checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / self._new_id("reduced_memory_calibration")
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        scf_options = self._reduced_local_memory_calibration_options()
        scan = self._generate_electronic_structure_candidates(
            quantum_region_id,
            owner_user_id,
            {
                "charge_candidates": [0],
                "spin_strategy": "explicit",
                "spin_multiplicities": [3],
                "requested_methods": ["UHF"],
                "basis_set": "def2-svp",
                "max_scf_attempts": 1,
                "spin_contamination_threshold": 0.5,
                "benchmark_case_id": None,
                "include_active_space_candidates": False,
                "resource_calibration_only": True,
                "scf_options": scf_options,
            },
            timeout_seconds=timeout_seconds,
            stop_after_resource_timeout=True,
            execution_options={
                "cpu_count": REDUCED_LOCAL_CALIBRATION_CPU_COUNT,
                "memory_limit_mb": REDUCED_LOCAL_CALIBRATION_CONTAINER_MEMORY_MB,
                "checkpoint_directory": str(checkpoint_directory),
                "monitor_resources": True,
                "terminate_at_memory_bytes": int(
                    REDUCED_LOCAL_CALIBRATION_CONTAINER_MEMORY_MB
                    * 1024
                    * 1024
                    * REDUCED_LOCAL_CALIBRATION_PEAK_STOP_RATIO
                ),
            },
        )
        measurement = self._reduced_calibration_measurement(scan)
        status = "completed" if self._reduced_calibration_passed(measurement) else "needs_model_review"
        return self._write_reduced_calibration_report(
            region,
            resource_diagnostic,
            scf_executed=True,
            status=status,
            measurement=measurement,
            scan=scan,
            checkpoint_directory=checkpoint_directory,
        )

    def _write_reduced_calibration_report(
        self,
        region,
        resource_diagnostic: dict,
        *,
        scf_executed: bool,
        status: str,
        measurement: dict | None,
        scan: dict | None,
        checkpoint_directory: Path | None,
    ) -> dict:
        report = {
            "report_type": "reduced_local_algorithm_memory_calibration",
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "quantum_region_id": region.quantum_region_id,
            "purpose": "Resource calibration only; not a full SCF or literature-system reproduction.",
            "scf_executed": scf_executed,
            "status": status,
            "resource_diagnostic": resource_diagnostic,
            "calibration_configuration": self._reduced_local_memory_calibration_options(),
            "checkpoint_directory": str(checkpoint_directory) if checkpoint_directory else None,
            "measurement": measurement,
            "scan": scan,
            "cas_hamiltonian_fci_pauli_vqe_created": False,
            "next_step": (
                "Submit a resource report for a separate 900-second neutral-triplet SCF; do not start it automatically."
                if status == "completed"
                else "Stop after this calibration diagnostic; do not queue a complete SCF or another spin state."
            ),
        }
        report_path = self._write_json_artifact(self._new_id("reduced_memory_calibration"), report)
        self.repository.update_quantum_region(
            region.quantum_region_id,
            region.owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def _reduced_calibration_measurement(self, scan: dict) -> dict | None:
        candidates = scan.get("candidates") or []
        if not candidates:
            return None
        artifact_id = candidates[0].get("result_artifact_id")
        if not artifact_id:
            return None
        payload = self._read_json_artifact(STRUCTURE_ARTIFACT_ROOT / f"{artifact_id}.json")
        attempts = payload.get("scf_attempts", [])
        diagnostic = payload.get("diagnostic", {})
        progress_events = diagnostic.get("scf_iteration_log", [])
        iteration_started = any(attempt.get("iterations") for attempt in attempts) or any(
            event.get("event") == "iteration" for event in progress_events
        )
        completed_cycles = [
            event.get("cycle") for event in progress_events if event.get("event") == "iteration" and event.get("cycle") is not None
        ]
        monitor = payload.get("execution_metadata", {}).get("container_resource_monitor") or diagnostic.get(
            "container_resource_monitor"
        )
        if candidates[0].get("converged"):
            farthest_scf_stage = "scf_converged"
        elif any(event.get("event") == "scf_kernel_end" for event in progress_events):
            farthest_scf_stage = "scf_kernel_completed"
        elif iteration_started:
            farthest_scf_stage = "first_scf_iteration_completed"
        elif any(event.get("event") == "scf_kernel_start" for event in progress_events):
            farthest_scf_stage = "scf_kernel_started"
        elif (payload.get("df_artifact") or diagnostic).get("df_cderi_available"):
            farthest_scf_stage = "df_integrals_built"
        else:
            farthest_scf_stage = diagnostic.get("failure_stage", "before_scf_kernel")
        execution_metadata = payload.get("execution_metadata", {})
        runtime_metadata = payload.get("runtime_metadata") or {}
        df_artifact = payload.get("df_artifact") or {}
        monitored_process_peak_rss_bytes = monitor.get("monitored_process_peak_rss_bytes") if monitor else None
        process_peak_rss_mb = runtime_metadata.get("process_max_rss_mb")
        process_peak_rss_source = "pyscf_resource_getrusage"
        if process_peak_rss_mb is None and monitored_process_peak_rss_bytes is not None:
            process_peak_rss_mb = monitored_process_peak_rss_bytes / (1024 * 1024)
            process_peak_rss_source = "sampled_container_proc_pid1_vmhwm"
        return {
            "candidate_id": candidates[0].get("candidate_id"),
            "result_artifact_id": artifact_id,
            "quality_status": candidates[0].get("quality_status"),
            "farthest_scf_stage": farthest_scf_stage,
            "last_completed_scf_cycle": max(completed_cycles) if completed_cycles else None,
            "iteration_started": iteration_started,
            "docker_exit_code": diagnostic.get("docker_exit_code"),
            "oom_suspected": diagnostic.get("oom_suspected", False),
            "container_resource_monitor": monitor,
            "container_peak_memory_bytes": monitor.get("peak_memory_bytes") if monitor else None,
            "peak_sample_timestamp_utc": monitor.get("peak_sample_timestamp_utc") if monitor else None,
            "peak_sample_timestamp_monotonic": monitor.get("peak_sample_timestamp_monotonic") if monitor else None,
            "cgroup_memory_peak_bytes": monitor.get("cgroup_memory_peak_bytes") if monitor else None,
            "cgroup_memory_peak_available": bool(monitor and monitor.get("cgroup_memory_peak_available")),
            "monitored_process_peak_rss_bytes": monitored_process_peak_rss_bytes,
            "threshold_triggered": bool(monitor and monitor.get("terminated_for_memory_limit")),
            "pyscf_process_peak_rss_mb": process_peak_rss_mb,
            "pyscf_process_peak_rss_source": process_peak_rss_source,
            "pyscf_process_peak_rss_sampled_at_utc": runtime_metadata.get("process_max_rss_sampled_at_utc"),
            "pyscf_runtime": runtime_metadata,
            "df_artifact": df_artifact,
            "df_cderi_size_bytes": df_artifact.get("df_cderi_size_bytes") or diagnostic.get("df_cderi_size_bytes"),
            "df_cderi_sha256": execution_metadata.get("df_cderi_sha256") or diagnostic.get("df_cderi_sha256"),
            "checkpoint_size_bytes": execution_metadata.get("checkpoint_size_bytes")
            or diagnostic.get("checkpoint_size_bytes"),
            "checkpoint_sha256": execution_metadata.get("checkpoint_sha256") or diagnostic.get("checkpoint_sha256"),
            "checkpoint_validation": payload.get("checkpoint_validation") or diagnostic.get("checkpoint_validation"),
            "utf8_decoding_succeeded": (execution_metadata.get("output_decoding") or diagnostic.get("output_decoding") or {}).get(
                "succeeded"
            ),
            "scf_attempts": attempts,
            "message": payload.get("message"),
        }

    @staticmethod
    def _uks_preconditioner_measurement(result: dict, result_artifact_path: Path) -> dict:
        diagnostic = result.get("diagnostic") or {}
        execution_metadata = result.get("execution_metadata") or {}
        monitor = execution_metadata.get("container_resource_monitor") or diagnostic.get("container_resource_monitor") or {}
        cycles = result.get("cycles") or [
            event
            for event in diagnostic.get("scf_iteration_log", [])
            if event.get("iteration_kind") == "uks_preconditioner_cycle"
        ]
        stop_code = result.get("stop_code")
        if not stop_code and result.get("status") == "timed_out_or_runtime_failed":
            stop_code = "stopped_for_timeout_or_runtime_failure"
        return {
            "result_artifact_id": result_artifact_path.stem,
            "status": result.get("status"),
            "stop_code": stop_code,
            "converged": bool(result.get("converged")),
            "completed_cycle_count": len(cycles),
            "cycles": cycles,
            "last_completed_cycle": cycles[-1].get("cycle") if cycles else None,
            "checkpoint_validation": result.get("checkpoint_validation") or diagnostic.get("checkpoint_validation"),
            "grid_configuration": result.get("grid_configuration"),
            "density_fitting_auxbasis": result.get("density_fitting_auxbasis"),
            "runtime_metadata": result.get("runtime_metadata"),
            "preconditioner_diagnostics": result.get("preconditioner_diagnostics"),
            "container_peak_memory_bytes": monitor.get("peak_memory_bytes"),
            "container_peak_is_sampled": True,
            "peak_sample_timestamp_utc": monitor.get("peak_sample_timestamp_utc"),
            "cgroup_memory_peak_available": bool(monitor.get("cgroup_memory_peak_available")),
            "cgroup_memory_peak_bytes": monitor.get("cgroup_memory_peak_bytes"),
            "process_peak_rss_bytes": monitor.get("monitored_process_peak_rss_bytes"),
            "threshold_triggered": bool(monitor.get("terminated_for_memory_limit")),
            "oom_suspected": bool(diagnostic.get("oom_suspected", False)),
            "checkpoint_sha256": execution_metadata.get("checkpoint_sha256") or diagnostic.get("checkpoint_sha256"),
            "checkpoint_size_bytes": execution_metadata.get("checkpoint_size_bytes") or diagnostic.get("checkpoint_size_bytes"),
            "density_available": bool(
                result.get("density_artifact", {}).get("density_available")
                or diagnostic.get("density_available")
            ),
            "density_sha256": execution_metadata.get("density_sha256") or diagnostic.get("density_sha256"),
            "density_size_bytes": execution_metadata.get("density_size_bytes") or diagnostic.get("density_size_bytes"),
            "utf8_decoding_succeeded": (
                execution_metadata.get("output_decoding") or diagnostic.get("output_decoding") or {}
            ).get("succeeded"),
            "message": result.get("message"),
        }

    @staticmethod
    def _reduced_calibration_passed(measurement: dict | None) -> bool:
        if not measurement or measurement.get("oom_suspected") or not measurement.get("iteration_started"):
            return False
        required_values = (
            measurement.get("container_peak_memory_bytes"),
            measurement.get("pyscf_process_peak_rss_mb"),
            measurement.get("peak_sample_timestamp_utc"),
            measurement.get("df_cderi_size_bytes"),
            measurement.get("checkpoint_size_bytes"),
            measurement.get("farthest_scf_stage"),
            measurement.get("utf8_decoding_succeeded"),
        )
        if any(value is None for value in required_values) or measurement.get("utf8_decoding_succeeded") is not True:
            return False
        monitor = measurement.get("container_resource_monitor") or {}
        if measurement.get("threshold_triggered") or monitor.get("terminated_for_memory_limit"):
            return False
        peak_memory = measurement.get("container_peak_memory_bytes")
        peak_limit = int(
            REDUCED_LOCAL_CALIBRATION_CONTAINER_MEMORY_MB
            * 1024
            * 1024
            * REDUCED_LOCAL_CALIBRATION_PEAK_STOP_RATIO
        )
        if peak_memory >= peak_limit:
            return False
        return measurement["df_cderi_size_bytes"] > 0 and measurement["checkpoint_size_bytes"] > 0

    def run_h_capped_scf_preflight(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        timeout_seconds: int = H_CAPPED_PREFLIGHT_TIMEOUT_SECONDS,
    ) -> dict:
        """Run bounded parity-valid SCF scans and persist a report without confirming any state."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_graph_cut":
            raise StructureModelingError("h_capped_region_not_found", "未找到 H 封端有限簇量子区。", 404)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        electron_count_neutral = sum(atomic_numbers[site["element"]] for site in cluster["atomic_sites"])
        scan_summaries = []
        for charge, multiplicities in self._parity_valid_charge_spin_groups(electron_count_neutral):
            scan = self._generate_electronic_structure_candidates(
                quantum_region_id,
                owner_user_id,
                {
                    "charge_candidates": [charge],
                    "spin_strategy": "explicit",
                    "spin_multiplicities": multiplicities,
                    "requested_methods": ["UHF", "ROHF"],
                    "basis_set": "def2-svp",
                    "max_scf_attempts": 3,
                    "spin_contamination_threshold": 0.5,
                    "benchmark_case_id": None,
                },
                timeout_seconds=timeout_seconds,
                stop_after_resource_timeout=True,
            )
            scan_summaries.append({"charge": charge, "spin_multiplicities": multiplicities, **scan})
            if scan.get("stopped_for_resource_timeout"):
                break
        report = self._build_h_capped_preflight_report(
            region,
            owner_user_id,
            electron_count_neutral,
            timeout_seconds,
            scan_summaries,
        )
        report_path = self._write_json_artifact(self._new_id("hcap_preflight"), report)
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
            warnings=list(region.warnings or []) + ["已完成 H 封端有限簇短时 SCF/CAS 预检；尚未确认电子态或 CAS。"],
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def run_h_capped_neutral_triplet_preflight(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        *,
        timeout_seconds: int = H_CAPPED_SERIAL_PREFLIGHT_TIMEOUT_SECONDS,
        cpu_count: int = H_CAPPED_SERIAL_PREFLIGHT_CPU_COUNT,
        memory_limit_mb: int = H_CAPPED_SERIAL_PREFLIGHT_MEMORY_MB,
    ) -> dict:
        """Run only the auditable neutral-triplet SCF preflight; never create CAS or quantum artifacts."""
        region = self.repository.get_quantum_region(quantum_region_id, owner_user_id)
        if region is None or region.embedding_method != "h_link_atoms_graph_cut":
            raise StructureModelingError("h_capped_region_not_found", "未找到 H 封端有限簇量子区。", 404)
        if region.quantum_region_id != "qr_hcap_5f4cc8a363904c5084f4137b96e3f886":
            raise StructureModelingError("serial_preflight_region_not_allowed", "当前串行预检仅允许已指定的内层 H 封端模型。", 409)
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        neutral_electron_count = sum(atomic_numbers[site["element"]] for site in cluster["atomic_sites"])
        if neutral_electron_count != 270:
            raise StructureModelingError("neutral_electron_count_unexpected", "内层封端模型的中性电子数与预检假设不一致。", 409)
        run_id = self._new_id("scf_neutral_triplet")
        checkpoint_directory = STRUCTURE_ARTIFACT_ROOT / "scf_checkpoints" / run_id
        checkpoint_directory.mkdir(parents=True, exist_ok=True)
        scf_options = {
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "checkpoint_path": "/checkpoints/scf.chk",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_cycle": 300,
            "diis_space": 12,
            "conv_tol": 1e-8,
            "conv_tol_grad": 1e-5,
            "strategies": [
                {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False},
                {"level_shift": 0.5, "initial_guess": "atom", "damping": 0.2, "use_newton": True},
                {"level_shift": 0.0, "initial_guess": "minao", "damping": 0.0, "use_newton": False},
            ],
        }
        scan = self._generate_electronic_structure_candidates(
            quantum_region_id,
            owner_user_id,
            {
                "charge_candidates": [0],
                "spin_strategy": "explicit",
                "spin_multiplicities": [3],
                "requested_methods": ["UHF", "ROHF"],
                "basis_set": "def2-svp",
                "max_scf_attempts": 3,
                "spin_contamination_threshold": 0.5,
                "benchmark_case_id": None,
                "include_active_space_candidates": False,
                "scf_options": scf_options,
            },
            timeout_seconds=timeout_seconds,
            stop_after_resource_timeout=True,
            execution_options={
                "cpu_count": cpu_count,
                "memory_limit_mb": memory_limit_mb,
                "checkpoint_directory": str(checkpoint_directory),
            },
        )
        report = self._build_h_capped_preflight_report(
            region,
            owner_user_id,
            neutral_electron_count,
            timeout_seconds,
            [{"charge": 0, "spin_multiplicities": [3], **scan}],
        )
        report["serial_execution_policy"] = {
            "assumption": "The periodic source model is neutral; neutral finite-cluster charge is a first-round hypothesis only.",
            "requested_charge": 0,
            "requested_multiplicity": 3,
            "next_multiplicities_only_after_valid_result": [5, 1],
            "container_cpu_limit": cpu_count,
            "container_memory_limit_mb": memory_limit_mb,
            "checkpoint_directory": str(checkpoint_directory),
            "cas_hamiltonian_fci_pauli_vqe_created": False,
        }
        report_path = self._write_json_artifact(run_id, report)
        self.repository.update_quantum_region(
            quantum_region_id,
            owner_user_id,
            preflight_artifact_path=str(report_path),
            status="needs_model_review",
        )
        return {**report, "preflight_artifact_id": report_path.stem}

    def _build_h_capped_cluster(
        self,
        *,
        full_sites: list[dict],
        host_atom_count: int,
        active_site,
        expansion_shells: int,
        label: str,
    ) -> dict:
        host_sites = full_sites[:host_atom_count]
        adsorbate_sites = full_sites[host_atom_count:]
        edges = self._host_covalent_edges(host_sites)
        adjacency: dict[int, set[int]] = {index: set() for index in range(host_atom_count)}
        for left, right in edges:
            adjacency[left].add(right)
            adjacency[right].add(left)
        required = set(active_site.center_atom_indices + active_site.neighbor_atom_indices)
        adsorbate_positions = np.asarray([site["position_angstrom"] for site in adsorbate_sites], dtype=float)
        contact_atoms = {
            index
            for index, site in enumerate(host_sites)
            if np.min(np.linalg.norm(adsorbate_positions - np.asarray(site["position_angstrom"], dtype=float), axis=1))
            <= H_CAPPED_ADSORBATE_CONTACT_DISTANCE_ANGSTROM
        }
        retained_host = self._expand_host_graph(required | contact_atoms, adjacency, expansion_shells)
        cut_bonds = [
            {"retained_atom_index": left, "removed_atom_index": right}
            for left, right in edges
            if (left in retained_host) != (right in retained_host)
        ]
        invalid_cuts = [
            item
            for item in cut_bonds
            if host_sites[item["retained_atom_index"]]["element"] != "C"
            or host_sites[item["removed_atom_index"]]["element"] != "C"
        ]
        if invalid_cuts:
            raise StructureModelingError(
                "h_capped_cluster_invalid_boundary",
                f"{label} 会切断非 C-C 键，已拒绝生成不受控的封端簇。",
                422,
            )
        link_atoms = []
        next_index = len(full_sites)
        for bond in cut_bonds:
            retained_index = bond["retained_atom_index"]
            removed_index = bond["removed_atom_index"]
            retained_position = np.asarray(host_sites[retained_index]["position_angstrom"], dtype=float)
            removed_position = np.asarray(host_sites[removed_index]["position_angstrom"], dtype=float)
            direction = removed_position - retained_position
            length = np.linalg.norm(direction)
            if length == 0:
                raise StructureModelingError("h_capped_cluster_invalid_bond", "检测到零长度边界键。", 422)
            hydrogen_position = retained_position + H_CAPPED_CARBON_HYDROGEN_BOND_LENGTH_ANGSTROM * direction / length
            link_atoms.append(
                {
                    "index": next_index,
                    "element": "H",
                    "position_angstrom": [float(value) for value in hydrogen_position],
                    "is_link_atom": True,
                    "parent_atom_index": retained_index,
                    "cut_bond_partner_index": removed_index,
                }
            )
            bond["link_atom_index"] = next_index
            bond["bond_length_angstrom"] = float(length)
            next_index += 1
        region_atom_indices = sorted(retained_host) + list(range(host_atom_count, len(full_sites)))
        frozen_indices = [index for index in range(host_atom_count) if index not in retained_host]
        retained_sites = [full_sites[index] for index in region_atom_indices]
        capped_sites = [*retained_sites, *link_atoms]
        formula = Atoms(symbols=[site["element"] for site in capped_sites]).get_chemical_formula(mode="hill")
        return {
            "boundary_label": label,
            "boundary_rule": {
                "graph_expansion_shells": expansion_shells,
                "adsorbate_contact_distance_angstrom": H_CAPPED_ADSORBATE_CONTACT_DISTANCE_ANGSTROM,
                "bond_detection": "ASE covalent radii plus 0.25 angstrom",
                "link_atom_rule": "C-H link atom along retained-to-removed C-C bond vector",
                "carbon_hydrogen_bond_length_angstrom": H_CAPPED_CARBON_HYDROGEN_BOND_LENGTH_ANGSTROM,
            },
            "region_atom_indices": region_atom_indices,
            "frozen_environment_atom_indices": frozen_indices,
            "direct_adsorbate_contact_atom_indices": sorted(contact_atoms),
            "cut_bonds": cut_bonds,
            "link_atoms": link_atoms,
            "capped_formula": formula,
            "atomic_sites": capped_sites,
        }

    def _build_reduced_local_cluster(self, full_sites: list[dict], active_site) -> dict:
        """Keep the requested Fe-N4/Li2S4 core and terminate only graphitic C-C boundaries."""
        fe_indices = list(active_site.center_atom_indices)
        nitrogen_indices = [index for index in active_site.neighbor_atom_indices if full_sites[index]["element"] == "N"]
        if len(fe_indices) != 1 or full_sites[fe_indices[0]]["element"] != "Fe" or len(nitrogen_indices) != 4:
            raise StructureModelingError("reduced_model_active_site_invalid", "缩减模型要求一个 Fe 和四个已确认 N。", 409)
        host_atom_count = min(index for index, site in enumerate(full_sites) if site["element"] != "C")
        first_layer_carbons = self._nitrogen_bound_carbons(full_sites, host_atom_count, nitrogen_indices)
        adsorbate_indices = [index for index in range(host_atom_count, len(full_sites)) if index not in {*fe_indices, *nitrogen_indices}]
        adsorbate_formula = Atoms(symbols=[full_sites[index]["element"] for index in adsorbate_indices]).get_chemical_formula(mode="hill")
        if adsorbate_formula != "Li2S4":
            raise StructureModelingError("reduced_model_adsorbate_invalid", "缩减模型必须保留完整 Li2S4。", 409)
        retained_indices = sorted({*fe_indices, *nitrogen_indices, *first_layer_carbons, *adsorbate_indices})
        edges = self._host_covalent_edges(full_sites[:host_atom_count])
        cut_bonds = []
        for left, right in edges:
            if left in first_layer_carbons and right not in first_layer_carbons:
                cut_bonds.append({"retained_atom_index": left, "removed_atom_index": right})
            elif right in first_layer_carbons and left not in first_layer_carbons:
                cut_bonds.append({"retained_atom_index": right, "removed_atom_index": left})
        if any(
            full_sites[bond["retained_atom_index"]]["element"] != "C"
            or full_sites[bond["removed_atom_index"]]["element"] != "C"
            for bond in cut_bonds
        ):
            raise StructureModelingError("reduced_model_non_cc_boundary", "缩减模型边界包含非 C-C 键，已拒绝生成。", 422)
        link_atoms = self._build_link_atoms(full_sites, cut_bonds)
        capped_sites = [full_sites[index] for index in retained_indices] + link_atoms
        structure_sha256 = self._structure_sha256(capped_sites)
        return {
            "retention_rule": "Fe + four confirmed N + complete Li2S4 + every C directly bonded to N",
            "boundary_rule": "Only cut C-C bonds; add a 1.09 angstrom H link atom along the retained-to-removed bond vector.",
            "region_atom_indices": retained_indices,
            "deleted_atom_indices": [index for index in range(len(full_sites)) if index not in retained_indices],
            "first_layer_carbon_atom_indices": sorted(first_layer_carbons),
            "cut_bonds": cut_bonds,
            "link_atoms": link_atoms,
            "atomic_sites": capped_sites,
            "capped_formula": Atoms(symbols=[site["element"] for site in capped_sites]).get_chemical_formula(mode="hill"),
            "neutral_electron_count": sum(atomic_numbers[site["element"]] for site in capped_sites),
            "estimated_def2_svp_spherical_ao_count": self._estimate_def2_svp_spherical_aos(capped_sites),
            "structure_sha256": structure_sha256,
        }

    @staticmethod
    def _nitrogen_bound_carbons(full_sites: list[dict], host_atom_count: int, nitrogen_indices: list[int]) -> set[int]:
        carbons: set[int] = set()
        for nitrogen_index in nitrogen_indices:
            nitrogen_position = np.asarray(full_sites[nitrogen_index]["position_angstrom"], dtype=float)
            maximum_distance = covalent_radii[atomic_numbers["N"]] + covalent_radii[atomic_numbers["C"]] + H_CAPPED_COVALENT_BOND_TOLERANCE_ANGSTROM
            for carbon_index in range(host_atom_count):
                if np.linalg.norm(nitrogen_position - np.asarray(full_sites[carbon_index]["position_angstrom"], dtype=float)) <= maximum_distance:
                    carbons.add(carbon_index)
        if len(carbons) < 4:
            raise StructureModelingError("reduced_model_first_layer_missing", "未能完整识别 N 的第一层 C。", 422)
        return carbons

    @staticmethod
    def _build_link_atoms(full_sites: list[dict], cut_bonds: list[dict]) -> list[dict]:
        link_atoms = []
        for offset, bond in enumerate(cut_bonds, start=len(full_sites)):
            retained_position = np.asarray(full_sites[bond["retained_atom_index"]]["position_angstrom"], dtype=float)
            removed_position = np.asarray(full_sites[bond["removed_atom_index"]]["position_angstrom"], dtype=float)
            direction = removed_position - retained_position
            bond_length = np.linalg.norm(direction)
            if bond_length == 0:
                raise StructureModelingError("reduced_model_zero_boundary_bond", "检测到零长度边界键。", 422)
            bond["link_atom_index"] = offset
            bond["bond_length_angstrom"] = float(bond_length)
            link_atoms.append(
                {
                    "index": offset,
                    "element": "H",
                    "position_angstrom": [
                        float(value)
                        for value in retained_position + H_CAPPED_CARBON_HYDROGEN_BOND_LENGTH_ANGSTROM * direction / bond_length
                    ],
                    "is_link_atom": True,
                    "parent_atom_index": bond["retained_atom_index"],
                    "cut_bond_partner_index": bond["removed_atom_index"],
                }
            )
        return link_atoms

    @staticmethod
    def _structure_sha256(atomic_sites: list[dict]) -> str:
        canonical_sites = [
            {"index": site["index"], "element": site["element"], "position_angstrom": site["position_angstrom"]}
            for site in atomic_sites
        ]
        return hashlib.sha256(json.dumps(canonical_sites, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _estimate_def2_svp_spherical_aos(atomic_sites: list[dict]) -> int:
        unsupported = sorted({site["element"] for site in atomic_sites} - set(DEF2_SVP_SPHERICAL_AO_ESTIMATES))
        if unsupported:
            raise StructureModelingError("basis_estimate_unsupported_element", f"无法估算 def2-SVP AO：{', '.join(unsupported)}", 422)
        return sum(DEF2_SVP_SPHERICAL_AO_ESTIMATES[site["element"]] for site in atomic_sites)

    @staticmethod
    def _reduced_cluster_summary(cluster: dict) -> dict:
        return {
            "model_label": REDUCED_LOCAL_MODEL_LABEL,
            "atom_count": len(cluster["atomic_sites"]),
            "neutral_electron_count": cluster["neutral_electron_count"],
            "estimated_def2_svp_spherical_ao_count": cluster["estimated_def2_svp_spherical_ao_count"],
            "structure_sha256": cluster["structure_sha256"],
            "capped_formula": cluster["capped_formula"],
        }

    @staticmethod
    def _reduced_local_scf_options() -> dict:
        return {
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "df_cderi_path": "/checkpoints/df_cderi.h5",
            "checkpoint_path": "/checkpoints/scf.chk",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_memory_mb": REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            "max_cycle": 300,
            "record_iteration_energy": True,
            "diis_space": 12,
            "conv_tol": 1e-8,
            "conv_tol_grad": 1e-5,
            "strategies": [
                {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False},
            ],
        }

    @staticmethod
    def _reduced_local_memory_calibration_options() -> dict:
        return {
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "df_cderi_path": "/checkpoints/df_cderi.h5",
            "checkpoint_path": "/checkpoints/scf.chk",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_memory_mb": REDUCED_LOCAL_CALIBRATION_PYSCF_MEMORY_MB,
            "max_cycle": 1,
            "record_iteration_energy": False,
            "diis_space": 8,
            "conv_tol": 1e-8,
            "conv_tol_grad": 1e-5,
            "strategies": [
                {"level_shift": 0.3, "initial_guess": "atom", "damping": 0.1, "use_newton": False},
            ],
        }

    @staticmethod
    def _reduced_local_newton_rescue_options() -> dict:
        return {
            "newton_rescue_mode": True,
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "df_cderi_path": "/checkpoints/df_cderi.h5",
            "checkpoint_path": "/checkpoints/scf.chk",
            "checkpoint_validation_path": "/checkpoints/checkpoint_validation.json",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_memory_mb": REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            "max_cycle": REDUCED_LOCAL_NEWTON_MAX_CYCLES,
            "record_iteration_energy": True,
            "macro_gradient_stagnation_window": REDUCED_LOCAL_NEWTON_STAGNATION_WINDOW,
            "conv_tol": 1e-8,
            "conv_tol_grad": 1e-5,
            "strategies": [
                {"level_shift": 0.0, "initial_guess": "atom", "damping": 0.0, "use_newton": True},
            ],
        }

    @staticmethod
    def _reduced_local_uks_preconditioner_options() -> dict:
        return {
            "preconditioner_only": True,
            "xc": "PBE",
            "grid_level": 1,
            "grid_pruning": "pyscf_default",
            "density_fitting": True,
            "density_fitting_auxbasis": None,
            "df_cderi_load_path": "/inputs/df_cderi.h5",
            "initial_density_checkpoint_path": "/checkpoints/source_uhf.chk",
            "checkpoint_validation_source_path": "/checkpoints/source_uhf.chk",
            "checkpoint_path": "/checkpoints/scf.chk",
            "checkpoint_validation_path": "/checkpoints/checkpoint_validation.json",
            "density_output_path": "/checkpoints/uks_density.npz",
            "progress_path": "/checkpoints/scf_progress.jsonl",
            "max_memory_mb": REDUCED_LOCAL_FULL_SCF_PYSCF_MEMORY_MB,
            "max_cycle": REDUCED_LOCAL_UKS_MAX_CYCLES,
            "conv_tol": 1e-7,
            "conv_tol_grad": 1e-4,
            "oscillation_minimum_completed_cycles": REDUCED_LOCAL_UKS_OSCILLATION_MINIMUM_CYCLES,
            "oscillation_window_size": REDUCED_LOCAL_UKS_OSCILLATION_WINDOW,
            "oscillation_minimum_direction_reversals": REDUCED_LOCAL_UKS_OSCILLATION_REVERSALS,
            "oscillation_minimum_gradient": REDUCED_LOCAL_UKS_OSCILLATION_MINIMUM_GRADIENT,
            "rapid_residual_growth_multiplier": REDUCED_LOCAL_UKS_RAPID_GROWTH_MULTIPLIER,
        }

    @staticmethod
    def _reduced_local_resource_diagnostic(
        *,
        cpu_count: int = 4,
        container_memory_mb: int = REDUCED_LOCAL_CONTAINER_MEMORY_MB,
        pyscf_memory_mb: int = REDUCED_LOCAL_PYSCF_MEMORY_MB,
        host_memory_threshold_bytes: int = REDUCED_LOCAL_HOST_MEMORY_THRESHOLD_BYTES,
        host_memory_reserve_bytes: int | None = None,
        minimum_disk_free_bytes: int = 0,
    ) -> dict:
        try:
            import psutil

            memory_available_bytes = psutil.virtual_memory().available
            host_logical_cpu_count = psutil.cpu_count(logical=True)
            memory_probe_error = None
        except ImportError:
            memory_available_bytes = 0
            host_logical_cpu_count = None
            memory_probe_error = "psutil is unavailable; cannot safely verify the host-memory guardrail."
        docker_version = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], text=True, capture_output=True, check=False)
        docker_ready = docker_version.returncode == 0
        disk_free_bytes = shutil.disk_usage(STRUCTURE_ARTIFACT_ROOT).free
        return {
            "host_memory_available_bytes": memory_available_bytes,
            "host_memory_threshold_bytes": host_memory_threshold_bytes,
            "host_memory_reserve_bytes": host_memory_reserve_bytes,
            "host_logical_cpu_count": host_logical_cpu_count,
            "host_cpu_reserve": 2,
            "container_cpu_limit": cpu_count,
            "container_memory_limit_mb": container_memory_mb,
            "pyscf_max_memory_mb": pyscf_memory_mb,
            "disk_free_bytes": disk_free_bytes,
            "minimum_disk_free_bytes": minimum_disk_free_bytes,
            "docker_engine_version": docker_version.stdout.strip() if docker_ready else None,
            "docker_engine_diagnostic": docker_version.stderr.strip() if not docker_ready else None,
            "memory_probe_error": memory_probe_error,
            "eligible": (
                memory_probe_error is None
                and docker_ready
                and memory_available_bytes >= host_memory_threshold_bytes
                and host_logical_cpu_count is not None
                and host_logical_cpu_count >= cpu_count + 2
                and disk_free_bytes >= minimum_disk_free_bytes
            ),
        }

    @staticmethod
    def _host_covalent_edges(host_sites: list[dict]) -> list[tuple[int, int]]:
        edges: list[tuple[int, int]] = []
        for left in range(len(host_sites)):
            left_site = host_sites[left]
            left_position = np.asarray(left_site["position_angstrom"], dtype=float)
            for right in range(left + 1, len(host_sites)):
                right_site = host_sites[right]
                maximum_distance = (
                    covalent_radii[atomic_numbers[left_site["element"]]]
                    + covalent_radii[atomic_numbers[host_sites[right]["element"]]]
                    + H_CAPPED_COVALENT_BOND_TOLERANCE_ANGSTROM
                )
                if np.linalg.norm(left_position - np.asarray(host_sites[right]["position_angstrom"], dtype=float)) <= maximum_distance:
                    edges.append((left, right))
        return edges

    @staticmethod
    def _expand_host_graph(seed_indices: set[int], adjacency: dict[int, set[int]], expansion_shells: int) -> set[int]:
        retained = set(seed_indices)
        frontier = set(seed_indices)
        for _ in range(expansion_shells):
            frontier = {neighbor for node in frontier for neighbor in adjacency[node] if neighbor not in retained}
            retained.update(frontier)
        return retained

    @staticmethod
    def _parity_valid_charge_spin_groups(neutral_electron_count: int) -> list[tuple[int, list[int]]]:
        groups = []
        for charge in (-1, 0, 1):
            electron_count = neutral_electron_count - charge
            groups.append((charge, [1, 3, 5] if electron_count % 2 == 0 else [2, 4]))
        return groups

    def _build_h_capped_preflight_report(
        self,
        region,
        owner_user_id: int,
        neutral_electron_count: int,
        timeout_seconds: int,
        scan_summaries: list[dict],
    ) -> dict:
        cluster = self._read_json_artifact(region.geometry_artifact_path)
        candidates = self.repository.list_electronic_structure_candidates(region.quantum_region_id, owner_user_id)
        candidate_reports = [self._serialize_h_capped_preflight_candidate(record) for record in candidates]
        eligible = [item for item in candidate_reports if item["quality_status"] == "eligible_for_confirmation"]
        return {
            "report_type": "h_capped_finite_cluster_scf_preflight",
            "quantum_region_id": region.quantum_region_id,
            "boundary_label": cluster["boundary_label"],
            "capped_formula": cluster["capped_formula"],
            "source_candidate_sha256": cluster["source_candidate_sha256"],
            "region_atom_indices": cluster["region_atom_indices"],
            "frozen_environment_atom_indices": cluster["frozen_environment_atom_indices"],
            "cut_bonds": cluster["cut_bonds"],
            "link_atoms": cluster["link_atoms"],
            "neutral_electron_count": neutral_electron_count,
            "charge_spin_scan": [
                {"charge": charge, "spin_multiplicities": multiplicities}
                for charge, multiplicities in self._parity_valid_charge_spin_groups(neutral_electron_count)
            ],
            "timeout_seconds_per_candidate": timeout_seconds,
            "scan_summaries": scan_summaries,
            "candidates": candidate_reports,
            "eligible_candidate_count": len(eligible),
            "status": "needs_model_review",
            "conclusion": "候选仅用于边界敏感性预检；未确认电荷、自旋或 CAS，且未执行 VQE 闭环。",
        }

    def _serialize_h_capped_preflight_candidate(self, record) -> dict:
        payload = self._read_json_artifact(record.result_artifact_path) if record.result_artifact_path else {}
        active_spaces = []
        for candidate in payload.get("active_space_candidates", []):
            active_orbitals = candidate.get("active_orbitals")
            active_electrons = candidate.get("active_electrons")
            if not isinstance(active_orbitals, int) or not isinstance(active_electrons, int):
                continue
            active_spaces.append(
                {
                    **candidate,
                    "mapping_qubit_count": active_orbitals * 2,
                    "fci_determinant_dimension": self._estimate_fci_determinant_dimension(
                        active_electrons,
                        active_orbitals,
                        record.spin_multiplicity,
                    ),
                    "within_protocol_guardrails": active_orbitals <= QUANTUM_CLOSURE_MAX_ACTIVE_ORBITALS,
                }
            )
        return {
            "candidate_id": record.candidate_id,
            "total_charge": record.total_charge,
            "spin_multiplicity": record.spin_multiplicity,
            "quality_status": record.quality_status,
            "scf_converged": bool(record.converged),
            "total_energy_hartree": record.total_energy_hartree,
            "spin_square_s2": record.spin_square_s2,
            "expected_spin_square_s2": record.expected_spin_square_s2,
            "spin_contamination": record.spin_contamination_delta,
            "spin_contamination_threshold": record.spin_contamination_threshold,
            "frontier_orbitals": self._frontier_orbitals(payload),
            "active_space_candidates": active_spaces,
            "scf_configuration": payload.get("scf_configuration"),
            "runtime_metadata": payload.get("runtime_metadata"),
            "execution_metadata": payload.get("execution_metadata"),
            "failure_diagnostic": payload.get("diagnostic"),
            "warnings": record.warnings,
            "result_artifact_id": Path(record.result_artifact_path).stem if record.result_artifact_path else None,
        }

    @staticmethod
    def _frontier_orbitals(payload: dict) -> dict | None:
        energies = payload.get("orbital_energies_hartree") or []
        occupancies = payload.get("occupancies") or []
        if not energies or len(energies) != len(occupancies):
            return None
        occupied = [index for index, occupancy in enumerate(occupancies) if occupancy > 1e-8]
        virtual = [index for index, occupancy in enumerate(occupancies) if occupancy < 1e-8]
        homo = occupied[-1] if occupied else None
        lumo = virtual[0] if virtual else None
        return {
            "homo_index": homo,
            "homo_energy_hartree": energies[homo] if homo is not None else None,
            "lumo_index": lumo,
            "lumo_energy_hartree": energies[lumo] if lumo is not None else None,
        }

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
            task_owner_user_id=owner_user_id,
        )
        return {"task_id": task_id, "status": "queued", "message": "多自旋电子结构候选已提交后台执行。"}

    def get_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_electronic_structure_candidate(candidate_id, owner_user_id)
        if record is None:
            raise StructureModelingError("electronic_structure_candidate_not_found", "未找到电子结构候选或无权访问。", 404)
        return self.serialize_electronic_structure_candidate(record)

    @staticmethod
    def _assert_not_preconditioner_only(payload: dict) -> None:
        if payload.get("preconditioner_only") or payload.get("downstream_consumable") is False:
            raise StructureModelingError(
                "preconditioner_only_not_consumable",
                "density preconditioner Artifact 不能确认或被量子闭环消费。",
                409,
            )

    @staticmethod
    def _electronic_structure_result_quality(result: dict, contamination_threshold: float) -> tuple[bool, bool, str]:
        if result.get("preconditioner_only") or result.get("downstream_consumable") is False:
            return False, False, "preconditioner_only"
        contamination = result.get("spin_contamination")
        is_converged = result.get("status") not in {"needs_model_review", "failed"}
        exceeds_threshold = contamination is not None and contamination > contamination_threshold
        if result.get("status") == "failed":
            return False, exceeds_threshold, "failed"
        quality_status = "eligible_for_confirmation" if is_converged and not exceeds_threshold else "needs_model_review"
        return is_converged, exceeds_threshold, quality_status

    def confirm_electronic_structure_candidate(self, candidate_id: str, owner_user_id: int, request: dict) -> dict:
        candidate = self.repository.get_electronic_structure_candidate(candidate_id, owner_user_id)
        if candidate is None:
            raise StructureModelingError("electronic_structure_candidate_not_found", "未找到电子结构候选或无权访问。", 404)
        if candidate.result_artifact_path:
            self._assert_not_preconditioner_only(self._read_json_artifact(candidate.result_artifact_path))
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

    def create_quantum_closure_benchmark(
        self,
        hamiltonian_id: str,
        owner_user_id: int,
        request: dict,
    ) -> dict:
        """Run the protocol-locked FCI, exact-Pauli and simulator-VQE comparison."""
        context = self._validate_quantum_closure_preflight(hamiltonian_id, owner_user_id)
        hamiltonian = context["hamiltonian"]
        active_space = context["active_space"]
        region = context["region"]
        benchmark = context["benchmark"]
        candidate = context["candidate"]
        workflow = context["workflow"]

        closure_id = self._new_id("closure")
        input_manifest_path = self._write_quantum_closure_artifact(
            f"{closure_id}_input_manifest",
            {
                "protocol": "fe-n4c66-li2s4-quantum-closure-v1",
                "benchmark_key": benchmark.benchmark_key,
                "research_benchmark_id": benchmark.benchmark_id,
                "research_candidate_id": candidate.candidate_id,
                "source_candidate_id": candidate.source_candidate_id,
                "source_candidate_sha256": context["source_candidate_sha256"],
                "workflow_id": workflow.workflow_id,
                "quantum_region_id": region.quantum_region_id,
                "quantum_region_geometry_sha256": context["quantum_region_geometry_sha256"],
                "active_space_id": active_space.active_space_id,
                "active_electrons": active_space.active_electrons,
                "active_orbitals": active_space.active_orbitals,
                "orbital_indices": active_space.orbital_indices,
                "spin_multiplicity": region.spin_multiplicity,
                "basis_set": hamiltonian.basis_set,
                "fermionic_hamiltonian_id": hamiltonian.hamiltonian_id,
                "fermionic_hamiltonian_sha256": hamiltonian.artifact_hash,
                "request": request,
                "execution_backend_type": "simulator",
                "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
            },
            {"fermionic_hamiltonian_id": hamiltonian.hamiltonian_id, "research_candidate_id": candidate.candidate_id},
        )
        artifacts = {"closure_input_manifest": self._artifact_descriptor(input_manifest_path)}

        classical_response = self.generate_classical_reference(hamiltonian_id, owner_user_id)
        classical_reference = self.repository.get_classical_reference(classical_response["reference_id"], owner_user_id)
        if classical_reference is None or classical_reference.status != "completed" or classical_reference.energy_hartree is None:
            raise StructureModelingError("classical_reference_failed", "FCI 经典参考未成功完成，无法建立量子闭环。", 409)
        classical_payload = self._read_json_artifact(classical_reference.artifact_path)
        classical_path = self._write_quantum_closure_artifact(
            f"{closure_id}_classical_reference",
            {
                "upstream_classical_reference_id": classical_reference.reference_id,
                "upstream_artifact_sha256": self._hash_file(Path(classical_reference.artifact_path), "sha256"),
                "result": classical_payload,
            },
            {"classical_reference_id": classical_reference.reference_id},
        )
        artifacts["classical_reference"] = self._artifact_descriptor(classical_path)

        mapping_response = self.map_fermionic_hamiltonian(
            hamiltonian_id,
            owner_user_id,
            {
                "mapping_method": request["mapping_method"],
                "enable_z2_tapering": False,
                "z2_tapering_sectors": None,
                "pauli_coefficient_cutoff": QUANTUM_CLOSURE_PAULI_COEFFICIENT_CUTOFF,
            },
        )
        qubit_hamiltonian = self.repository.get_qubit_hamiltonian(mapping_response["qubit_hamiltonian_id"], owner_user_id)
        if qubit_hamiltonian is None:
            raise StructureModelingError("qubit_mapping_failed", "Pauli Hamiltonian 未保存。", 500)
        if qubit_hamiltonian.qubit_count > QUANTUM_CLOSURE_MAX_QUBITS:
            raise StructureModelingError("quantum_closure_qubit_limit", "映射后的量子比特数超过闭环基准上限。", 422)
        pauli_payload = self._read_json_artifact(qubit_hamiltonian.pauli_artifact_path)
        pauli_path = self._write_quantum_closure_artifact(
            f"{closure_id}_pauli_hamiltonian",
            {
                "upstream_qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id,
                "upstream_artifact_sha256": self._hash_file(Path(qubit_hamiltonian.pauli_artifact_path), "sha256"),
                "mapping_method": qubit_hamiltonian.mapping_method,
                "qubit_count": qubit_hamiltonian.qubit_count,
                "pauli_hamiltonian": pauli_payload,
            },
            {"qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id},
        )
        artifacts["pauli_hamiltonian"] = self._artifact_descriptor(pauli_path)

        try:
            exact_pauli = self.vqe_service.exact_diagonalize_pauli_hamiltonian(
                qubit_hamiltonian.qubit_count,
                pauli_payload["pauli_terms"],
            )
        except ValueError as exc:
            raise StructureModelingError("exact_pauli_diagonalization_failed", str(exc), 422) from exc
        exact_path = self._write_quantum_closure_artifact(
            f"{closure_id}_exact_pauli_diagonalization",
            {
                "qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id,
                "pauli_hamiltonian_sha256": self._hash_file(pauli_path, "sha256"),
                "result": exact_pauli,
            },
            {"qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id},
        )
        artifacts["exact_pauli_diagonalization"] = self._artifact_descriptor(exact_path)
        fci_energy = float(classical_reference.energy_hartree)
        exact_energy = exact_pauli["ground_state_energy_hartree"]
        mapping_error = abs(fci_energy - exact_energy)

        if mapping_error > request["mapping_tolerance_hartree"]:
            return self._persist_quantum_closure_result(
                closure_id=closure_id,
                context=context,
                request=request,
                artifacts=artifacts,
                qubit_hamiltonian=qubit_hamiltonian,
                classical_reference=classical_reference,
                fci_energy=fci_energy,
                exact_energy=exact_energy,
                mapping_error=mapping_error,
                status="mapping_mismatch",
                qualification="invalid_mapping_reference",
                failure_code="mapping_mismatch",
            )

        vqe_request = {
            "ansatz": "hardware_efficient_ry_cx",
            "ansatz_layers": request["ansatz_layers"],
            "optimizer": request["optimizer"],
            "max_iterations": request["max_iterations"],
            "convergence_tolerance": request["convergence_tolerance"],
            "shots": request["shots"],
            "measurement_grouping": "qubit_wise_commuting",
        }
        circuit_response = self.compile_vqe_circuit(qubit_hamiltonian.qubit_hamiltonian_id, owner_user_id, vqe_request)
        circuit = self.repository.get_vqe_circuit(circuit_response["vqe_circuit_id"], owner_user_id)
        qasm_path = self._write_quantum_closure_artifact(
            f"{closure_id}_vqe_circuit_qasm",
            {
                "upstream_vqe_circuit_id": circuit.vqe_circuit_id,
                "ansatz": "ry_cx",
                "qasm": self._read_json_artifact(circuit.qasm_artifact_path),
            },
            {"vqe_circuit_id": circuit.vqe_circuit_id},
        )
        artifacts["vqe_circuit_qasm"] = self._artifact_descriptor(qasm_path)
        execution_response = self.execute_vqe_circuit(circuit.vqe_circuit_id, owner_user_id)
        execution = self.repository.get_vqe_execution(execution_response["execution_id"], owner_user_id)
        history_path = self._write_quantum_closure_artifact(
            f"{closure_id}_vqe_iteration_history",
            {
                "upstream_vqe_execution_id": execution.execution_id,
                "execution_backend_type": "simulator",
                "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
                "result": self._read_json_artifact(execution.iteration_artifact_path),
            },
            {"vqe_execution_id": execution.execution_id},
        )
        artifacts["vqe_iteration_history"] = self._artifact_descriptor(history_path)
        vqe_energy = float(execution.final_energy_hartree)
        vqe_error = abs(vqe_energy - exact_energy)
        status, qualification, failure_code = self._classify_quantum_closure(
            vqe_energy=vqe_energy,
            exact_energy=exact_energy,
            vqe_error=vqe_error,
            converged=bool(execution.converged),
            vqe_target_tolerance=request["vqe_target_tolerance_hartree"],
        )
        return self._persist_quantum_closure_result(
            closure_id=closure_id,
            context=context,
            request=request,
            artifacts=artifacts,
            qubit_hamiltonian=qubit_hamiltonian,
            classical_reference=classical_reference,
            vqe_execution=execution,
            fci_energy=fci_energy,
            exact_energy=exact_energy,
            vqe_energy=vqe_energy,
            mapping_error=mapping_error,
            vqe_error=vqe_error,
            status=status,
            qualification=qualification,
            failure_code=failure_code,
        )

    def get_quantum_closure_benchmark(self, closure_benchmark_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_quantum_closure_benchmark(closure_benchmark_id, owner_user_id)
        if record is None:
            raise StructureModelingError("quantum_closure_benchmark_not_found", "未找到量子闭环基准或无权访问。", 404)
        return self._serialize_quantum_closure_benchmark(record)

    def list_quantum_closure_benchmarks(self, workflow_id: str, owner_user_id: int) -> dict:
        if self.repository.get_workflow(workflow_id, owner_user_id) is None:
            raise StructureModelingError("workflow_not_found", "未找到结构建模工作流。", 404)
        return {
            "workflow_id": workflow_id,
            "items": [
                self._serialize_quantum_closure_benchmark(record)
                for record in self.repository.list_quantum_closure_benchmarks(workflow_id, owner_user_id)
            ],
        }

    def _validate_quantum_closure_preflight(self, hamiltonian_id: str, owner_user_id: int) -> dict:
        """Freeze and validate the only literature-backed input chain eligible for this protocol."""
        hamiltonian = self.repository.get_fermionic_hamiltonian(hamiltonian_id, owner_user_id)
        if hamiltonian is None:
            raise StructureModelingError("hamiltonian_not_found", "未找到费米子 Hamiltonian 或无权访问。", 404)
        active_space = self.repository.get_active_space(hamiltonian.active_space_id, owner_user_id)
        if active_space is None or active_space.status != "confirmed":
            raise StructureModelingError("active_space_not_confirmed", "量子闭环仅允许使用已确认的活性空间。", 409)
        region = self.repository.get_quantum_region(active_space.quantum_region_id, owner_user_id)
        if region is None or region.status != "quantum_region_built":
            raise StructureModelingError("quantum_region_not_ready", "量子区尚未完成电荷和自旋确认。", 409)
        if region.total_charge is None or region.spin_multiplicity is None:
            raise StructureModelingError("quantum_region_model_incomplete", "量子区缺少已确认的电荷或自旋多重度。", 409)
        orbital_metadata = active_space.orbital_metadata or {}
        if orbital_metadata.get("spin_contamination_warning") or not orbital_metadata.get("method_name"):
            raise StructureModelingError("needs_model_review", "SCF 自旋污染或收敛依据未通过，不能创建闭环基准。", 409)
        if active_space.active_orbitals > QUANTUM_CLOSURE_MAX_ACTIVE_ORBITALS:
            raise StructureModelingError("quantum_closure_active_orbital_limit", "活性轨道数超过闭环基准上限 4。", 422)
        determinant_dimension = self._estimate_fci_determinant_dimension(
            active_space.active_electrons,
            active_space.active_orbitals,
            region.spin_multiplicity,
        )
        if determinant_dimension > QUANTUM_CLOSURE_MAX_FCI_DETERMINANTS:
            raise StructureModelingError(
                "quantum_closure_fci_resource_limit",
                f"FCI 行列式维度 {determinant_dimension} 超过上限 {QUANTUM_CLOSURE_MAX_FCI_DETERMINANTS}。",
                422,
            )
        adsorption_model = self.repository.get_adsorption_model(region.adsorption_model_id, owner_user_id)
        active_site = self.repository.get_active_site(adsorption_model.active_site_id, owner_user_id) if adsorption_model else None
        structure = self.repository.get_structure(active_site.structure_id, owner_user_id) if active_site else None
        workflow = self.repository.get_workflow(structure.workflow_id, owner_user_id) if structure else None
        if workflow is None:
            raise StructureModelingError("workflow_not_found", "无法回溯量子闭环所属的结构工作流。", 409)
        selection = self.repository.get_research_benchmark_selection_for_workflow(workflow.workflow_id, owner_user_id)
        if selection is None:
            raise StructureModelingError("quantum_closure_literature_selection_required", "量子闭环必须从冻结的文献候选工作流发起。", 409)
        benchmark = self.repository.get_research_benchmark(selection.benchmark_id)
        candidate = self.repository.get_research_benchmark_candidate(selection.benchmark_id, selection.candidate_id)
        if benchmark is None or candidate is None:
            raise StructureModelingError("research_benchmark_not_found", "文献基准或候选记录不可用。", 409)
        if benchmark.benchmark_key != QUANTUM_CLOSURE_BENCHMARK_KEY:
            raise StructureModelingError("quantum_closure_benchmark_key_required", "首期量子闭环只允许指定的 FeN4C66-Li2S4 文献基准。", 422)
        if benchmark.scientific_validation_level != "reproduction_baseline_only":
            raise StructureModelingError("quantum_closure_validation_level_invalid", "文献基准的科学验证级别不符合闭环协议。", 422)
        workflow_payload = workflow.payload or {}
        if workflow_payload.get("data_source") != "literature_open_dataset":
            raise StructureModelingError("quantum_closure_data_source_invalid", "闭环工作流必须保留 literature_open_dataset 来源。", 422)
        candidate_payload = self._read_json_artifact(candidate.coordinate_artifact_path)
        composition = Counter(site["element"] for site in candidate_payload.get("atomic_sites", []))
        required_composition = Counter({"C": 66, "Fe": 1, "N": 4, "Li": 2, "S": 4})
        if composition != required_composition or candidate.source_metadata.get("composition_validation") != "passed":
            raise StructureModelingError("quantum_closure_candidate_composition_invalid", "文献候选未通过 C66 Fe1 N4 Li2 S4 组成校验。", 422)
        candidate_path = Path(candidate.coordinate_artifact_path)
        region_path = Path(region.geometry_artifact_path)
        return {
            "hamiltonian": hamiltonian,
            "active_space": active_space,
            "region": region,
            "workflow": workflow,
            "benchmark": benchmark,
            "candidate": candidate,
            "fci_determinant_dimension": determinant_dimension,
            "source_candidate_sha256": self._hash_file(candidate_path, "sha256"),
            "quantum_region_geometry_sha256": self._hash_file(region_path, "sha256"),
        }

    @staticmethod
    def _estimate_fci_determinant_dimension(active_electrons: int, active_orbitals: int, spin_multiplicity: int) -> int:
        spin_excess = spin_multiplicity - 1
        alpha_numerator = active_electrons + spin_excess
        beta_numerator = active_electrons - spin_excess
        if alpha_numerator % 2 or beta_numerator % 2 or beta_numerator < 0:
            raise StructureModelingError("quantum_closure_spin_electron_inconsistent", "CAS 电子数与自旋多重度不一致。", 422)
        alpha_electrons = alpha_numerator // 2
        beta_electrons = beta_numerator // 2
        if alpha_electrons > active_orbitals or beta_electrons > active_orbitals:
            raise StructureModelingError("quantum_closure_electron_orbital_inconsistent", "CAS 电子数超过活性轨道可容纳范围。", 422)
        return math.comb(active_orbitals, alpha_electrons) * math.comb(active_orbitals, beta_electrons)

    @staticmethod
    def _classify_quantum_closure(
        *,
        vqe_energy: float,
        exact_energy: float,
        vqe_error: float,
        converged: bool,
        vqe_target_tolerance: float,
    ) -> tuple[str, str, str | None]:
        if vqe_energy < exact_energy - QUANTUM_CLOSURE_VARIATIONAL_TOLERANCE_HARTREE:
            return "non_variational_result", "simulator_vqe_outside_target", "non_variational_result"
        if not converged:
            return "vqe_not_converged", "simulator_vqe_outside_target", "vqe_not_converged"
        if vqe_error > vqe_target_tolerance:
            return "vqe_outside_target", "simulator_vqe_outside_target", "vqe_outside_target"
        return "benchmark_validated_simulator_vqe", "benchmark_validated_simulator_vqe", None

    def _persist_quantum_closure_result(
        self,
        *,
        closure_id: str,
        context: dict,
        request: dict,
        artifacts: dict,
        qubit_hamiltonian,
        classical_reference,
        status: str,
        qualification: str,
        failure_code: str | None,
        fci_energy: float,
        exact_energy: float,
        mapping_error: float,
        vqe_execution=None,
        vqe_energy: float | None = None,
        vqe_error: float | None = None,
    ) -> dict:
        result_path = self._write_quantum_closure_artifact(
            f"{closure_id}_result",
            {
                "closure_benchmark_id": closure_id,
                "protocol": "fe-n4c66-li2s4-quantum-closure-v1",
                "energies_hartree": {
                    "E_FCI": fci_energy,
                    "E_exact_pauli": exact_energy,
                    "E_VQE": vqe_energy,
                },
                "errors_hartree": {"mapping_error": mapping_error, "vqe_error": vqe_error},
                "thresholds_hartree": {
                    "mapping_tolerance": request["mapping_tolerance_hartree"],
                    "vqe_target_tolerance": request["vqe_target_tolerance_hartree"],
                    "variational_tolerance": QUANTUM_CLOSURE_VARIATIONAL_TOLERANCE_HARTREE,
                },
                "status": status,
                "result_qualification": qualification,
                "failure_code": failure_code,
                "execution_backend_type": "simulator",
                "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
                "artifacts": artifacts,
            },
            {
                "fermionic_hamiltonian_id": context["hamiltonian"].hamiltonian_id,
                "qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id,
                "classical_reference_id": classical_reference.reference_id,
                "vqe_execution_id": vqe_execution.execution_id if vqe_execution is not None else None,
            },
        )
        artifacts = {**artifacts, "closure_result": self._artifact_descriptor(result_path)}
        active_space = context["active_space"]
        region = context["region"]
        hamiltonian = context["hamiltonian"]
        benchmark = context["benchmark"]
        candidate = context["candidate"]
        record = self.repository.create_quantum_closure_benchmark(
            {
                "closure_benchmark_id": closure_id,
                "owner_user_id": context["workflow"].owner_user_id,
                "research_benchmark_id": benchmark.benchmark_id,
                "research_candidate_id": candidate.candidate_id,
                "workflow_id": context["workflow"].workflow_id,
                "quantum_region_id": region.quantum_region_id,
                "active_space_id": active_space.active_space_id,
                "fermionic_hamiltonian_id": hamiltonian.hamiltonian_id,
                "qubit_hamiltonian_id": qubit_hamiltonian.qubit_hamiltonian_id,
                "classical_reference_id": classical_reference.reference_id,
                "vqe_execution_id": vqe_execution.execution_id if vqe_execution is not None else None,
                "source_candidate_sha256": context["source_candidate_sha256"],
                "fermionic_hamiltonian_sha256": hamiltonian.artifact_hash,
                "pauli_hamiltonian_sha256": artifacts["pauli_hamiltonian"]["sha256"],
                "mapping_method": qubit_hamiltonian.mapping_method,
                "qubit_count": qubit_hamiltonian.qubit_count,
                "active_electrons": active_space.active_electrons,
                "active_orbitals": active_space.active_orbitals,
                "spin_multiplicity": region.spin_multiplicity,
                "basis_set": hamiltonian.basis_set,
                "fci_energy_hartree": fci_energy,
                "exact_pauli_energy_hartree": exact_energy,
                "vqe_energy_hartree": vqe_energy,
                "mapping_error_hartree": mapping_error,
                "vqe_error_hartree": vqe_error,
                "mapping_tolerance_hartree": request["mapping_tolerance_hartree"],
                "vqe_target_tolerance_hartree": request["vqe_target_tolerance_hartree"],
                "status": status,
                "result_qualification": qualification,
                "failure_code": failure_code,
                "artifact_manifest": artifacts,
                "completed_at": datetime.utcnow(),
            }
        )
        self._set_workflow_status(
            context["workflow"].workflow_id,
            record.owner_user_id,
            "completed" if status == "benchmark_validated_simulator_vqe" else "needs_model_review",
            "quantum_closure_benchmark_completed",
            {
                "closure_benchmark_id": record.closure_benchmark_id,
                "status": status,
                "result_qualification": qualification,
                "failure_code": failure_code,
            },
        )
        return self._serialize_quantum_closure_benchmark(record)

    @staticmethod
    def _artifact_descriptor(path: Path) -> dict:
        return {
            "artifact_id": path.stem,
            "filename": path.name,
            "sha256": StructureModelingService._hash_file(path, "sha256"),
        }

    def _write_quantum_closure_artifact(
        self,
        artifact_id: str,
        payload: dict,
        upstream_object_ids: dict[str, str | None],
        exception: str | None = None,
    ) -> Path:
        """Write a closure Artifact with stable provenance metadata before hashing it into the manifest."""
        return self._write_json_artifact(
            artifact_id,
            {
                "artifact_metadata": {
                    "generator": "backend.quantum_closure_benchmark",
                    "software_version": "3.0.0",
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "upstream_object_ids": upstream_object_ids,
                    "exception": exception,
                },
                **payload,
            },
        )

    @staticmethod
    def _serialize_quantum_closure_benchmark(record) -> dict:
        return {
            "closure_benchmark_id": record.closure_benchmark_id,
            "research_benchmark_id": record.research_benchmark_id,
            "research_candidate_id": record.research_candidate_id,
            "workflow_id": record.workflow_id,
            "quantum_region_id": record.quantum_region_id,
            "active_space_id": record.active_space_id,
            "fermionic_hamiltonian_id": record.fermionic_hamiltonian_id,
            "qubit_hamiltonian_id": record.qubit_hamiltonian_id,
            "classical_reference_id": record.classical_reference_id,
            "vqe_execution_id": record.vqe_execution_id,
            "E_FCI_hartree": record.fci_energy_hartree,
            "E_exact_pauli_hartree": record.exact_pauli_energy_hartree,
            "E_VQE_hartree": record.vqe_energy_hartree,
            "mapping_error_hartree": record.mapping_error_hartree,
            "vqe_error_hartree": record.vqe_error_hartree,
            "mapping_tolerance_hartree": record.mapping_tolerance_hartree,
            "vqe_target_tolerance_hartree": record.vqe_target_tolerance_hartree,
            "mapping_method": record.mapping_method,
            "qubit_count": record.qubit_count,
            "active_electrons": record.active_electrons,
            "active_orbitals": record.active_orbitals,
            "spin_multiplicity": record.spin_multiplicity,
            "basis_set": record.basis_set,
            "execution_backend_type": "simulator",
            "energy_uncertainty_method": "statevector_exact_no_shot_sampling",
            "status": record.status,
            "result_qualification": record.result_qualification,
            "failure_code": record.failure_code,
            "artifacts": record.artifact_manifest or {},
            "created_at": record.created_at.isoformat(),
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

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
            input_purpose="legacy_screening",
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
        task_id = task_manager.submit_cancellable(
            self._run_direct_dft_calculation,
            calculation_id,
            owner_user_id,
            task_owner_user_id=owner_user_id,
        )
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
        task_id = task_manager.submit_cancellable(
            self._run_direct_dft_calculation,
            dft_calculation_id,
            owner_user_id,
            task_owner_user_id=owner_user_id,
        )
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

    def _generate_electronic_structure_candidates(
        self,
        quantum_region_id: str,
        owner_user_id: int,
        request: dict,
        timeout_seconds: int = BACKGROUND_ELECTRONIC_STRUCTURE_TIMEOUT_SECONDS,
        stop_after_resource_timeout: bool = False,
        execution_options: dict | None = None,
    ) -> dict:
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
                    adapter_options = {"timeout_seconds": timeout_seconds}
                    if execution_options is not None:
                        adapter_options["execution_options"] = execution_options
                    result = self.electronic_structure_adapter.generate_active_space_candidates(
                        {
                            "atomic_sites": atomic_sites,
                            "total_charge": total_charge,
                            "spin_multiplicity": spin_multiplicity,
                            "basis_set": request["basis_set"],
                            "requested_methods": request["requested_methods"],
                            "max_scf_attempts": request["max_scf_attempts"],
                            "spin_contamination_threshold": request["spin_contamination_threshold"],
                            "include_active_space_candidates": request.get("include_active_space_candidates", True),
                            "resource_calibration_only": request.get("resource_calibration_only", False),
                            "expected_checkpoint_metadata": request.get("expected_checkpoint_metadata"),
                            "scf_options": request.get("scf_options", {}),
                        },
                        **adapter_options,
                    )
                except ElectronicStructureRuntimeError as exc:
                    result = {
                        "status": "failed",
                        "message": f"PySCF 运行失败：{exc}",
                        "basis_set": request["basis_set"],
                        "scf_attempts": [],
                        "diagnostic": exc.diagnostic,
                    }
                artifact_path = self._write_json_artifact(self._new_id("electronic_structure"), result)
                contamination = result.get("spin_contamination")
                is_converged, exceeds_threshold, quality_status = self._electronic_structure_result_quality(
                    result,
                    request["spin_contamination_threshold"],
                )
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
                if stop_after_resource_timeout and "timed out" in str(result.get("message", "")).lower():
                    return {
                        "quantum_region_id": quantum_region_id,
                        "status": "needs_model_review",
                        "candidate_count": len(candidates),
                        "eligible_candidate_count": len(
                            [candidate for candidate in candidates if candidate["quality_status"] == "eligible_for_confirmation"]
                        ),
                        "candidates": candidates,
                        "stopped_for_resource_timeout": True,
                    }
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
            task_owner_user_id=owner_user_id,
        )
        return {"task_id": task_id, "status": "queued", "message": "电子结构计算已提交后台执行。"}

    @staticmethod
    def get_background_task(task_id: str, owner_user_id: int) -> dict:
        status = task_manager.get_status(task_id, owner_user_id)
        if status is None:
            raise StructureModelingError("task_not_found", "未找到后台任务。", 404)
        return {"task_id": task_id, "status": status["status"], "progress": status["progress"], "message": status["message"], "result": task_manager.get_result(task_id) if status["status"] == "completed" else None}

    def confirm_active_space(self, quantum_region_id: str, active_space_id: str, owner_user_id: int) -> dict:
        record = self.repository.get_active_space(active_space_id, owner_user_id)
        if record is None or record.quantum_region_id != quantum_region_id:
            raise StructureModelingError("active_space_not_found", "未找到活性空间候选或无权访问。", 404)
        self._assert_not_preconditioner_only(record.orbital_metadata or {})
        if record.status == "needs_model_review":
            raise StructureModelingError("active_space_needs_review", "该活性空间存在自旋污染或资源限制，需人工复核后才能确认。", 409)
        confirmed = self.repository.update_active_space(active_space_id, owner_user_id, status="confirmed")
        return self.serialize_active_space(confirmed)

    def build_fermionic_hamiltonian(self, active_space_id: str, owner_user_id: int) -> dict:
        active_space = self.repository.get_active_space(active_space_id, owner_user_id)
        if active_space is None or active_space.status != "confirmed":
            raise StructureModelingError("active_space_not_confirmed", "请先确认活性空间。", 409)
        self._assert_not_preconditioner_only(active_space.orbital_metadata or {})
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
                "result_qualification": "exploratory_simulator_vqe",
                "qualification_note": "普通 VQE 执行未进行同一 Pauli Hamiltonian 的精确对角化和闭环阈值验收。",
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
        return {"file_id": record.file_id, "material_name": record.material_name, "material_family": record.material_family, "description": record.description, "original_filename": record.original_filename, "file_type": record.file_type, "input_purpose": record.input_purpose, "file_size_bytes": record.file_size_bytes, "file_hash": record.file_hash, "parse_status": record.parse_status, "parse_error": {"code": record.parse_error_code, "message": record.parse_error_message} if record.parse_error_code else None, "structure_id": record.structure_id, "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat()}

    def serialize_parse_result(self, file_record, structure) -> dict:
        is_molecular = file_record.input_purpose == "molecular_logical_circuit"
        eligible = (
            is_molecular
            and file_record.file_type == "xyz"
            and structure.dimensionality == "non_periodic"
            and structure.validation_status in {"valid", "valid_with_warnings"}
            and 1 <= structure.atom_count <= 32
        )
        reasons: list[str] = []
        if is_molecular and not eligible:
            if file_record.file_type != "xyz":
                reasons.append("molecular_source_format_not_eligible")
            if structure.dimensionality != "non_periodic":
                reasons.append("molecular_periodic_structure_not_supported")
            if not 1 <= structure.atom_count <= 32:
                reasons.append("invalid_atom_count")
            if structure.validation_status not in {"valid", "valid_with_warnings"}:
                reasons.append("structure_validation_failed")
        return {"file_id": file_record.file_id, "structure_id": structure.structure_id, "workflow_id": structure.workflow_id, "parse_status": file_record.parse_status, "validation_status": structure.validation_status, "formula": structure.formula, "elements": structure.elements, "atom_count": structure.atom_count, "structure_type": structure.structure_type, "warnings": structure.parse_warnings + structure.validation_warnings, "molecular_model_creation_eligible": eligible, "molecular_model_creation_eligibility_reasons": reasons}

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
        return {"quantum_region_id": region.quantum_region_id, "adsorption_model_id": region.adsorption_model_id, "region_atom_indices": region.region_atom_indices, "frozen_environment_atom_indices": region.frozen_environment_atom_indices, "embedding_method": region.embedding_method, "total_charge": region.total_charge, "spin_multiplicity": region.spin_multiplicity, "geometry_source_type": region.geometry_source_type, "geometry_method": region.geometry_method, "geometry_artifact_id": Path(region.geometry_artifact_path).stem, "preflight_artifact_id": Path(region.preflight_artifact_path).stem if region.preflight_artifact_path else None, "status": region.status, "warnings": region.warnings}

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
        vqe_objects.extend(
            self._stage_object(
                "quantum_closure_benchmark",
                record.closure_benchmark_id,
                record.fermionic_hamiltonian_id,
                record.status,
            )
            for record in resources.get("quantum_closure_benchmarks", [])
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
            ("quantum_closure_benchmark", "closure_benchmark_id", resources.get("quantum_closure_benchmarks", [])),
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
            add(record, record.preflight_artifact_path, "h_capped_scf_preflight", "quantum_region", record.quantum_region_id, "quantum_region")
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
        for record in resources.get("quantum_closure_benchmarks", []):
            for artifact_role, artifact in (record.artifact_manifest or {}).items():
                artifact_id = artifact.get("artifact_id")
                if not artifact_id:
                    continue
                add(
                    record,
                    str(STRUCTURE_ARTIFACT_ROOT / f"{artifact_id}.json"),
                    artifact_role,
                    "quantum_closure_benchmark",
                    record.closure_benchmark_id,
                    "vqe",
                    artifact_id=artifact_id,
                    filename=artifact.get("filename"),
                )
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
