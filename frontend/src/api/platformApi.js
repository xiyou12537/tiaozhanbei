import apiClient from './index'

export function fetchPlatformHealth() {
  return apiClient.get('/health')
}

export function fetchPlatformCases() {
  return apiClient.get('/platform/cases')
}

export function fetchPlatformCandidates() {
  return apiClient.get('/platform/candidates')
}

export function createPlatformWorkflow(payload) {
  return apiClient.post('/platform/workflows', payload)
}

export function createScreeningWorkflow(payload) {
  return apiClient.post('/platform/screening-workflows', payload)
}

export function fetchPlatformWorkflow(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}`)
}

export function fetchScreeningWorkflow(workflowId) {
  return apiClient.get(`/platform/screening-workflows/${workflowId}`)
}

export function fetchScreeningWorkflows() {
  return apiClient.get('/platform/screening-workflows')
}

export function fetchPlatformWorkflowStages(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/stages`)
}

export function fetchPlatformWorkflowEvents(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/events`)
}

export function fetchPlatformWorkflowResult(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/result`)
}

export function fetchPlatformWorkflowSummary(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/summary`)
}

export function fetchPlatformWorkflowArtifacts(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/artifacts`)
}

export function fetchClassicalScreening(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/classical-screening`)
}

export function fetchQuantumRefinement(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/quantum-refinement`)
}

export function fetchScreeningLeaderboard(workflowId) {
  return apiClient.get(`/platform/workflows/${workflowId}/leaderboard`)
}

export function fetchCandidateExplanation(workflowId, materialId) {
  return apiClient.get(`/platform/workflows/${workflowId}/candidate-explanations/${materialId}`)
}

export function cancelPlatformWorkflow(workflowId) {
  return apiClient.post(`/platform/workflows/${workflowId}/cancel`)
}

export function uploadStructureFile(formData, idempotencyKey) {
  return apiClient.post('/platform/structure-files', formData, {
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function parseStructureFile(fileId) {
  return apiClient.post(`/platform/structure-files/${fileId}/parse`)
}

export function fetchStructureFile(fileId) {
  return apiClient.get(`/platform/structure-files/${fileId}`)
}

export function fetchStructure(structureId, includeAtomicSites = true) {
  return apiClient.get(`/platform/structures/${structureId}`, {
    params: { include_atomic_sites: includeAtomicSites },
  })
}

export function suggestStructureActiveSites(structureId) {
  return apiClient.post(`/platform/structures/${structureId}/active-sites/suggest`)
}

export function confirmStructureActiveSite(structureId, payload) {
  return apiClient.post(`/platform/structures/${structureId}/active-sites/confirm`, payload)
}

export function createAdsorptionModels(activeSiteId, payload) {
  return apiClient.post(`/platform/active-sites/${activeSiteId}/adsorption-models`, payload)
}

export function createGeometryOptimization(adsorptionModelId, payload) {
  return apiClient.post(`/platform/adsorption-models/${adsorptionModelId}/geometry-optimizations`, payload)
}

export function importDftResult(adsorptionModelId, payload) {
  return apiClient.post(`/platform/adsorption-models/${adsorptionModelId}/dft-imports`, payload)
}

export function createQuantumRegion(adsorptionModelId, payload) {
  return apiClient.post(`/platform/adsorption-models/${adsorptionModelId}/quantum-regions`, payload)
}

export function createElectronicStructureCandidates(quantumRegionId, payload) {
  return apiClient.post(`/platform/quantum-regions/${quantumRegionId}/electronic-structure-candidates`, payload)
}

export function fetchElectronicStructureCandidate(candidateId) {
  return apiClient.get(`/platform/electronic-structure-candidates/${candidateId}`)
}

export function confirmElectronicStructureCandidate(candidateId, payload = {}) {
  return apiClient.post(`/platform/electronic-structure-candidates/${candidateId}/confirm`, payload)
}

export function queueActiveSpaceCandidates(quantumRegionId) {
  return apiClient.post(`/platform/quantum-regions/${quantumRegionId}/active-space-candidates/queued`)
}

export function fetchStructureTask(taskId) {
  return apiClient.get(`/platform/structure-tasks/${taskId}`)
}

export function confirmActiveSpace(quantumRegionId, activeSpaceId) {
  return apiClient.post(`/platform/quantum-regions/${quantumRegionId}/active-space-confirm`, {
    active_space_id: activeSpaceId,
  })
}

export function createFermionicHamiltonian(activeSpaceId) {
  return apiClient.post(`/platform/active-spaces/${activeSpaceId}/fermionic-hamiltonians`)
}

export function createQubitMapping(hamiltonianId, payload) {
  return apiClient.post(`/platform/fermionic-hamiltonians/${hamiltonianId}/qubit-mappings`, payload)
}

export function createVqeCircuit(qubitHamiltonianId, payload) {
  return apiClient.post(`/platform/qubit-hamiltonians/${qubitHamiltonianId}/vqe-circuits`, payload)
}

export function executeVqeCircuit(vqeCircuitId) {
  return apiClient.post(`/platform/vqe-circuits/${vqeCircuitId}/executions`)
}

export function fetchVqeExecution(executionId) {
  return apiClient.get(`/platform/vqe-executions/${executionId}`)
}

export function fetchStructureWorkflow(workflowId) {
  return apiClient.get(`/platform/structure-screening-workflows/${workflowId}`)
}

export function fetchResearchBenchmarks(benchmarkKey) {
  return apiClient.get('/platform/research-benchmarks', {
    params: benchmarkKey ? { benchmark_key: benchmarkKey } : undefined,
  })
}

export function fetchResearchBenchmark(benchmarkId) {
  return apiClient.get(`/platform/research-benchmarks/${benchmarkId}`)
}

export function fetchResearchBenchmarkCandidates(benchmarkId) {
  return apiClient.get(`/platform/research-benchmarks/${benchmarkId}/candidates`)
}

export function fetchResearchBenchmarkCandidateArtifact(benchmarkId, candidateId) {
  return apiClient.get(`/platform/research-benchmarks/${benchmarkId}/candidates/${candidateId}/artifact`)
}

export function selectResearchBenchmarkCandidate(benchmarkId, candidateId) {
  return apiClient.post(`/platform/research-benchmarks/${benchmarkId}/candidates/${candidateId}/select`)
}

export function importMaterialsCloudResearchBenchmark() {
  return apiClient.post('/platform/research-benchmarks/import-materials-cloud', {
    benchmark_key: 'fe-n4-c66-li2s4-literature-v1',
    dataset_url: 'https://archive.materialscloud.org/records/f5t2r-6qf35',
    source_license: 'CC-BY-4.0',
    adsorbate: 'Li2S4',
    retain_raw_artifacts: true,
  })
}

export function fetchStructureWorkflowArtifact(workflowId, artifactId) {
  return apiClient.get(`/platform/structure-screening-workflows/${workflowId}/artifacts/${artifactId}`)
}

export function downloadStructureWorkflowArtifact(workflowId, artifactId) {
  return apiClient.get(
    `/platform/structure-screening-workflows/${workflowId}/artifacts/${artifactId}/download`,
    { responseType: 'blob' }
  )
}
