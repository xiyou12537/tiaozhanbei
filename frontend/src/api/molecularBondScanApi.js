import apiClient from './index.js'

export function fetchMolecularBondScanCapabilitiesRequest() {
  return apiClient.get('/molecular-bond-scans/capabilities', { skipAuthRedirect: true })
}

export function createMolecularBondScanRequest(payload, idempotencyKey) {
  return apiClient.post('/molecular-bond-scans', payload, {
    headers: { 'Idempotency-Key': idempotencyKey },
    skipAuthRedirect: true,
  })
}

export function fetchMolecularBondScanRequest(scanId) {
  return apiClient.get(`/molecular-bond-scans/${encodeURIComponent(scanId)}`, { skipAuthRedirect: true })
}
