import { readFileSync } from 'node:fs'

const base = JSON.parse(readFileSync(new URL('./h2-molecule-workflow.json', import.meta.url), 'utf8'))

export default {
  ...base,
  workflow_id: 'molwf_zero_swap_fixture',
  distribution: {
    ...base.distribution,
    inter_qpu_topology: [{ source: 0, target: 1 }],
    partition_chip_routing: [
      {
        partition_id: 'P1',
        virtual_qpu_id: 'T1',
        logical_qubits: [0, 1],
        physical_qubit_count: 2,
        physical_coupling_map: [{ source: 0, target: 1 }],
        logical_to_physical_initial: { 0: 0, 1: 1 },
        logical_to_physical_final: { 0: 0, 1: 1 },
        original_two_qubit_operation_count: 1,
        routed_two_qubit_operation_count: 1,
      },
      {
        partition_id: 'P2',
        virtual_qpu_id: 'T2',
        logical_qubits: [2, 3],
        physical_qubit_count: 2,
        physical_coupling_map: [{ source: 0, target: 1 }],
        logical_to_physical_initial: { 2: 0, 3: 1 },
        logical_to_physical_final: { 2: 0, 3: 1 },
        original_two_qubit_operation_count: 1,
        routed_two_qubit_operation_count: 1,
      },
    ],
    two_qubit_routing_evidence: [
      {
        partition_id: 'P1',
        virtual_qpu_id: 'T1',
        gate_index: 4,
        gate: 'cx',
        logical_qubits: [0, 1],
        initial_physical_qubits: [0, 1],
        final_physical_qubits: [0, 1],
        routing_status: 'direct',
        path: [0, 1],
        swap_positions: [],
        swap_path: [],
      },
    ],
    routed_execution_plan: [
      {
        execution_index: 0,
        original_gate_index: 4,
        operation: 'cx',
        scope: 'intra_qpu',
        partition_ids: ['P1'],
        virtual_qpu_ids: ['T1'],
        logical_qubits: [0, 1],
        physical_qubits: [0, 1],
        physical_edge_is_valid: true,
        layout_before: { 0: 0, 1: 1 },
        layout_after: { 0: 0, 1: 1 },
      },
    ],
    intra_chip_routing_cost: {
      abstract_swap_count: 0,
      routed_two_qubit_operation_count: 1,
      native_two_qubit_gate_equivalent_count: 1,
    },
    final_logical_to_physical_layout: { 0: 0, 1: 1, 2: 0, 3: 1 },
    actual_routed_plan_consumption: true,
  },
}
