import apiClient from './index'

export function fetchKnowledgeDocuments() {
  return apiClient.get('/knowledge/documents')
}

export function fetchKnowledgeStats() {
  return apiClient.get('/knowledge/stats')
}

export function fetchKnowledgeAnalytics() {
  return apiClient.get('/knowledge/analytics')
}

export function searchKnowledge(payload) {
  return apiClient.post('/knowledge/search', payload)
}
