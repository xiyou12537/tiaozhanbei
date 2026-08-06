import {
  createScreeningWorkflow,
  fetchCandidateExplanation as fetchCandidateExplanationApi,
  fetchClassicalScreening,
  fetchPlatformCandidates,
  fetchQuantumRefinement,
  fetchScreeningLeaderboard as fetchScreeningLeaderboardApi,
  fetchScreeningWorkflow,
  fetchScreeningWorkflows,
} from '../api/platformApi'
import { mapCandidates } from './workflowMappers'
import {
  buildScreeningCreatePayload,
  mapClassicalScreeningRows,
  mapExplanation,
  mapLeaderboardRows,
  mapQuantumRefinementRows,
  mapScreeningCreateResponse,
  mapScreeningWorkflow,
  mapScreeningWorkflowHistory,
} from './screeningWorkflowMappers'

export async function fetchScreeningCandidates() {
  const { data } = await fetchPlatformCandidates()
  return mapCandidates(data || []).map(item => ({
    ...item,
    materialId: item.materialId || item.raw?.material_id || '',
    materialName: item.materialName || item.raw?.material_name || item.name,
    materialFamily: item.materialFamily || item.raw?.material_family || item.family,
    activeSite: item.raw?.active_site || '',
  }))
}

export async function submitScreeningWorkflow(payload) {
  const { data } = await createScreeningWorkflow(buildScreeningCreatePayload(payload))
  return mapScreeningCreateResponse(data)
}

export async function fetchScreeningWorkflowBundle(workflowId) {
  const { data } = await fetchScreeningWorkflow(workflowId)
  return mapScreeningWorkflow(data)
}

export async function fetchScreeningStageBundle(workflowId) {
  const [classicalResult, quantumResult, leaderboardResult] = await Promise.allSettled([
    fetchClassicalScreening(workflowId),
    fetchQuantumRefinement(workflowId),
    fetchScreeningLeaderboardApi(workflowId),
  ])

  return {
    classicalScreening:
      classicalResult.status === 'fulfilled'
        ? mapClassicalScreeningRows(classicalResult.value.data?.results || [])
        : [],
    quantumRefinement:
      quantumResult.status === 'fulfilled'
        ? mapQuantumRefinementRows(quantumResult.value.data?.results || [])
        : [],
    leaderboard:
      leaderboardResult.status === 'fulfilled'
        ? mapLeaderboardRows(leaderboardResult.value.data?.leaderboard || [])
        : [],
    recommendedMaterial:
      leaderboardResult.status === 'fulfilled'
        ? leaderboardResult.value.data?.recommended_material || ''
        : '',
  }
}

export async function fetchScreeningLeaderboard(workflowId) {
  const { data } = await fetchScreeningLeaderboardApi(workflowId)
  return {
    workflowId: data.workflow_id,
    candidateCount: data.candidate_count,
    recommendedMaterial: data.recommended_material,
    leaderboard: mapLeaderboardRows(data.leaderboard || []),
  }
}

export async function fetchScreeningWorkflowHistory() {
  const { data } = await fetchScreeningWorkflows()
  return mapScreeningWorkflowHistory(data || [])
}

export async function fetchCandidateExplanation(workflowId, materialId) {
  const { data } = await fetchCandidateExplanationApi(workflowId, materialId)
  return {
    workflowId: data.workflow_id,
    candidateMaterial: data.candidate_material,
    explanation: mapExplanation(data.explanation || {}),
  }
}
