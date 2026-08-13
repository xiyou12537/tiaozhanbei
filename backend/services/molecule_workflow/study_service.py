from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models_db import DeploymentEvaluationRecord, DeploymentStudyRecord, MolecularProblemRecord

from .service import MoleculeWorkflowError, MoleculeWorkflowService


class MolecularStudyService:
    """Run one molecular calculation and evaluate several deployment targets."""

    def __init__(self, session: Session, workflow_service: MoleculeWorkflowService) -> None:
        self.session = session
        self.workflow_service = workflow_service

    def submit(self, request: dict[str, Any], user_id: int) -> dict[str, Any]:
        study_id, molecular_problem_id = f"study_{uuid.uuid4().hex}", f"mprob_{uuid.uuid4().hex}"
        evaluation_records = [
            DeploymentEvaluationRecord(
                evaluation_id=f"deval_{uuid.uuid4().hex}",
                study_id=study_id,
                architecture_id=architecture["architecture_id"],
                status="queued",
                request_json=architecture,
            )
            for architecture in request["architectures"]
        ]
        skeleton = self._result_skeleton(molecular_problem_id, evaluation_records, request["architectures"])
        self.session.add(MolecularProblemRecord(
            problem_id=molecular_problem_id,
            user_id=user_id,
            molecule_name=request["molecule_name"],
            status="queued",
            request_json=request,
            result_json=skeleton["molecular_problem"],
        ))
        study = DeploymentStudyRecord(
            study_id=study_id,
            user_id=user_id,
            problem_id=molecular_problem_id,
            status="queued",
            request_json=request,
            result_json=self._with_lifecycle(skeleton, current_stage="queued"),
        )
        self.session.add(study)
        self.session.add_all(evaluation_records)
        self.session.commit()
        return self._response(study)

    def execute(self, study_id: str, user_id: int) -> None:
        study = self._study(study_id, user_id)
        problem = self.session.get(MolecularProblemRecord, study.problem_id)
        if problem is None:
            return
        study.status = problem.status = "running"
        partial_result = self._result_without_lifecycle(study.result_json)
        if partial_result is not None:
            partial_result["molecular_problem"]["status"] = "running"
            self._set_result(study, partial_result)
        self._update_lifecycle(study, current_stage="molecular_problem", started_at=self._now())
        self.session.commit()
        try:
            request = dict(study.request_json)
            architectures = request.pop("architectures")
            # The common PySCF/Hamiltonian/VQE path is deliberately called once.
            request["partition"] = architectures[0]["partition"]
            base = self.workflow_service.execute(request, user_id, wait_for_compute_slot=True)
            problem.status = "completed"
            problem.result_json = self._problem_result(problem.problem_id, base)
            self._replace_result(study, molecular_problem=problem.result_json, current_stage="deployment_evaluation")
            self.session.commit()

            for architecture in architectures:
                record = self.session.query(DeploymentEvaluationRecord).filter_by(
                    study_id=study_id, architecture_id=architecture["architecture_id"]
                ).one()
                record.status = "running"
                self._replace_evaluation(study, self._evaluation_skeleton(record, architecture, status="running"))
                self.session.commit()

                outcome = self._evaluate_architecture(base, record, architecture)
                record.status = outcome["status"]
                record.result_json = outcome
                record.error_json = outcome.get("failure_reason")
                self._replace_evaluation(study, outcome)
                self.session.commit()

            study.status = "completed"
            self._update_lifecycle(study, current_stage="completed", completed_at=self._now())
            self.session.commit()
        except Exception as exc:
            problem.status = study.status = "failed"
            error = self._error(
                "molecular_study_failed", str(exc), "molecular_problem", study, problem.problem_id
            )
            problem.error_json = error
            study.error_json = error
            current_result = self._result_without_lifecycle(study.result_json)
            if current_result:
                current_result["molecular_problem"]["status"] = "failed"
            self._set_result(study, current_result or self._result_skeleton(problem.problem_id, [], []))
            self._update_lifecycle(study, current_stage="failed", completed_at=self._now())
            self.session.commit()

    def get(self, study_id: str, user_id: int) -> dict[str, Any] | None:
        study = self.session.query(DeploymentStudyRecord).filter_by(study_id=study_id, user_id=user_id).one_or_none()
        return self._response(study) if study is not None else None

    def _study(self, study_id: str, user_id: int) -> DeploymentStudyRecord:
        study = self.session.query(DeploymentStudyRecord).filter_by(study_id=study_id, user_id=user_id).one_or_none()
        if study is None:
            raise MoleculeWorkflowError("molecular_study_not_found", "Study not found.", "lookup", 404, study_id)
        return study

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _response(self, study: DeploymentStudyRecord) -> dict[str, Any]:
        result = self._normalise_result(study)
        lifecycle = (study.result_json or {}).get("_lifecycle", {})
        summary = (result or {}).get("summary", {})
        error = study.error_json
        if error is not None:
            error = {
                "code": error.get("code", "molecular_study_failed"),
                "message": error.get("message", "Molecular study failed."),
                "stage": error.get("stage"),
                "study_id": error.get("study_id", study.study_id),
                "molecular_problem_id": error.get("molecular_problem_id", study.problem_id),
                "architecture_id": error.get("architecture_id"),
            }
        return {
            "study_id": study.study_id,
            "molecular_problem_id": study.problem_id,
            # Deprecated compatibility alias for pre-P0.1.1 consumers.
            "problem_id": study.problem_id,
            "status": study.status,
            "current_stage": lifecycle.get("current_stage", study.status),
            "created_at": self._timestamp(study.created_at),
            "started_at": lifecycle.get("started_at"),
            "completed_at": lifecycle.get("completed_at"),
            "completed_evaluation_count": summary.get("completed_evaluation_count", 0),
            "total_evaluation_count": summary.get("total_evaluation_count", 0),
            "result": result,
            "error": error,
        }

    def _normalise_result(self, study: DeploymentStudyRecord) -> dict[str, Any] | None:
        """Read pre-P0.1.1 records without exposing an untyped legacy shape."""
        raw_result = self._result_without_lifecycle(study.result_json)
        records = self.session.query(DeploymentEvaluationRecord).filter_by(study_id=study.study_id).all()
        architectures = list(study.request_json.get("architectures", []))
        architecture_by_id = {item["architecture_id"]: item for item in architectures}
        if raw_result is None:
            return self._result_skeleton(study.problem_id, records, architectures)

        raw_problem = raw_result.get("molecular_problem") or {}
        if "molecular_problem_id" in raw_problem:
            problem = raw_problem
        else:
            problem = self._problem_skeleton(study.problem_id, raw_problem.get("status", study.status))
            problem.update({
                key: raw_problem[key]
                for key in ("stages", "molecule", "hf_energy_hartree", "active_space", "hamiltonian")
                if key in raw_problem
            })
            if raw_problem.get("vqe") is not None:
                problem["vqe"] = {
                    **raw_problem["vqe"],
                    "unpartitioned_energy_hartree": raw_problem.get("unpartitioned_vqe_energy_hartree"),
                }
            raw_fci = raw_problem.get("fci_reference")
            if raw_fci:
                problem["fci_reference"] = {
                    "status": "available" if raw_fci.get("available") else "not_configured",
                    "method": raw_fci.get("method"),
                    "energy_hartree": raw_fci.get("energy_hartree"),
                    "message": raw_fci.get("message") or raw_fci.get("reason"),
                }
            problem["vqe_fci_scientific_error_hartree"] = raw_problem.get("vqe_fci_scientific_error_hartree")

        raw_evaluations = {item.get("architecture_id"): item for item in raw_result.get("deployment_evaluations", [])}
        evaluations = []
        for record in records:
            architecture = architecture_by_id.get(record.architecture_id, record.request_json)
            legacy = raw_evaluations.get(record.architecture_id) or record.result_json
            evaluations.append(self._normalise_evaluation(record, architecture, legacy))
        return {
            "molecular_problem": problem,
            "deployment_evaluations": evaluations,
            "summary": self._summary(evaluations),
        }

    def _normalise_evaluation(
        self, record: DeploymentEvaluationRecord, architecture: dict[str, Any], raw: dict[str, Any] | None
    ) -> dict[str, Any]:
        if raw is None:
            return self._evaluation_skeleton(record, architecture, status=record.status)
        if "evaluation_id" in raw:
            return raw
        status = "completed" if raw.get("status") in {"deployable", "not_deployable"} else raw.get("status", record.status)
        result = self._evaluation_skeleton(record, architecture, status=status)
        if raw.get("status") == "deployable":
            partition_scale = raw.get("partition_scale", {})
            partitions = partition_scale.get("partitions", [])
            result.update({
                "is_deployable": True,
                "partition_summary": {
                    "partition_count": partition_scale.get("partition_count", len(partitions)),
                    "partition_sizes": [len(item.get("qubits", [])) for item in partitions],
                    "partitions": partitions,
                },
                "metrics": {
                    "abstract_swap_count": raw.get("swap_count", 0),
                    "cross_partition_communication_count": raw.get("cross_qpu_communication_count", 0),
                    "original_operation_count": raw.get("original_operation_count", 0),
                    "routed_operation_count": raw.get("routed_operation_count", 0),
                    "original_two_qubit_operation_count": raw.get("routing", {}).get("original_two_qubit_operation_count", 0),
                    "routed_two_qubit_operation_count": raw.get("routing", {}).get("routed_two_qubit_operation_count", 0),
                    "native_two_qubit_gate_equivalent_count": raw.get("native_two_qubit_gate_equivalent_count", 0),
                },
                "energy_validation": {
                    "unpartitioned_vqe_energy_hartree": raw.get("unpartitioned_vqe_energy_hartree", 0.0),
                    "distributed_simulation_energy_hartree": raw.get("distributed_vqe_energy_hartree", 0.0),
                    "distributed_execution_error_hartree": raw.get("distributed_vqe_vqe_execution_error_hartree", 0.0),
                },
            })
        elif raw.get("failure"):
            result.update({"is_deployable": False, "failure_reason": raw["failure"]})
        return result

    @staticmethod
    def _problem_skeleton(molecular_problem_id: str, status: str) -> dict[str, Any]:
        return {
            "molecular_problem_id": molecular_problem_id,
            "status": status,
            "stages": [],
            "molecule": None,
            "hf_energy_hartree": None,
            "active_space": None,
            "hamiltonian": None,
            "vqe": None,
            "fci_reference": {
                "status": "not_configured", "method": None, "energy_hartree": None,
                "message": "No constrained-active-space FCI runtime is configured.",
            },
            "vqe_fci_scientific_error_hartree": None,
            "optimizer_validation": None,
            "scientific_validation": None,
            "hamiltonian_builder_version": None,
            "scientific_validation_version": None,
        }

    def _result_skeleton(
        self,
        molecular_problem_id: str,
        records: list[DeploymentEvaluationRecord],
        architectures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evaluations = [
            self._evaluation_skeleton(record, architecture, status="queued")
            for record, architecture in zip(records, architectures, strict=True)
        ]
        return {
            "molecular_problem": self._problem_skeleton(molecular_problem_id, "queued"),
            "deployment_evaluations": evaluations,
            "summary": self._summary(evaluations),
        }

    @staticmethod
    def _architecture_result(architecture: dict[str, Any]) -> dict[str, Any]:
        partition = architecture["partition"]
        return {
            "inter_qpu_topology": partition.get("inter_qpu_topology") or partition.get("topology_edges") or [],
            "virtual_qpus": partition.get("virtual_qpus") or [],
            "initial_layout": partition.get("initial_layout", "identity"),
            "routing_method": partition.get("routing_method", "shortest_path_swap"),
        }

    def _evaluation_skeleton(
        self, record: DeploymentEvaluationRecord, architecture: dict[str, Any], *, status: str
    ) -> dict[str, Any]:
        return {
            "evaluation_id": record.evaluation_id,
            "architecture_id": architecture["architecture_id"],
            "architecture_name": architecture.get("architecture_name") or architecture["architecture_id"],
            "status": status,
            "is_deployable": None,
            "failure_reason": None,
            "partition_summary": None,
            "architecture": self._architecture_result(architecture),
            "metrics": None,
            "energy_validation": None,
            "distribution": None,
        }

    @staticmethod
    def _summary(evaluations: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total_evaluation_count": len(evaluations),
            "completed_evaluation_count": sum(item["status"] == "completed" for item in evaluations),
            "deployable_evaluation_count": sum(item.get("is_deployable") is True for item in evaluations),
            "non_deployable_evaluation_count": sum(item.get("is_deployable") is False for item in evaluations),
            "failed_evaluation_count": sum(item["status"] == "failed" for item in evaluations),
        }

    def _set_result(self, study: DeploymentStudyRecord, result: dict[str, Any]) -> None:
        lifecycle = (study.result_json or {}).get("_lifecycle", {})
        study.result_json = {**result, "_lifecycle": lifecycle}

    def _replace_result(self, study: DeploymentStudyRecord, *, molecular_problem: dict[str, Any], current_stage: str) -> None:
        result = self._result_without_lifecycle(study.result_json)
        result["molecular_problem"] = molecular_problem
        result["summary"] = self._summary(result["deployment_evaluations"])
        self._set_result(study, result)
        self._update_lifecycle(study, current_stage=current_stage)

    def _replace_evaluation(self, study: DeploymentStudyRecord, evaluation: dict[str, Any]) -> None:
        result = self._result_without_lifecycle(study.result_json)
        result["deployment_evaluations"] = [
            evaluation if item["evaluation_id"] == evaluation["evaluation_id"] else item
            for item in result["deployment_evaluations"]
        ]
        result["summary"] = self._summary(result["deployment_evaluations"])
        self._set_result(study, result)

    def _update_lifecycle(self, study: DeploymentStudyRecord, **updates: str) -> None:
        payload = study.result_json or {}
        lifecycle = dict(payload.get("_lifecycle", {}))
        lifecycle.update({key: value for key, value in updates.items() if value is not None})
        study.result_json = {**payload, "_lifecycle": lifecycle}

    @staticmethod
    def _with_lifecycle(result: dict[str, Any], **lifecycle: str) -> dict[str, Any]:
        return {**result, "_lifecycle": lifecycle}

    @staticmethod
    def _result_without_lifecycle(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {key: value for key, value in payload.items() if key != "_lifecycle"}

    def _problem_result(self, molecular_problem_id: str, base: dict[str, Any]) -> dict[str, Any]:
        common_stages = {
            "input_validation", "electronic_structure", "active_space_selection", "fermionic_hamiltonian",
            "qubit_mapping", "vqe_optimization",
        }
        return {
            "molecular_problem_id": molecular_problem_id,
            "status": "completed",
            "stages": [stage for stage in base["stages"] if stage["stage"] in common_stages],
            "molecule": base["molecule"],
            "hf_energy_hartree": base["hf_energy_hartree"],
            "active_space": base["active_space"],
            "hamiltonian": base["hamiltonian"],
            "vqe": {**base["vqe"], "unpartitioned_energy_hartree": base["energies"]["unpartitioned_benchmark_energy_hartree"]},
            "fci_reference": base.get("fci_reference") or {
                "status": "not_configured", "method": None, "energy_hartree": None,
                "message": "No constrained-active-space FCI runtime is configured.",
            },
            "vqe_fci_scientific_error_hartree": (base.get("scientific_validation") or {}).get("vqe_fci_error_hartree"),
            "optimizer_validation": base.get("optimizer_validation"),
            "scientific_validation": base.get("scientific_validation"),
            "hamiltonian_builder_version": base.get("hamiltonian_builder_version"),
            "scientific_validation_version": base.get("scientific_validation_version"),
        }

    def _evaluate_architecture(
        self, base: dict[str, Any], record: DeploymentEvaluationRecord, architecture: dict[str, Any]
    ) -> dict[str, Any]:
        partition = architecture["partition"]
        try:
            partition_result = self.workflow_service._partition_circuit(
                base["vqe"]["qasm"], base["hamiltonian"]["qubit_count"], partition["partition_count"]
            )
            mapping_result = self.workflow_service._map_virtual_nodes(partition_result, partition)
            routing_result = self.workflow_service._route_partition_circuits(
                base["vqe"]["qasm"], partition_result, mapping_result, partition
            )
            distributed = self.workflow_service._run_distributed_simulation(
                base["hamiltonian"], partition_result, mapping_result, routing_result
            )
            vqe_energy = base["energies"]["unpartitioned_benchmark_energy_hartree"]
            distributed_energy = distributed["energy_hartree"]
            distribution = {
                "backend_type": "simulator",
                "capability_level": "logical_virtual_qpu",
                "is_real_qpu": False,
                "partition_scheme": partition_result["partition_scheme"],
                "virtual_node_mapping": mapping_result["virtual_node_mapping"],
                "topology_edges": mapping_result["topology_edges"],
                "mapping_cost": mapping_result["mapping_cost"],
                "inter_qpu_topology": mapping_result["inter_qpu_topology"],
                "partition_chip_routing": routing_result["partition_chip_routing"],
                "two_qubit_routing_evidence": routing_result["two_qubit_routing_evidence"],
                "routed_execution_plan": routing_result["routed_execution_plan"],
                "original_two_qubit_operation_count": routing_result["original_two_qubit_operation_count"],
                "routed_two_qubit_operation_count": routing_result["routed_two_qubit_operation_count"],
                "intra_chip_routing_cost": routing_result["intra_chip_routing_cost"],
                "cross_partition_communication_count": distributed["cross_partition_communication_count"],
                "communication_events": distributed["communication_events"],
                "actual_partition_consumption": distributed["actual_partition_consumption"],
                "actual_routed_plan_consumption": distributed["actual_routed_plan_consumption"],
                "final_logical_to_physical_layout": distributed["final_logical_to_physical_layout"],
                "simulation_strategy": distributed["simulation_strategy"],
                "state_norm": distributed["state_norm"],
            }
            partition_routing = routing_result["partition_chip_routing"]
            return {
                **self._evaluation_skeleton(record, architecture, status="completed"),
                "is_deployable": True,
                "partition_summary": {
                    "partition_count": len(partition_result["partitions"]),
                    "partition_sizes": [len(item) for item in partition_result["partitions"]],
                    "partitions": partition_result["partition_scheme"]["partitions"],
                },
                "metrics": {
                    "abstract_swap_count": routing_result["intra_chip_routing_cost"]["abstract_swap_count"],
                    "cross_partition_communication_count": distributed["cross_partition_communication_count"],
                    "original_operation_count": sum(item["original_operation_count"] for item in partition_routing),
                    "routed_operation_count": sum(item["routed_operation_count"] for item in partition_routing),
                    "original_two_qubit_operation_count": routing_result["original_two_qubit_operation_count"],
                    "routed_two_qubit_operation_count": routing_result["routed_two_qubit_operation_count"],
                    "native_two_qubit_gate_equivalent_count": routing_result["intra_chip_routing_cost"]["native_two_qubit_gate_equivalent_count"],
                },
                "energy_validation": {
                    "unpartitioned_vqe_energy_hartree": vqe_energy,
                    "distributed_simulation_energy_hartree": distributed_energy,
                    "distributed_execution_error_hartree": abs(distributed_energy - vqe_energy),
                },
                "distribution": distribution,
            }
        except MoleculeWorkflowError as exc:
            if exc.status_code == 422:
                return {
                    **self._evaluation_skeleton(record, architecture, status="completed"),
                    "is_deployable": False,
                    "failure_reason": self._failure_reason(exc),
                }
            return {
                **self._evaluation_skeleton(record, architecture, status="failed"),
                "failure_reason": self._failure_reason(exc),
            }
        except Exception as exc:
            return {
                **self._evaluation_skeleton(record, architecture, status="failed"),
                "failure_reason": {"code": "deployment_evaluation_failed", "message": str(exc), "stage": "deployment_evaluation"},
            }

    @staticmethod
    def _failure_reason(exc: MoleculeWorkflowError) -> dict[str, Any]:
        failure = exc.as_dict()
        return {"code": failure["code"], "message": failure["message"], "stage": failure.get("stage")}

    @staticmethod
    def _error(
        code: str, message: str, stage: str | None, study: DeploymentStudyRecord, molecular_problem_id: str
    ) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "stage": stage,
            "study_id": study.study_id,
            "molecular_problem_id": molecular_problem_id,
            "architecture_id": None,
        }
