import apiClient from './api/index'

export { registerUser as register, loginUser as login, fetchCurrentUser as getMe } from './api/authApi'
export {
  uploadCircuit,
  fetchCircuitInfo as getCircuitInfo,
  runPartitionTask as runPartition,
  fetchPartitionTaskStatus as getTaskStatus,
  fetchPartitionTaskResult as getPartitionResult,
  fetchTopologyPresets as getTopologyPresets,
  findTopologyMapping as findMapping,
  compareTopologyMappings as compareTopologies,
  fetchPartitionGraphData as getGraphData,
  getPartitionGraphPngUrl,
  getReportDownloadUrl,
} from './api/capabilityApi'
export {
  fetchPlatformCases,
  fetchPlatformCandidates,
  createPlatformWorkflow,
  fetchPlatformWorkflow,
  fetchPlatformWorkflowStages,
  fetchPlatformWorkflowEvents,
  fetchPlatformWorkflowResult,
  fetchPlatformWorkflowSummary,
  fetchPlatformWorkflowArtifacts,
  cancelPlatformWorkflow,
} from './api/platformApi'
export { fetchUserHistory } from './api/historyApi'
export { fetchChatHistory as getChatHistory, clearChatHistoryApi as clearChatHistory } from './api/chatApi'

export default apiClient
