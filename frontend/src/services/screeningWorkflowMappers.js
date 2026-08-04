export function buildScreeningCreatePayload(payload) {
  return {
    case_id: payload.caseId || 'li-s-demo',
    candidate_materials: payload.candidateMaterials,
  }
}

export function mapScreeningCreateResponse(data = {}) {
  return {
    workflowId: data.workflow_id || '',
    caseId: data.case_id || '',
    status: data.status || 'created',
    candidateCount: data.candidate_count || 0,
    recommendedMaterial: data.recommended_material || '',
    createdAt: data.created_at || '',
    updatedAt: data.updated_at || '',
  }
}

export function mapScreeningWorkflow(data = {}) {
  return {
    workflowId: data.workflow_id || '',
    caseId: data.case_id || '',
    status: data.status || 'unknown',
    candidateCount: data.candidate_count || 0,
    candidateResults: mapCandidateResults(data.candidate_results || []),
    classicalScreening: mapClassicalScreeningRows(data.classical_screening || []),
    quantumRefinement: mapQuantumRefinementRows(data.quantum_refinement || []),
    explanations: mapExplanationMap(data.explanations || {}),
    leaderboard: mapLeaderboardRows(data.leaderboard || []),
    recommendedMaterial: data.recommended_material || '',
    createdAt: data.created_at || '',
    updatedAt: data.updated_at || '',
    raw: data,
  }
}

export function mapScreeningWorkflowHistory(rows = []) {
  return rows.map(item => ({
    workflowId: item.workflow_id || '',
    caseId: item.case_id || '',
    status: item.status || 'unknown',
    candidateCount: Number(item.candidate_count || 0),
    recommendedMaterial: item.recommended_material || '',
    createdAt: item.created_at || '',
    updatedAt: item.updated_at || '',
    selectedCandidates: [],
    source: 'backend',
  }))
}

export function mapClassicalScreeningRows(rows = []) {
  return rows.map(item => ({
    candidateMaterial: item.candidate_material || '',
    materialProfile: mapMaterialProfile(item.material_profile || {}),
    screening: item.screening || {},
    raw: item,
  }))
}

export function mapQuantumRefinementRows(rows = []) {
  return rows.map(item => ({
    candidateMaterial: item.candidate_material || '',
    chemistryModel: item.chemistry_model || {},
    quantumProblem: item.quantum_problem || {},
    distributedExecution: item.distributed_execution || {},
    quantumRefinement: item.quantum_refinement || {},
    raw: item,
  }))
}

export function mapLeaderboardRows(rows = []) {
  return rows.map(item => ({
    candidateMaterial: item.candidate_material || '',
    score: item.score || {},
    explanation: mapExplanation(item.explanation || {}),
    raw: item,
  }))
}

export function mapExplanation(explanation = {}) {
  return {
    candidateMaterial: explanation.candidate_material || '',
    recommendationReason: explanation.recommendation_reason || '',
    riskNotes: Array.isArray(explanation.risk_notes) ? explanation.risk_notes : [],
    scoreBreakdown: explanation.score_breakdown || {},
    evidenceSourceSummary: explanation.evidence_source_summary || {},
    modelLimitations: Array.isArray(explanation.model_limitations) ? explanation.model_limitations : [],
    nextValidationStep: explanation.next_validation_step || '',
    keyEvidence: explanation.key_evidence || {},
    raw: explanation,
  }
}

function mapCandidateResults(rows = []) {
  return rows.map(item => ({
    candidateMaterial: item.candidate_material || '',
    materialProfile: mapMaterialProfile(item.material_profile || {}),
    screening: item.screening || {},
    chemistryModel: item.chemistry_model || {},
    quantumProblem: item.quantum_problem || {},
    distributedExecution: item.distributed_execution || {},
    quantumRefinement: item.quantum_refinement || {},
    score: item.score || {},
    explanation: mapExplanation(item.explanation || {}),
    raw: item,
  }))
}

function mapExplanationMap(explanations = {}) {
  return Object.fromEntries(
    Object.entries(explanations).map(([materialId, explanation]) => [materialId, mapExplanation(explanation || {})])
  )
}

function mapMaterialProfile(profile = {}) {
  return {
    materialId: profile.material_id || '',
    materialName: profile.material_name || '',
    materialFamily: profile.material_family || '',
    activeSite: profile.active_site || '',
    sourceReference: profile.source_reference || '',
    raw: profile,
  }
}
