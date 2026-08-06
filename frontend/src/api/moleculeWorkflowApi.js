import apiClient from './index.js'

export const MOLECULE_WORKFLOW_TIMEOUT_MS = 15 * 60 * 1000

export function createMoleculeWorkflowRequest(payload, idempotencyKey) {
  return apiClient.post('/molecule-workflows', payload, {
    headers: { 'Idempotency-Key': idempotencyKey },
    timeout: MOLECULE_WORKFLOW_TIMEOUT_MS,
    skipAuthRedirect: true,
  })
}

export function fetchMoleculeWorkflowRequest(workflowId) {
  return apiClient.get(`/molecule-workflows/${encodeURIComponent(workflowId)}`, {
    skipAuthRedirect: true,
  })
}

export function fetchMoleculeWorkflowHistoryRequest(params) {
  return apiClient.get('/molecule-workflows', {
    params,
    skipAuthRedirect: true,
  })
}

export function fetchMoleculeWorkflowCapabilitiesRequest() {
  return apiClient.get('/molecule-workflows/capabilities', {
    skipAuthRedirect: true,
  })
}
