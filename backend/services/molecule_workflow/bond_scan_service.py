from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.models_db import (
    DeploymentEvaluationRecord,
    MolecularBondScanPointRecord,
    MolecularBondScanRecord,
    MolecularProblemRecord,
)
from backend.services.electronic_structure.docker_adapter import ElectronicStructureRuntimeError

from .service import MoleculeWorkflowError, MoleculeWorkflowService
from .study_service import MolecularStudyService


class MolecularBondScanService:
    """Persist and execute a deterministic LiH bond scan point by point."""

    def __init__(self, session: Session, workflow_service: MoleculeWorkflowService) -> None:
        self.session = session
        self.workflow_service = workflow_service

    def submit(self, request: dict[str, Any], user_id: int, idempotency_key: str | None) -> dict[str, Any]:
        if idempotency_key:
            existing = self.session.query(MolecularBondScanRecord).filter_by(user_id=user_id, idempotency_key=idempotency_key).one_or_none()
            if existing:
                if existing.request_json != request:
                    raise MoleculeWorkflowError("idempotency_key_conflict", "Idempotency-Key is already associated with a different request.", "input_validation", 409)
                return self._response(existing)
        scan_id = f"bondscan_{uuid.uuid4().hex}"
        distances = self._distances(request["scan"])
        record = MolecularBondScanRecord(
            scan_id=scan_id, user_id=user_id, idempotency_key=idempotency_key, request_json=request,
            status="queued", current_stage="input_validation",
        )
        self.session.add(record)
        self.session.add_all(
            MolecularBondScanPointRecord(
                point_id=f"bondpoint_{uuid.uuid4().hex}", scan_id=scan_id, point_index=index,
                distance_angstrom=distance, status="queued",
            )
            for index, distance in enumerate(distances)
        )
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if idempotency_key:
                existing = self.session.query(MolecularBondScanRecord).filter_by(
                    user_id=user_id, idempotency_key=idempotency_key
                ).one_or_none()
                if existing is not None:
                    if existing.request_json == request:
                        return self._response(existing)
                    raise MoleculeWorkflowError(
                        "idempotency_key_conflict",
                        "Idempotency-Key is already associated with a different request.",
                        "input_validation",
                        409,
                    ) from exc
            raise MoleculeWorkflowError("bond_scan_persistence_failed", "Could not persist the bond scan request.", "input_validation", 503) from exc
        return self._response(record)

    def execute(self, scan_id: str, user_id: int) -> None:
        scan = self._scan(scan_id, user_id)
        scan.status, scan.current_stage, scan.started_at = "running", "scan_point_generation", datetime.now(timezone.utc)
        self.session.commit()
        request = scan.request_json
        points = self._points(scan_id)
        try:
            scan.current_stage = "point_calculations"
            self.session.commit()
            for point in points:
                if point.status in {"completed", "failed"}:
                    continue
                self._execute_point(scan, point, request)
            scan.current_stage = "minimum_selection"
            result = self._result(scan)
            self._annotate_minimum_consistency(points, result)
            result = self._result(scan)
            # Formally deploy only a scientifically validated minimum. An
            # optimizer-valid fallback is retained as explicitly labelled
            # engineering-only deployment evidence.
            minimum = result["scientific_vqe_discrete_minimum"] or result["vqe_discrete_minimum"]
            if minimum:
                scan.current_stage = "deployment_evaluation"
                selected_record = next(point for point in points if point.point_index == minimum["point_index"])
                workflow_id = (selected_record.result_json or {}).get("_workflow_id")
                if not workflow_id:
                    raise MoleculeWorkflowError("selected_point_workflow_missing", "The selected point has no reusable workflow result.", "deployment_evaluation", 503)
                selected_workflow = self.workflow_service.get(workflow_id, scan.user_id)
                result["deployment_reference_point_index"] = selected_record.point_index
                result["deployment_result"] = self._evaluate_deployments(selected_workflow, request["deployment_architectures"])
                if result["engineering_only_deployment"]:
                    result["summary"]["issues"].append(
                        "Deployment evidence uses an optimizer-valid point because no scientifically validated VQE minimum is available."
                    )
            else:
                result["summary"]["issues"].append("No VQE point passed validation; deployment evaluation was not run.")
            completed = sum(point.status == "completed" for point in points)
            if completed == 0:
                raise MoleculeWorkflowError("all_scan_points_failed", "All LiH scan points failed.", "point_calculations", 503)
            failed = [point for point in points if point.status == "failed"]
            if failed:
                result["summary"]["issues"].append(
                    f"{len(failed)} scan point(s) failed; completed points and any deployment result were retained."
                )
            scan.status, scan.current_stage, scan.result_json, scan.completed_at = "completed", "completed", result, datetime.now(timezone.utc)
            self.session.commit()
        except Exception as exc:
            # Retain point-level evidence even when aggregation or a later
            # deployment attempt fails; the original point failure must not
            # discard completed scientific/engineering results.
            try:
                partial = self._result(scan)
            except Exception:
                partial = self._partial_result(self._points(scan.scan_id))
            scan.status, scan.current_stage, scan.completed_at = "failed", "failed", datetime.now(timezone.utc)
            scan.result_json = partial
            scan.error_json = self._error(scan, None, None, "bond_scan_failed", str(exc), scan.current_stage)
            self.session.commit()

    def get(self, scan_id: str, user_id: int) -> dict[str, Any] | None:
        scan = self.session.query(MolecularBondScanRecord).filter_by(scan_id=scan_id, user_id=user_id).one_or_none()
        return self._response(scan) if scan else None

    @staticmethod
    def _distances(options: dict[str, Any]) -> list[float]:
        count = int(options["point_count"])
        start, end = float(options["start_distance_angstrom"]), float(options["end_distance_angstrom"])
        return [round(start + (end - start) * index / (count - 1), 12) for index in range(count)]

    def _execute_point(self, scan: MolecularBondScanRecord, point: MolecularBondScanPointRecord, request: dict[str, Any]) -> None:
        point.status, point.started_at = "running", datetime.now(timezone.utc)
        if point.molecular_problem_id is None:
            point.molecular_problem_id = f"mprob_scan_{uuid.uuid4().hex}"
            self.session.add(MolecularProblemRecord(
                problem_id=point.molecular_problem_id,
                user_id=scan.user_id,
                molecule_name="LiH",
                status="running",
                request_json={"molecule_type": "LiH", "distance_angstrom": point.distance_angstrom},
            ))
        self.session.commit()
        chemistry = request["chemistry"]
        workflow_request = {
            "molecule_name": "LiH",
            "geometry": [
                {"element": "Li", "coordinates_angstrom": [0.0, 0.0, 0.0]},
                {"element": "H", "coordinates_angstrom": [0.0, 0.0, point.distance_angstrom]},
            ],
            "charge": chemistry["charge"], "spin_multiplicity": chemistry["spin_multiplicity"],
            "basis_set": chemistry["basis_set"], "mapping_method": "jordan_wigner",
            "active_space_orbitals": chemistry["active_space_orbitals"],
            "pauli_coefficient_cutoff": chemistry["pauli_coefficient_cutoff"], "vqe": chemistry["vqe"],
            "partition": request["deployment_architectures"][0]["partition"], "execution_mode": "logical_virtual_qpu",
        }
        try:
            workflow = self.workflow_service.execute(workflow_request, scan.user_id, wait_for_compute_slot=True)
            fci_reference = workflow.get("fci_reference") or self._fci_reference(workflow, workflow_request)
            validation_status = (workflow.get("scientific_validation") or {}).get("status", workflow["validation_status"])
            point_result = self._point_result(point, workflow, fci_reference)
            point.status, point.validation_status, point.result_json, point.completed_at = "completed", validation_status, point_result, datetime.now(timezone.utc)
            problem = self.session.get(MolecularProblemRecord, point.molecular_problem_id)
            if problem is not None:
                problem.status = "completed"
                problem.result_json = point_result
        except MoleculeWorkflowError as exc:
            point.status, point.error_json, point.completed_at = "failed", self._error(
                scan, point, point.molecular_problem_id, exc.code, exc.message, exc.stage
            ), datetime.now(timezone.utc)
            problem = self.session.get(MolecularProblemRecord, point.molecular_problem_id)
            if problem is not None:
                problem.status = "failed"
                problem.error_json = point.error_json
        except Exception as exc:
            point.status, point.error_json, point.completed_at = "failed", self._error(
                scan, point, point.molecular_problem_id, "scan_point_failed", str(exc), "point_calculations"
            ), datetime.now(timezone.utc)
            problem = self.session.get(MolecularProblemRecord, point.molecular_problem_id)
            if problem is not None:
                problem.status = "failed"
                problem.error_json = point.error_json
        self.session.commit()

    def _fci_reference(self, workflow: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        try:
            active = workflow["active_space"]
            atomic_sites = [{"element": item["element"], "position_angstrom": item["coordinates_angstrom"]} for item in request["geometry"]]
            result = self.workflow_service.electronic_structure_adapter.calculate_classical_reference({
                "atomic_sites": atomic_sites, "total_charge": request["charge"], "spin_multiplicity": request["spin_multiplicity"],
                "basis_set": request["basis_set"], "orbital_indices": active["orbital_indices"], "active_electrons": active["active_electrons"],
            })
            if result.get("status") == "completed":
                return {"status": "available", "method": result.get("method"), "energy_hartree": result.get("energy_hartree"), "message": None}
            return {"status": "unavailable", "method": result.get("method"), "energy_hartree": None, "message": result.get("message")}
        except (AttributeError, ElectronicStructureRuntimeError, KeyError):
            return {"status": "unavailable", "method": None, "energy_hartree": None, "message": "FCI reference runtime is unavailable."}

    def _point_result(self, point: MolecularBondScanPointRecord, workflow: dict[str, Any], fci: dict[str, Any]) -> dict[str, Any]:
        vqe_energy = workflow["energies"]["unpartitioned_benchmark_energy_hartree"]
        return {
            "point_index": point.point_index, "distance_angstrom": point.distance_angstrom, "status": "completed",
            "validation_status": workflow["validation_status"], "validation_issues": workflow["validation_issues"],
            "optimizer_validation": workflow.get("optimizer_validation"),
            "scientific_validation": workflow.get("scientific_validation"),
            "deployment_validation": workflow.get("deployment_validation"),
            "molecular_problem_id": point.molecular_problem_id, "hf_energy_hartree": workflow["hf_energy_hartree"],
            "vqe_energy_hartree": vqe_energy, "vqe_converged": workflow["vqe"]["converged"],
            "optimizer_diagnostics": workflow["vqe"]["optimizer_diagnostics"], "fci_reference": fci,
            "vqe_fci_scientific_error_hartree": (workflow.get("scientific_validation") or {}).get("vqe_fci_error_hartree", abs(vqe_energy - fci["energy_hartree"]) if fci["energy_hartree"] is not None else None),
            "qubit_count": workflow["hamiltonian"]["qubit_count"], "pauli_term_count": workflow["hamiltonian"]["pauli_term_count"],
            "qasm": workflow["vqe"]["qasm"], "stages": workflow["stages"], "error": None,
            "_workflow_id": workflow["workflow_id"],
        }

    def _evaluate_deployments(self, workflow: dict[str, Any], architectures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evaluator = MolecularStudyService(self.session, self.workflow_service)
        results = []
        for architecture in architectures:
            record = DeploymentEvaluationRecord(
                evaluation_id=f"deval_scan_{uuid.uuid4().hex}", study_id=f"scan_deploy_{uuid.uuid4().hex}",
                architecture_id=architecture["architecture_id"], status="running", request_json=architecture,
            )
            results.append(evaluator._evaluate_architecture(workflow, record, architecture))
        return results

    def _result(self, scan: MolecularBondScanRecord) -> dict[str, Any]:
        points = [self._point_response(point) for point in self._points(scan.scan_id)]
        hf_minimum = self._minimum(points, "hf_energy_hartree", eligible=lambda point: point["status"] == "completed")
        vqe_minimum = self._minimum(points, "vqe_energy_hartree", eligible=lambda point: point.get("validation_status") == "passed")
        scientific_vqe_minimum = self._minimum(
            points,
            "vqe_energy_hartree",
            eligible=lambda point: (point.get("scientific_validation") or {}).get("status") == "passed",
        )
        fci_minimum = self._minimum(points, "fci_reference.energy_hartree", eligible=lambda point: point.get("fci_reference", {}).get("energy_hartree") is not None)
        return {
            "points": points,
            "hf_discrete_minimum": hf_minimum,
            "vqe_discrete_minimum": vqe_minimum,
            "scientific_vqe_discrete_minimum": scientific_vqe_minimum,
            # This conclusion becomes knowable only after a deployment target
            # has been selected. In particular, an all-failed scan has neither
            # scientific nor engineering deployment evidence.
            "engineering_only_deployment": (
                scientific_vqe_minimum is None and vqe_minimum is not None
                if vqe_minimum is not None
                else None
            ),
            "fci_discrete_minimum": fci_minimum,
            "deployment_reference_point_index": None, "deployment_study_id": None, "deployment_result": None,
            "summary": {
                "issues": [],
                "minimum_at_boundary": any(item and item["minimum_at_boundary"] for item in (hf_minimum, vqe_minimum, scientific_vqe_minimum, fci_minimum)),
            },
        }

    @staticmethod
    def _minimum(points: list[dict[str, Any]], field: str, eligible) -> dict[str, Any] | None:
        candidates = [point for point in points if eligible(point)]
        if not candidates:
            return None
        def energy(point):
            value: Any = point
            for component in field.split("."):
                value = value[component]
            return value
        best = min(candidates, key=energy)
        boundary = best["point_index"] in {points[0]["point_index"], points[-1]["point_index"]}
        return {"point_index": best["point_index"], "distance_angstrom": best["distance_angstrom"], "energy_hartree": energy(best), "minimum_at_boundary": boundary, "message": "Discrete scan minimum is at the scan boundary; the range may not bracket the true minimum." if boundary else None}

    def _annotate_minimum_consistency(self, points: list[MolecularBondScanPointRecord], result: dict[str, Any]) -> None:
        """Persist whether the scientific VQE and FCI discrete minima agree."""
        vqe_minimum = result.get("scientific_vqe_discrete_minimum")
        fci_minimum = result.get("fci_discrete_minimum")
        if vqe_minimum is None or fci_minimum is None:
            status = "needs_review"
            message = "A scientifically validated VQE or FCI discrete minimum is unavailable."
        elif vqe_minimum["point_index"] == fci_minimum["point_index"]:
            status, message = "passed", None
        else:
            status, message = "needs_review", "The scientifically validated VQE and FCI discrete minima occur at different scan points."
        for point in points:
            payload = dict(point.result_json or {})
            if not payload or not payload.get("scientific_validation"):
                continue
            scientific_validation = dict(payload["scientific_validation"])
            scientific_validation["minimum_consistency_status"] = status
            if message is not None:
                scientific_validation["issues"] = [*scientific_validation.get("issues", []), {"code": "minimum_consistency_needs_review", "message": message}]
            payload["scientific_validation"] = scientific_validation
            point.result_json = payload
            flag_modified(point, "result_json")
        self.session.commit()

    def _response(self, scan: MolecularBondScanRecord) -> dict[str, Any]:
        points = self._points(scan.scan_id)
        result = dict(scan.result_json) if scan.result_json is not None else self._partial_result(points)
        if "engineering_only_deployment" not in result:
            # Neither a partial result nor an older persisted terminal result
            # establishes a deployment-selection conclusion.
            result["engineering_only_deployment"] = None
        if scan.status in {"completed", "failed"} and "engineering_only_deployment" not in (scan.result_json or {}):
            # A terminal pre-P1.2 record cannot establish whether deployment
            # was engineering-only. Preserve that unknown instead of emitting
            # a misleading false boolean.
            summary = dict(result.get("summary") or {})
            if "legacy_result_missing_release_fields" not in summary.get("issues", []):
                summary["issues"] = [*summary.get("issues", []), "legacy_result_missing_release_fields"]
            result["summary"] = summary
        counts = {status: sum(point.status == status for point in points) for status in ("queued", "running", "completed", "failed")}
        return {
            "scan_id": scan.scan_id, "molecule_type": "LiH", "status": scan.status, "current_stage": scan.current_stage,
            "execution_mode": "logical_virtual_qpu", "is_real_qpu": False,
            "created_at": scan.created_at.isoformat(), "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
            "total_point_count": len(points), "queued_point_count": counts["queued"], "running_point_count": counts["running"],
            "completed_point_count": counts["completed"], "failed_point_count": counts["failed"],
            "needs_review_point_count": sum(point.validation_status == "needs_review" for point in points),
            "current_point_index": next((point.point_index for point in points if point.status == "running"), None),
            "result": result, "error": scan.error_json,
        }

    def _partial_result(self, points: list[MolecularBondScanPointRecord]) -> dict[str, Any]:
        return {"points": [self._point_response(point) for point in points], "hf_discrete_minimum": None, "vqe_discrete_minimum": None, "scientific_vqe_discrete_minimum": None, "engineering_only_deployment": None, "fci_discrete_minimum": None, "deployment_reference_point_index": None, "deployment_study_id": None, "deployment_result": None, "summary": {"issues": [], "minimum_at_boundary": False}}

    @staticmethod
    def _point_response(point: MolecularBondScanPointRecord) -> dict[str, Any]:
        if point.result_json:
            return {key: value for key, value in point.result_json.items() if not key.startswith("_")}
        return {"point_index": point.point_index, "distance_angstrom": point.distance_angstrom, "status": point.status, "validation_status": point.validation_status, "validation_issues": [], "optimizer_validation": None, "scientific_validation": None, "deployment_validation": None, "molecular_problem_id": point.molecular_problem_id, "hf_energy_hartree": None, "vqe_energy_hartree": None, "vqe_converged": None, "optimizer_diagnostics": None, "fci_reference": {"status": "not_configured", "method": None, "energy_hartree": None, "message": "Point has not reached FCI evaluation."}, "vqe_fci_scientific_error_hartree": None, "qubit_count": None, "pauli_term_count": None, "qasm": None, "stages": [], "error": point.error_json}

    def _points(self, scan_id: str) -> list[MolecularBondScanPointRecord]:
        return self.session.query(MolecularBondScanPointRecord).filter_by(scan_id=scan_id).order_by(MolecularBondScanPointRecord.point_index).all()

    def _scan(self, scan_id: str, user_id: int) -> MolecularBondScanRecord:
        scan = self.session.query(MolecularBondScanRecord).filter_by(scan_id=scan_id, user_id=user_id).one_or_none()
        if scan is None:
            raise MoleculeWorkflowError("molecular_bond_scan_not_found", "Bond scan not found.", "lookup", 404)
        return scan

    @staticmethod
    def _error(scan, point, molecular_problem_id, code, message, stage):
        return {
            "code": code,
            "message": message,
            "stage": stage,
            "scan_id": scan.scan_id,
            "point_index": point.point_index if point else None,
            "molecular_problem_id": molecular_problem_id,
        }
