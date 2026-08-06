import apiClient from './index'

export function uploadCircuit(qasmContent) {
  return apiClient.post('/circuit/upload', { qasm_content: qasmContent })
}

export function fetchCircuitInfo(circuitId) {
  return apiClient.get(`/circuit/info/${circuitId}`)
}

export function runPartitionTask(params) {
  return apiClient.post('/partition/run', params)
}

export function fetchPartitionTaskStatus(taskId) {
  return apiClient.get(`/partition/status/${taskId}`)
}

export function fetchPartitionTaskResult(taskId) {
  return apiClient.get(`/partition/result/${taskId}`)
}

export function fetchTopologyPresets() {
  return apiClient.get('/mapping/topology-presets')
}

export function findTopologyMapping(taskId, topologyEdges) {
  return apiClient.post('/mapping/find', { task_id: taskId, topology_edges: topologyEdges })
}

export function compareTopologyMappings(taskId, topologies) {
  return apiClient.post('/mapping/compare', { task_id: taskId, topologies })
}

export function fetchPartitionGraphData(taskId) {
  return apiClient.get(`/export/graph-data/${taskId}`)
}

export function getPartitionGraphPngUrl(taskId) {
  return `/api/export/graph/${taskId}/png`
}

export function getReportDownloadUrl(taskId) {
  return `/api/export/report/${taskId}/download`
}
