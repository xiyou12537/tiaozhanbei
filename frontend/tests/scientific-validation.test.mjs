import assert from 'node:assert/strict'
import test from 'node:test'
import { circuitOperationMeta, scientificValidationView, scanScientificErrorSeries, workflowExecutionHeadline } from '../src/services/scientificValidationService.js'

test('three validation domains preserve backend status and label absent fields as legacy', () => {
  assert.deepEqual(scientificValidationView('optimizer', { status: 'passed', optimizer: 'Powell', success: true, termination_reason: 'optimizer_reported_success', nfev: 38 }).status, 'passed')
  assert.equal(scientificValidationView('scientific', { status: 'needs_review', issues: [{ code: 'particle_number_mismatch', message: 'particle number is not conserved' }] }).title, '科学结果需复核')
  assert.equal(scientificValidationView('deployment', null).message, '旧版结果，未提供该项验证')
})

test('scientific error curve preserves real zero, skips unavailable FCI and marks review points', () => {
  const points = [
    { point_index: 0, distance_angstrom: 1, status: 'completed', scientific_validation: { status: 'passed' }, vqe_fci_scientific_error_hartree: 0 },
    { point_index: 1, distance_angstrom: 1.2, status: 'completed', scientific_validation: { status: 'needs_review' }, vqe_fci_scientific_error_hartree: 0.01 },
    { point_index: 2, distance_angstrom: 1.4, status: 'failed', vqe_fci_scientific_error_hartree: 0.02 },
    { point_index: 3, distance_angstrom: 1.6, status: 'completed', vqe_fci_scientific_error_hartree: null },
  ]
  assert.deepEqual(scanScientificErrorSeries(points), [
    { pointIndex: 0, distance: 1, error: 0, needsReview: false },
    { pointIndex: 1, distance: 1.2, error: 0.01, needsReview: true },
  ])
})

test('particle-conserving operation map distinguishes state preparation, Pauli evolution, routing and unknown gates', () => {
  assert.equal(circuitOperationMeta('x').group, 'hf_initial_state')
  assert.equal(circuitOperationMeta('rz').group, 'parameterized_excitation')
  assert.equal(circuitOperationMeta('sdg').label, 'SDG')
  assert.equal(circuitOperationMeta('swap').group, 'routing_swap')
  assert.equal(circuitOperationMeta('cx', 'inter_qpu').group, 'inter_qpu_cx')
  assert.equal(circuitOperationMeta('custom_gate').label, 'CUSTOM_GATE')
})

test('workflow completion headline remains separate from all validation conclusions', () => {
  const headline = workflowExecutionHeadline('completed', 'passed')
  assert.equal(headline.title, 'Workflow 执行已完成')
  assert.doesNotMatch(headline.message, /计算通过/)
})
