from __future__ import annotations

import logging
import math
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from ase.data import atomic_numbers

from backend.services.electronic_structure.docker_adapter import (
    DockerPySCFAdapter,
    ElectronicStructureRuntimeError,
)
from backend.services.quantum_chemistry.vqe_service import VqeSimulatorService
from backend.services.runtime_status import load_circuit_runtime, load_partition_pipeline
from quantum_partitioning.chip_mapping import (
    build_partition_interaction_graph,
    find_chip_mapping,
    parse_target_topology,
)

from .distributed_simulator import DistributedSimulationError, LogicalVirtualQPUSimulator
from .repository import MoleculeWorkflowRepository

logger = logging.getLogger(__name__)

MAX_ATOMS = 10
MAX_MAPPED_QUBITS = 12
MAX_ACTIVE_ORBITALS = MAX_MAPPED_QUBITS // 2
STAGE_NAMES = (
    "input_validation",
    "electronic_structure",
    "active_space_selection",
    "fermionic_hamiltonian",
    "qubit_mapping",
    "vqe_optimization",
    "circuit_partitioning",
    "virtual_node_mapping",
    "logical_distributed_simulation",
)


class MoleculeWorkflowError(Exception):
    def __init__(self, code: str, message: str, stage: str, status_code: int = 422, workflow_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.status_code = status_code
        self.workflow_id = workflow_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "workflow_id": self.workflow_id,
        }


class MoleculeWorkflowService:
    """Orchestrate and persist the real small-molecule logical simulation loop."""

    def __init__(
        self,
        repository: MoleculeWorkflowRepository,
        electronic_structure_adapter: DockerPySCFAdapter | None = None,
        vqe_service: VqeSimulatorService | None = None,
        distributed_simulator: LogicalVirtualQPUSimulator | None = None,
    ) -> None:
        self.repository = repository
        self.electronic_structure_adapter = electronic_structure_adapter or DockerPySCFAdapter()
        self.vqe_service = vqe_service or VqeSimulatorService()
        self.distributed_simulator = distributed_simulator or LogicalVirtualQPUSimulator()

    def execute(self, request: dict[str, Any], owner_user_id: int, idempotency_key: str | None = None) -> dict[str, Any]:
        if idempotency_key:
            existing = self.repository.get_by_idempotency_key(owner_user_id, idempotency_key)
            if existing is not None:
                return self._resolve_idempotent_record(existing, request)

        workflow_id = f"molwf_{uuid.uuid4().hex}"
        try:
            record = self.repository.create(
                {
                    "workflow_id": workflow_id,
                    "user_id": owner_user_id,
                    "idempotency_key": idempotency_key,
                    "molecule_name": request["molecule_name"],
                    "execution_mode": request["execution_mode"],
                    "status": "running",
                    "current_stage": STAGE_NAMES[0],
                    "request_json": request,
                    "stages_json": [],
                }
            )
        except IntegrityError:
            self.repository.session.rollback()
            if idempotency_key:
                existing = self.repository.get_by_idempotency_key(owner_user_id, idempotency_key)
                if existing is not None:
                    return self._resolve_idempotent_record(existing, request)
            raise

        stages: list[dict[str, Any]] = []
        try:
            atomic_sites = self._run_stage(
                record,
                stages,
                "input_validation",
                lambda: self._validate_input(request),
                lambda sites: {"atom_count": len(sites), "geometry_optimization_performed": False},
            )
            electronic_request = {
                "atomic_sites": atomic_sites,
                "total_charge": request["charge"],
                "spin_multiplicity": request["spin_multiplicity"],
                "basis_set": request["basis_set"],
            }
            electronic_result = self._run_stage(
                record,
                stages,
                "electronic_structure",
                lambda: self._generate_electronic_structure(electronic_request),
                lambda result: {
                    "method_name": result["method_name"],
                    "hf_total_energy_hartree": result["hf_total_energy_hartree"],
                    "candidate_count": len(result["active_space_candidates"]),
                },
            )
            active_space = self._run_stage(
                record,
                stages,
                "active_space_selection",
                lambda: self._select_active_space(electronic_result, request.get("active_space_orbitals")),
                lambda result: result,
            )
            hamiltonian_result = self._run_stage(
                record,
                stages,
                "fermionic_hamiltonian",
                lambda: self._build_hamiltonian(electronic_request, active_space),
                lambda result: {
                    "core_energy_hartree": result["core_energy_hartree"],
                    "active_orbitals": active_space["active_orbitals"],
                },
            )
            mapped_hamiltonian = self._run_stage(
                record,
                stages,
                "qubit_mapping",
                lambda: self._map_hamiltonian(hamiltonian_result, request),
                lambda result: {
                    "mapping_method": result["mapping_method"],
                    "qubit_count": result["qubit_count"],
                    "pauli_term_count": len(result["pauli_terms"]),
                },
            )
            initial_occupied_qubits = self._hartree_fock_occupied_qubits(
                active_space["active_electrons"],
                request["spin_multiplicity"],
            )
            vqe_request = {
                **request["vqe"],
                "initial_occupied_qubits": initial_occupied_qubits,
            }
            vqe_result = self._run_stage(
                record,
                stages,
                "vqe_optimization",
                lambda: self.vqe_service.execute(
                    mapped_hamiltonian["qubit_count"],
                    mapped_hamiltonian["pauli_terms"],
                    vqe_request,
                ),
                lambda result: {
                    "iteration_count": len(result["history"]),
                    "converged": result["converged"],
                    "unpartitioned_energy_hartree": result["final_energy_hartree"],
                },
            )
            partition_result = self._run_stage(
                record,
                stages,
                "circuit_partitioning",
                lambda: self._partition_circuit(
                    vqe_result["qasm_content"],
                    mapped_hamiltonian["qubit_count"],
                    request["partition"]["partition_count"],
                ),
                lambda result: {
                    "partition_count": len(result["partitions"]),
                    "teleportations": result["teleportations"],
                    "global_gates": result["global_gates"],
                },
            )
            mapping_result = self._run_stage(
                record,
                stages,
                "virtual_node_mapping",
                lambda: self._map_virtual_nodes(partition_result, request["partition"]),
                lambda result: {
                    "virtual_node_count": len(result["virtual_node_mapping"]),
                    "mapping_cost": result["mapping_cost"],
                    "topology_edges": result["topology_edges"],
                },
            )
            distributed_result = self._run_stage(
                record,
                stages,
                "logical_distributed_simulation",
                lambda: self._run_distributed_simulation(
                    vqe_result["qasm_content"],
                    mapped_hamiltonian,
                    partition_result,
                    mapping_result,
                ),
                lambda result: {
                    "energy_hartree": result["energy_hartree"],
                    "cross_partition_communication_count": result["cross_partition_communication_count"],
                    "actual_partition_consumption": result["actual_partition_consumption"],
                },
            )

            unpartitioned_energy = float(vqe_result["final_energy_hartree"])
            distributed_energy = float(distributed_result["energy_hartree"])
            validation_status, validation_issues = self._scientific_validation(vqe_result)
            result = {
                "workflow_id": workflow_id,
                "status": "completed",
                "current_stage": "completed",
                "validation_status": validation_status,
                "validation_issues": validation_issues,
                "execution_mode": "logical_virtual_qpu",
                "is_real_qpu": False,
                "molecule": {
                    "molecule_name": request["molecule_name"],
                    "geometry": request["geometry"],
                    "atom_count": len(atomic_sites),
                    "charge": request["charge"],
                    "spin_multiplicity": request["spin_multiplicity"],
                    "basis_set": request["basis_set"],
                    "geometry_optimization_performed": False,
                },
                "stages": stages,
                "hf_energy_hartree": float(electronic_result["hf_total_energy_hartree"]),
                "active_space": active_space,
                "hamiltonian": {
                    "mapping_method": mapped_hamiltonian["mapping_method"],
                    "fallback_reason": mapped_hamiltonian.get("fallback_reason"),
                    "qubit_count": mapped_hamiltonian["qubit_count"],
                    "qubit_count_before_tapering": mapped_hamiltonian["qubit_count_before_tapering"],
                    "z2_tapering_applied": mapped_hamiltonian["z2_tapering_applied"],
                    "pauli_term_count": len(mapped_hamiltonian["pauli_terms"]),
                    "pauli_terms": mapped_hamiltonian["pauli_terms"],
                    "coefficient_cutoff": request["pauli_coefficient_cutoff"],
                    "truncation_error_estimate": mapped_hamiltonian["truncation_error_estimate"],
                },
                "vqe": {
                    "ansatz": "hardware_efficient_ry_cx",
                    "optimizer": vqe_result["optimizer"],
                    "initial_state": "hartree_fock_occupation",
                    "initial_occupied_qubits": initial_occupied_qubits,
                    "qasm": vqe_result["qasm_content"],
                    "converged": vqe_result["converged"],
                    "optimizer_diagnostics": vqe_result["optimizer_diagnostics"],
                    "best_parameters": vqe_result["best_parameters"],
                    "iteration_count": len(vqe_result["history"]),
                    "iteration_history": [
                        {
                            "iteration": item["iteration"],
                            "parameters": item["parameters"],
                            "energy_hartree": item["energy_hartree"],
                            "energy_uncertainty_hartree": item["energy_uncertainty_hartree"],
                        }
                        for item in vqe_result["history"]
                    ],
                },
                "distribution": {
                    "backend_type": "simulator",
                    "capability_level": "logical_virtual_qpu",
                    "is_real_qpu": False,
                    "partition_scheme": partition_result["partition_scheme"],
                    "virtual_node_mapping": mapping_result["virtual_node_mapping"],
                    "topology_edges": mapping_result["topology_edges"],
                    "mapping_cost": mapping_result["mapping_cost"],
                    "cross_partition_communication_count": distributed_result["cross_partition_communication_count"],
                    "communication_events": distributed_result["communication_events"],
                    "actual_partition_consumption": distributed_result["actual_partition_consumption"],
                    "simulation_strategy": distributed_result["simulation_strategy"],
                    "state_norm": distributed_result["state_norm"],
                },
                "energies": {
                    "unpartitioned_benchmark_energy_hartree": unpartitioned_energy,
                    "distributed_simulation_energy_hartree": distributed_energy,
                    "absolute_error_hartree": abs(distributed_energy - unpartitioned_energy),
                },
            }
            self.repository.complete(record, result)
            return result
        except MoleculeWorkflowError as exc:
            exc.workflow_id = workflow_id
            self._mark_running_stage_failed(stages, exc)
            self.repository.fail(record, exc.as_dict(), stages)
            raise
        except Exception as exc:
            logger.exception("Molecule workflow %s failed at stage %s", workflow_id, record.current_stage)
            error = MoleculeWorkflowError(
                "workflow_execution_failed",
                "分子计算工作流执行失败，请根据 workflow_id 查询失败阶段。",
                record.current_stage,
                500,
                workflow_id,
            )
            self._mark_running_stage_failed(stages, error)
            self.repository.fail(record, error.as_dict(), stages)
            raise error from exc

    def get(self, workflow_id: str, owner_user_id: int) -> dict[str, Any]:
        record = self.repository.get(workflow_id, owner_user_id)
        if record is None:
            raise MoleculeWorkflowError(
                "molecule_workflow_not_found",
                "未找到分子计算工作流或无权访问。",
                "lookup",
                404,
                workflow_id,
            )
        if record.status == "completed" and record.result_json:
            return record.result_json
        raise MoleculeWorkflowError(
            record.error_json.get("code", "molecule_workflow_not_completed") if record.error_json else "molecule_workflow_not_completed",
            record.error_json.get("message", "分子计算工作流尚未完成。") if record.error_json else "分子计算工作流尚未完成。",
            record.current_stage,
            409 if record.status == "running" else 422,
            workflow_id,
        )

    def list_workflows(
        self,
        owner_user_id: int,
        *,
        page: int,
        page_size: int,
        molecule_name: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
    ) -> dict[str, Any]:
        records, total = self.repository.list_for_user(
            owner_user_id,
            page=page,
            page_size=page_size,
            molecule_name=molecule_name,
            status=status,
            validation_status=validation_status,
        )
        return {
            "items": [self._history_item(record) for record in records],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        }

    @staticmethod
    def _history_item(record) -> dict[str, Any]:
        result = record.result_json or {}
        stages = result.get("stages") or record.stages_json or []
        completed_at = next(
            (stage.get("completed_at") for stage in reversed(stages) if stage.get("completed_at")),
            record.updated_at.isoformat() if record.status == "completed" and record.updated_at else None,
        )
        durations = [stage.get("duration_ms") for stage in stages if stage.get("duration_ms") is not None]
        energies = result.get("energies") or {}
        hamiltonian = result.get("hamiltonian") or {}
        vqe = result.get("vqe") or {}
        return {
            "workflow_id": record.workflow_id,
            "molecule_name": record.molecule_name,
            "created_at": record.created_at.isoformat(),
            "completed_at": completed_at,
            "duration_ms": float(sum(durations)) if durations else None,
            "status": record.status,
            "validation_status": result.get("validation_status"),
            "optimizer_name": vqe.get("optimizer"),
            "qubit_count": hamiltonian.get("qubit_count"),
            "pauli_term_count": hamiltonian.get("pauli_term_count"),
            "vqe_energy_hartree": energies.get("unpartitioned_benchmark_energy_hartree"),
            "distributed_energy_hartree": energies.get("distributed_simulation_energy_hartree"),
            "absolute_error_hartree": energies.get("absolute_error_hartree"),
        }

    def _run_stage(
        self,
        record,
        stages: list[dict[str, Any]],
        stage_name: str,
        operation: Callable[[], Any],
        detail_builder: Callable[[Any], dict[str, Any]],
    ) -> Any:
        started_at = datetime.now(timezone.utc)
        stage = {
            "stage": stage_name,
            "status": "running",
            "started_at": started_at.isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "details": {},
        }
        stages.append(stage)
        self.repository.update_progress(record, stage_name, stages)
        start = time.perf_counter()
        try:
            value = operation()
        except MoleculeWorkflowError:
            raise
        except ElectronicStructureRuntimeError as exc:
            raise MoleculeWorkflowError(
                "electronic_structure_runtime_unavailable",
                f"PySCF/OpenFermion 计算运行时不可用：{exc}",
                stage_name,
                503,
            ) from exc
        except DistributedSimulationError as exc:
            raise MoleculeWorkflowError(
                "logical_distributed_simulation_failed",
                str(exc),
                stage_name,
                422,
            ) from exc
        stage["status"] = "completed"
        stage["completed_at"] = datetime.now(timezone.utc).isoformat()
        stage["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
        stage["details"] = detail_builder(value)
        self.repository.update_progress(record, stage_name, stages)
        return value

    @staticmethod
    def _validate_input(request: dict[str, Any]) -> list[dict[str, Any]]:
        geometry = request["geometry"]
        if not 1 <= len(geometry) <= MAX_ATOMS:
            raise MoleculeWorkflowError(
                "atom_limit_exceeded",
                f"第一版仅支持 1 到 {MAX_ATOMS} 个原子的固定几何。",
                "input_validation",
                422,
            )
        atomic_sites = []
        for atom_index, atom in enumerate(geometry):
            element = atom["element"]
            if re.fullmatch(r"[A-Z][a-z]?", element) is None or element not in atomic_numbers:
                raise MoleculeWorkflowError(
                    "invalid_element_symbol",
                    f"第 {atom_index} 个原子的元素符号无效。",
                    "input_validation",
                    422,
                )
            atomic_sites.append(
                {
                    "element": element,
                    "position_angstrom": list(atom["coordinates_angstrom"]),
                }
            )
        for first_index, first_site in enumerate(atomic_sites):
            for second_site in atomic_sites[first_index + 1 :]:
                if math.dist(first_site["position_angstrom"], second_site["position_angstrom"]) < 1e-6:
                    raise MoleculeWorkflowError(
                        "overlapping_atoms",
                        "固定几何中存在坐标重合的原子。",
                        "input_validation",
                        422,
                    )
        electron_count = sum(atomic_numbers[site["element"]] for site in atomic_sites) - request["charge"]
        spin_excess = request["spin_multiplicity"] - 1
        if electron_count <= 0 or electron_count < spin_excess or (electron_count + spin_excess) % 2:
            raise MoleculeWorkflowError(
                "invalid_charge_spin_configuration",
                "总电荷、自旋多重度与分子电子数不兼容。",
                "input_validation",
                422,
            )
        return atomic_sites

    def _generate_electronic_structure(self, request: dict[str, Any]) -> dict[str, Any]:
        result = self.electronic_structure_adapter.generate_active_space_candidates(request)
        if result.get("status") == "needs_model_review" or not result.get("active_space_candidates"):
            raise MoleculeWorkflowError(
                result.get("error_code", "active_space_candidates_unavailable"),
                result.get("message", "未生成可用的活性空间候选。"),
                "electronic_structure",
                422,
            )
        return result

    @staticmethod
    def _scientific_validation(vqe_result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        if vqe_result["converged"]:
            return "passed", []
        return (
            "needs_review",
            [
                {
                    "code": "vqe_not_converged",
                    "stage": "vqe_optimization",
                    "iteration_count": len(vqe_result["history"]),
                    "message": "VQE optimizer did not converge within the configured iteration budget.",
                }
            ],
        )

    @staticmethod
    def _select_active_space(electronic_result: dict[str, Any], requested_orbitals: int | None) -> dict[str, Any]:
        valid_candidates = [
            candidate
            for candidate in electronic_result["active_space_candidates"]
            if 0 < int(candidate["active_electrons"]) <= 2 * int(candidate["active_orbitals"])
            and 2 * int(candidate["active_orbitals"]) <= MAX_MAPPED_QUBITS
        ]
        if requested_orbitals is not None:
            valid_candidates = [
                candidate for candidate in valid_candidates if int(candidate["active_orbitals"]) == requested_orbitals
            ]
        if not valid_candidates:
            raise MoleculeWorkflowError(
                "active_space_not_supported",
                f"没有满足不超过 {MAX_ACTIVE_ORBITALS} 个空间轨道/{MAX_MAPPED_QUBITS} 个量子比特的活性空间。",
                "active_space_selection",
                422,
            )
        selected = min(valid_candidates, key=lambda item: int(item["active_orbitals"]))
        return {
            "active_electrons": int(selected["active_electrons"]),
            "active_orbitals": int(selected["active_orbitals"]),
            "orbital_indices": [int(index) for index in selected["orbital_indices"]],
            "orbital_energies_hartree": [float(value) for value in selected.get("orbital_energies_hartree", [])],
            "selection_method": "requested_candidate" if requested_orbitals is not None else "smallest_valid_frontier_candidate",
        }

    def _build_hamiltonian(self, electronic_request: dict[str, Any], active_space: dict[str, Any]) -> dict[str, Any]:
        result = self.electronic_structure_adapter.build_hamiltonian(
            {
                **electronic_request,
                "orbital_indices": active_space["orbital_indices"],
                "active_electrons": active_space["active_electrons"],
            }
        )
        if "core_energy_hartree" not in result:
            raise MoleculeWorkflowError(
                "fermionic_hamiltonian_failed",
                result.get("message", "PySCF 未返回费米子 Hamiltonian 积分。"),
                "fermionic_hamiltonian",
                422,
            )
        return result

    @staticmethod
    def _hartree_fock_occupied_qubits(active_electrons: int, spin_multiplicity: int) -> list[int]:
        spin_excess = spin_multiplicity - 1
        if active_electrons < spin_excess or (active_electrons + spin_excess) % 2:
            raise MoleculeWorkflowError(
                "active_space_spin_incompatible",
                "活性电子数与自旋多重度不兼容，无法构造 Hartree–Fock 初态。",
                "vqe_optimization",
                422,
            )
        alpha_electrons = (active_electrons + spin_excess) // 2
        beta_electrons = active_electrons - alpha_electrons
        return [
            *[2 * orbital for orbital in range(alpha_electrons)],
            *[2 * orbital + 1 for orbital in range(beta_electrons)],
        ]

    def _map_hamiltonian(self, hamiltonian: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        mapping_request = {
            "core_energy_hartree": hamiltonian["core_energy_hartree"],
            "mapping_method": request["mapping_method"],
            "coefficient_cutoff": request["pauli_coefficient_cutoff"],
            "enable_z2_tapering": False,
            "z2_tapering_sectors": {},
        }
        for field in (
            "one_body_integrals",
            "two_body_integrals",
            "spin_orbital_one_body_integrals",
            "spin_orbital_two_body_integrals",
        ):
            if hamiltonian.get(field) is not None:
                mapping_request[field] = hamiltonian[field]
        result = self.electronic_structure_adapter.map_hamiltonian(mapping_request)
        if int(result["qubit_count"]) > MAX_MAPPED_QUBITS:
            raise MoleculeWorkflowError(
                "mapped_qubit_limit_exceeded",
                f"映射后得到 {result['qubit_count']} 个量子比特，超过第一版上限 {MAX_MAPPED_QUBITS}。",
                "qubit_mapping",
                422,
            )
        if not result.get("pauli_terms"):
            raise MoleculeWorkflowError(
                "empty_qubit_hamiltonian",
                "量子比特 Hamiltonian 不包含可执行的 Pauli 项。",
                "qubit_mapping",
                422,
            )
        return result

    @staticmethod
    def _partition_circuit(qasm_content: str, qubit_count: int, partition_count: int) -> dict[str, Any]:
        if partition_count > qubit_count:
            raise MoleculeWorkflowError(
                "invalid_partition_count",
                "分区数不能超过量子比特数。",
                "circuit_partitioning",
                422,
            )
        load_qasm_string, remove_single_qubit_gates, _ = load_circuit_runtime()
        parsed_qubit_count, gates = load_qasm_string(qasm_content)
        if parsed_qubit_count != qubit_count:
            raise MoleculeWorkflowError(
                "qasm_qubit_count_mismatch",
                "VQE QASM 与映射后 Hamiltonian 的量子比特数不一致。",
                "circuit_partitioning",
                422,
            )
        multi_qubit_gates = remove_single_qubit_gates(gates)
        scheme, b1, b2 = load_partition_pipeline()(
            gates=multi_qubit_gates,
            qubits=list(range(qubit_count)),
            num_partitions=partition_count,
            max_imbalance=1,
        )
        if scheme is None:
            raise MoleculeWorkflowError(
                "partition_scheme_unavailable",
                "现有线路分区算法未找到有效方案。",
                "circuit_partitioning",
                422,
            )
        return {
            "partitions": scheme.partitions,
            "optimized_gates": scheme.optimized_gates,
            "teleportations": int(scheme.teleportations),
            "global_gates": int(scheme.global_gates),
            "all_multi_qubit_gates": multi_qubit_gates,
            "partition_scheme": {
                "method": "existing_greedy_partitioning_pipeline",
                "partition_count": len(scheme.partitions),
                "partitions": [
                    {"partition_id": f"P{index + 1}", "qubits": partition}
                    for index, partition in enumerate(scheme.partitions)
                ],
                "teleportations": int(scheme.teleportations),
                "global_gate_count": int(scheme.global_gates),
                "parameters": {"b1": b1, "b2": b2, "max_imbalance": 1},
            },
        }

    @staticmethod
    def _map_virtual_nodes(partition_result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
        partition_count = len(partition_result["partitions"])
        raw_edges = request.get("topology_edges") or [
            {"source": index, "target": index + 1} for index in range(partition_count - 1)
        ]
        edges = [(int(edge["source"]), int(edge["target"])) for edge in raw_edges]
        topology_nodes = {node for edge in edges for node in edge}
        if topology_nodes != set(range(partition_count)):
            raise MoleculeWorkflowError(
                "invalid_virtual_topology",
                "虚拟节点拓扑必须恰好覆盖从 0 开始的全部分区节点。",
                "virtual_node_mapping",
                422,
            )
        interaction_graph, _ = build_partition_interaction_graph(
            partition_result["partitions"],
            partition_result["all_multi_qubit_gates"],
        )
        mapping, mapping_cost = find_chip_mapping(interaction_graph, parse_target_topology(edges))
        if mapping is None:
            raise MoleculeWorkflowError(
                "virtual_node_mapping_unavailable",
                "现有芯片映射算法未找到满足拓扑的虚拟节点映射。",
                "virtual_node_mapping",
                422,
            )
        partition_lookup = {
            f"P{index + 1}": partition for index, partition in enumerate(partition_result["partitions"])
        }
        virtual_node_mapping = [
            {
                "virtual_node_id": virtual_node_id,
                "partition_id": partition_id,
                "qubits": partition_lookup[partition_id],
            }
            for virtual_node_id, partition_id in sorted(mapping.items())
        ]
        return {
            "virtual_node_mapping": virtual_node_mapping,
            "mapping_cost": float(mapping_cost),
            "topology_edges": [
                {"source": source, "target": target} for source, target in edges
            ],
        }

    def _run_distributed_simulation(
        self,
        qasm_content: str,
        mapped_hamiltonian: dict[str, Any],
        partition_result: dict[str, Any],
        mapping_result: dict[str, Any],
    ) -> dict[str, Any]:
        return self.distributed_simulator.execute(
            qasm_content=qasm_content,
            qubit_count=mapped_hamiltonian["qubit_count"],
            pauli_terms=mapped_hamiltonian["pauli_terms"],
            partitions=partition_result["partitions"],
            virtual_node_mapping=mapping_result["virtual_node_mapping"],
        )

    @staticmethod
    def _mark_running_stage_failed(stages: list[dict[str, Any]], error: MoleculeWorkflowError) -> None:
        if not stages or stages[-1]["status"] != "running":
            return
        stages[-1]["status"] = "failed"
        stages[-1]["completed_at"] = datetime.now(timezone.utc).isoformat()
        stages[-1]["details"] = {"error_code": error.code, "message": error.message}

    def _resolve_idempotent_record(self, record, request: dict[str, Any]) -> dict[str, Any]:
        if record.request_json != request:
            raise MoleculeWorkflowError(
                "idempotency_key_reused",
                "同一 Idempotency-Key 不能用于不同的分子计算请求。",
                "input_validation",
                409,
                record.workflow_id,
            )
        if record.status == "completed" and record.result_json:
            return record.result_json
        if record.status == "failed":
            error = record.error_json or {}
            raise MoleculeWorkflowError(
                error.get("code", "molecule_workflow_failed"),
                error.get("message", "先前的同幂等键工作流执行失败。"),
                error.get("stage", record.current_stage),
                409,
                record.workflow_id,
            )
        raise MoleculeWorkflowError(
            "molecule_workflow_in_progress",
            "相同幂等键的分子计算工作流仍在执行。",
            record.current_stage,
            409,
            record.workflow_id,
        )
