import {
  cancelPlatformWorkflow,
  createPlatformWorkflow,
  fetchPlatformCandidates,
  fetchPlatformCases,
  fetchPlatformHealth,
  fetchPlatformWorkflow,
  fetchPlatformWorkflowArtifacts,
  fetchPlatformWorkflowEvents,
  fetchPlatformWorkflowResult,
  fetchPlatformWorkflowStages,
  fetchPlatformWorkflowSummary,
} from '../api/platformApi'
import {
  mapArtifacts,
  mapCases,
  mapCandidates,
  mapEventLogs,
  mapResultView,
  mapStageRuns,
  mapSummary,
} from './workflowMappers'

export async function fetchWorkflowBootstrap() {
  const [healthResult, caseResult, candidateResult] = await Promise.allSettled([
    fetchPlatformHealth(),
    fetchPlatformCases(),
    fetchPlatformCandidates(),
  ])

  const payload = {
    health: null,
    version: '',
    cases: [],
    candidates: [],
    apiReady: true,
    errors: [],
  }

  if (healthResult.status === 'fulfilled') {
    payload.health = healthResult.value.data || null
    payload.version = healthResult.value.data?.version || ''
  } else {
    payload.apiReady = false
    payload.errors.push(healthResult.reason)
  }

  if (caseResult.status === 'fulfilled') {
    payload.cases = mapCases(caseResult.value.data || [])
  } else {
    payload.apiReady = false
    payload.errors.push(caseResult.reason)
  }

  if (candidateResult.status === 'fulfilled') {
    payload.candidates = mapCandidates(candidateResult.value.data || [])
  } else {
    payload.apiReady = false
    payload.errors.push(candidateResult.reason)
  }

  return payload
}

export async function submitWorkflow(payload) {
  const { data } = await createPlatformWorkflow(payload)
  return data
}

export async function fetchWorkflowBundle(workflowId) {
  const [detailRes, stagesRes, eventsRes, summaryRes, resultRes, artifactsRes] = await Promise.allSettled([
    fetchPlatformWorkflow(workflowId),
    fetchPlatformWorkflowStages(workflowId),
    fetchPlatformWorkflowEvents(workflowId),
    fetchPlatformWorkflowSummary(workflowId),
    fetchPlatformWorkflowResult(workflowId),
    fetchPlatformWorkflowArtifacts(workflowId),
  ])

  if (detailRes.status !== 'fulfilled') {
    throw detailRes.reason
  }

  const bundle = {
    detail: detailRes.value.data,
    stages: stagesRes.status === 'fulfilled' ? mapStageRuns(stagesRes.value.data || []) : [],
    events: eventsRes.status === 'fulfilled' ? mapEventLogs(eventsRes.value.data || []) : [],
    summary: summaryRes.status === 'fulfilled' ? mapSummary(summaryRes.value.data) : null,
    resultView: resultRes.status === 'fulfilled' ? mapResultView(resultRes.value.data) : null,
    artifacts: artifactsRes.status === 'fulfilled' ? mapArtifacts(artifactsRes.value.data) : null,
  }

  return bundle
}

export async function cancelWorkflow(workflowId) {
  const { data } = await cancelPlatformWorkflow(workflowId)
  return data
}
