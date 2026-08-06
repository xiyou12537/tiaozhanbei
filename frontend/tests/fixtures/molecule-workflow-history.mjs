export const passedHistoryItem = {
  workflow_id: 'molwf_history_lih_passed',
  molecule_name: 'LiH',
  created_at: '2026-08-06T03:54:26+00:00',
  completed_at: '2026-08-06T03:54:35+00:00',
  duration_ms: 9125.4,
  status: 'completed',
  validation_status: 'passed',
  optimizer_name: 'Powell',
  qubit_count: 4,
  pauli_term_count: 100,
  vqe_energy_hartree: -7.8823622861,
  distributed_energy_hartree: -7.882362286,
  absolute_error_hartree: 0.0000000001,
}

export const needsReviewHistoryItem = {
  workflow_id: 'molwf_history_h2o_review',
  molecule_name: 'H2O',
  created_at: '2026-08-05T13:12:00+00:00',
  completed_at: '2026-08-05T13:12:16+00:00',
  duration_ms: 16420,
  status: 'completed',
  validation_status: 'needs_review',
  optimizer_name: 'Powell',
  qubit_count: 8,
  pauli_term_count: 276,
  vqe_energy_hartree: -74.9651,
  distributed_energy_hartree: -74.96509,
  absolute_error_hartree: 0.00001,
}

export const legacyHistoryItem = {
  workflow_id: 'molwf_history_legacy',
  molecule_name: 'H2',
  created_at: '2026-08-01T01:02:03+00:00',
  completed_at: null,
  duration_ms: null,
  status: 'failed',
  validation_status: null,
  optimizer_name: null,
  qubit_count: null,
  pauli_term_count: null,
  vqe_energy_hartree: null,
  distributed_energy_hartree: null,
  absolute_error_hartree: null,
}

export function historyResponse(items, overrides = {}) {
  return {
    items,
    page: 1,
    page_size: 20,
    total: items.length,
    total_pages: items.length ? 1 : 0,
    ...overrides,
  }
}
