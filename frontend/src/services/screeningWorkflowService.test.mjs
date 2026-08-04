import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildScreeningCreatePayload,
  mapExplanation,
  mapScreeningWorkflowHistory,
} from './screeningWorkflowMappers.js'

test('buildScreeningCreatePayload omits deprecated execution_mode', () => {
  const payload = buildScreeningCreatePayload({
    caseId: 'li-s-demo',
    candidateMaterials: ['Fe-N4/C', 'Co-N4/C', 'MoS2'],
    executionMode: 'sync',
  })

  assert.deepEqual(payload, {
    case_id: 'li-s-demo',
    candidate_materials: ['Fe-N4/C', 'Co-N4/C', 'MoS2'],
  })
  assert.equal(Object.hasOwn(payload, 'execution_mode'), false)
})

test('mapExplanation includes enhanced explanation fields', () => {
  const explanation = mapExplanation({
    candidate_material: 'Co-N4/C',
    recommendation_reason: 'Top final score.',
    risk_notes: ['Validate synthesis.'],
    score_breakdown: {
      classical_screening_score: 85,
      quantum_refine_score: 88,
    },
    evidence_source_summary: {
      distributed_execution: 'simulator_output',
    },
    model_limitations: ['Demo Hamiltonian.'],
    next_validation_step: 'Run DFT validation.',
    key_evidence: {
      distributed_execution: {
        subcircuits: [{ subcircuit_id: 'sub-1' }, { subcircuit_id: 'sub-2' }],
        estimated_runtime: 3.42,
      },
    },
  })

  assert.equal(explanation.candidateMaterial, 'Co-N4/C')
  assert.equal(explanation.scoreBreakdown.quantum_refine_score, 88)
  assert.equal(explanation.evidenceSourceSummary.distributed_execution, 'simulator_output')
  assert.deepEqual(explanation.modelLimitations, ['Demo Hamiltonian.'])
  assert.equal(explanation.nextValidationStep, 'Run DFT validation.')
})

test('mapScreeningWorkflowHistory maps backend list fields for history page', () => {
  const history = mapScreeningWorkflowHistory([
    {
      workflow_id: 'wf-001',
      case_id: 'li-s-demo',
      status: 'completed',
      candidate_count: 3,
      recommended_material: 'Co-N4/C',
      created_at: '2026-07-06T09:00:00',
      updated_at: '2026-07-06T09:01:00',
    },
  ])

  assert.deepEqual(history[0], {
    workflowId: 'wf-001',
    caseId: 'li-s-demo',
    status: 'completed',
    candidateCount: 3,
    recommendedMaterial: 'Co-N4/C',
    createdAt: '2026-07-06T09:00:00',
    updatedAt: '2026-07-06T09:01:00',
    selectedCandidates: [],
    source: 'backend',
  })
})
