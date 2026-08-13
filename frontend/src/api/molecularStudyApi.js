import apiClient from './index.js'

export function createMolecularStudyRequest(payload) {
  return apiClient.post('/molecular-studies', payload, { skipAuthRedirect: true })
}

export function fetchMolecularStudyRequest(studyId) {
  return apiClient.get(`/molecular-studies/${encodeURIComponent(studyId)}`, { skipAuthRedirect: true })
}
