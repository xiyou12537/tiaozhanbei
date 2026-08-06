from __future__ import annotations

import math
import re
from typing import Any

import numpy as np


class DistributedSimulationError(RuntimeError):
    """Raised when a partitioned logical simulation plan is incomplete or invalid."""


class LogicalVirtualQPUSimulator:
    """Execute an Ry-CX circuit as a tensor ordered by mapped virtual QPU nodes.

    This is an exact logical simulator, not hardware execution.  The partition and
    virtual-node mapping determine tensor-axis placement, gate locality and every
    recorded cross-node contraction.  Energy is evaluated from the resulting
    partition-aware tensor rather than copied from an unpartitioned execution.
    """

    _RY_PATTERN = re.compile(r"ry\(([^)]+)\)\s+q\[(\d+)]\s*;")
    _X_PATTERN = re.compile(r"x\s+q\[(\d+)]\s*;")
    _CX_PATTERN = re.compile(r"cx\s+q\[(\d+)]\s*,\s*q\[(\d+)]\s*;")

    def execute(
        self,
        *,
        qasm_content: str,
        qubit_count: int,
        pauli_terms: list[dict[str, Any]],
        partitions: list[list[int]],
        virtual_node_mapping: list[dict[str, Any]],
    ) -> dict[str, Any]:
        qubit_to_partition, partition_to_node, axis_order = self._validate_plan(
            qubit_count,
            partitions,
            virtual_node_mapping,
        )
        operations = self._parse_qasm(qasm_content, qubit_count)
        state = np.zeros((2,) * qubit_count, dtype=complex)
        state[(0,) * qubit_count] = 1.0
        qubit_to_axis = {qubit: axis for axis, qubit in enumerate(axis_order)}
        communication_events: list[dict[str, Any]] = []
        local_gate_count = 0

        for gate_index, operation in enumerate(operations):
            if operation["gate"] == "x":
                qubit = operation["qubits"][0]
                matrix = np.asarray([[0, 1], [1, 0]], dtype=complex)
                state = self._apply_matrix(state, matrix, [qubit_to_axis[qubit]])
                local_gate_count += 1
                continue
            if operation["gate"] == "ry":
                qubit = operation["qubits"][0]
                angle = operation["angle"]
                cosine = math.cos(angle / 2.0)
                sine = math.sin(angle / 2.0)
                matrix = np.asarray([[cosine, -sine], [sine, cosine]], dtype=complex)
                state = self._apply_matrix(state, matrix, [qubit_to_axis[qubit]])
                local_gate_count += 1
                continue

            control, target = operation["qubits"]
            control_partition = qubit_to_partition[control]
            target_partition = qubit_to_partition[target]
            if control_partition == target_partition:
                local_gate_count += 1
            else:
                communication_events.append(
                    {
                        "gate_index": gate_index,
                        "gate": "cx",
                        "control_qubit": control,
                        "target_qubit": target,
                        "source_partition_id": control_partition,
                        "target_partition_id": target_partition,
                        "source_virtual_node_id": partition_to_node[control_partition],
                        "target_virtual_node_id": partition_to_node[target_partition],
                    }
                )
            cx_matrix = np.asarray(
                [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]],
                dtype=complex,
            )
            state = self._apply_matrix(
                state,
                cx_matrix,
                [qubit_to_axis[control], qubit_to_axis[target]],
            )

        energy, term_expectations = self._evaluate_energy(
            state,
            pauli_terms,
            qubit_to_axis,
        )
        return {
            "energy_hartree": energy,
            "cross_partition_communication_count": len(communication_events),
            "communication_events": communication_events,
            "local_gate_count": local_gate_count,
            "state_norm": float(np.vdot(state.reshape(-1), state.reshape(-1)).real),
            "term_expectations": term_expectations,
            "axis_order_by_virtual_node": axis_order,
            "actual_partition_consumption": True,
            "simulation_strategy": "mapped_partition_tensor_contraction",
        }

    @staticmethod
    def _validate_plan(
        qubit_count: int,
        partitions: list[list[int]],
        virtual_node_mapping: list[dict[str, Any]],
    ) -> tuple[dict[int, str], dict[str, str], list[int]]:
        qubit_to_partition: dict[int, str] = {}
        partition_qubits: dict[str, list[int]] = {}
        for partition_index, qubits in enumerate(partitions, start=1):
            partition_id = f"P{partition_index}"
            partition_qubits[partition_id] = list(qubits)
            for qubit in qubits:
                if qubit in qubit_to_partition:
                    raise DistributedSimulationError(f"量子比特 {qubit} 被重复分配到多个分区。")
                qubit_to_partition[qubit] = partition_id
        if set(qubit_to_partition) != set(range(qubit_count)):
            raise DistributedSimulationError("分区方案必须且只能覆盖全部映射后量子比特。")

        partition_to_node: dict[str, str] = {}
        for assignment in virtual_node_mapping:
            partition_id = assignment["partition_id"]
            virtual_node_id = assignment["virtual_node_id"]
            if partition_id in partition_to_node:
                raise DistributedSimulationError(f"分区 {partition_id} 被重复映射。")
            if assignment.get("qubits") != partition_qubits.get(partition_id):
                raise DistributedSimulationError(f"虚拟节点 {virtual_node_id} 的量子比特与分区方案不一致。")
            partition_to_node[partition_id] = virtual_node_id
        if set(partition_to_node) != set(partition_qubits):
            raise DistributedSimulationError("每个逻辑分区都必须映射到一个虚拟 QPU 节点。")

        axis_order: list[int] = []
        for assignment in sorted(virtual_node_mapping, key=lambda item: item["virtual_node_id"]):
            axis_order.extend(sorted(assignment["qubits"]))
        return qubit_to_partition, partition_to_node, axis_order

    def _parse_qasm(self, qasm_content: str, qubit_count: int) -> list[dict[str, Any]]:
        operations: list[dict[str, Any]] = []
        declared_qubits: int | None = None
        for raw_line in qasm_content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("OPENQASM") or line.startswith("include"):
                continue
            register_match = re.fullmatch(r"qreg\s+q\[(\d+)]\s*;", line)
            if register_match:
                declared_qubits = int(register_match.group(1))
                continue
            ry_match = self._RY_PATTERN.fullmatch(line)
            if ry_match:
                operations.append(
                    {
                        "gate": "ry",
                        "angle": float(ry_match.group(1)),
                        "qubits": [int(ry_match.group(2))],
                    }
                )
                continue
            x_match = self._X_PATTERN.fullmatch(line)
            if x_match:
                operations.append({"gate": "x", "qubits": [int(x_match.group(1))]})
                continue
            cx_match = self._CX_PATTERN.fullmatch(line)
            if cx_match:
                operations.append(
                    {
                        "gate": "cx",
                        "qubits": [int(cx_match.group(1)), int(cx_match.group(2))],
                    }
                )
                continue
            raise DistributedSimulationError(f"logical_virtual_qpu 暂不支持 QASM 语句：{line}")
        if declared_qubits != qubit_count:
            raise DistributedSimulationError("QASM 量子寄存器规模与 Hamiltonian 不一致。")
        return operations

    @staticmethod
    def _apply_matrix(state: np.ndarray, matrix: np.ndarray, axes: list[int]) -> np.ndarray:
        moved = np.moveaxis(state, axes, list(range(len(axes))))
        updated = matrix @ moved.reshape(1 << len(axes), -1)
        restored = updated.reshape(moved.shape)
        return np.moveaxis(restored, list(range(len(axes))), axes)

    def _evaluate_energy(
        self,
        state: np.ndarray,
        pauli_terms: list[dict[str, Any]],
        qubit_to_axis: dict[int, int],
    ) -> tuple[float, list[dict[str, Any]]]:
        pauli_matrices = {
            "X": np.asarray([[0, 1], [1, 0]], dtype=complex),
            "Y": np.asarray([[0, -1j], [1j, 0]], dtype=complex),
            "Z": np.asarray([[1, 0], [0, -1]], dtype=complex),
        }
        energy = 0.0
        expectations: list[dict[str, Any]] = []
        flattened_state = state.reshape(-1)
        for term in pauli_terms:
            transformed = state
            if term["pauli_string"] != "I":
                for token in term["pauli_string"].split():
                    gate = token[0]
                    qubit = int(token[1:])
                    if gate not in pauli_matrices or qubit not in qubit_to_axis:
                        raise DistributedSimulationError(f"无效 Pauli 项：{term['pauli_string']}")
                    transformed = self._apply_matrix(
                        transformed,
                        pauli_matrices[gate],
                        [qubit_to_axis[qubit]],
                    )
            expectation = float(np.vdot(flattened_state, transformed.reshape(-1)).real)
            contribution = float(term["coefficient"]) * expectation
            energy += contribution
            expectations.append(
                {
                    "pauli_string": term["pauli_string"],
                    "expectation_value": expectation,
                    "energy_contribution_hartree": contribution,
                }
            )
        return float(energy), expectations
