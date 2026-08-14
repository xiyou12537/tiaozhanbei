import test from 'node:test'
import assert from 'node:assert/strict'
import { plainLanguageTerms, summarizeBondScanForBeginners, summarizeStudyForBeginners, summarizeWorkflowForBeginners, taskChoiceGuidance } from '../src/services/beginnerExperienceService.js'

test('beginner task choices describe all three primary jobs with real routes', () => {
  assert.deepEqual(taskChoiceGuidance.map(item => item.path), ['/app/molecules', '/app/molecular-studies/new', '/app/molecular-bond-scans/new'])
  assert.equal(taskChoiceGuidance.length, 3)
})

test('plain language glossary covers all protected technical terms', () => {
  const terms = new Set(plainLanguageTerms.map(([term]) => term))
  for (const term of ['Hamiltonian', 'VQE', 'HF', 'FCI', '活性空间', 'Pauli 项', 'Qubit', 'QPU', '分区', '拓扑', 'SWAP', '科学验证', '部署验证']) assert.ok(terms.has(term))
})

test('workflow summary preserves unknown status instead of calling it failed', () => {
  const summary = summarizeWorkflowForBeginners({ status: null, validation_status: null, energies: {} })
  assert.equal(summary.status, '状态待确认')
  assert.match(summary.statusReason, /不能据此判断任务失败或通过/)
})

test('workflow summary distinguishes completed results that still need review', () => {
  const summary = summarizeWorkflowForBeginners({ status: 'completed', validation_status: 'needs_review', validation_issues: [{ code: 'scientific' }], energies: { distributed_simulation_energy_hartree: -1.2 } })
  assert.equal(summary.status, '已完成')
  assert.equal(summary.confidence, '需要复核')
  assert.match(summary.keyResult, /-1.2 Ha/)
})

test('study and scan summaries keep failed and missing scientific minima explicit', () => {
  const study = summarizeStudyForBeginners({ status: 'failed', result: { deployment_evaluations: [] } })
  const scan = summarizeBondScanForBeginners({ status: 'completed', result: { scientific_vqe_discrete_minimum: null } })
  assert.equal(study.status, '未完成')
  assert.equal(scan.confidence, '没有通过科学验证的离散候选点')
  assert.equal(scan.keyResult, '尚无通过科学验证的离散候选距离')
})
