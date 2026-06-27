import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 请求拦截器：自动带上 JWT Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：401 时跳转到登录页
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/?auth=login'
    }
    return Promise.reject(err)
  }
)

// ── 认证 ──
export const register = (username, password) => api.post('/auth/register', { username, password })
export const login = (username, password) => api.post('/auth/login', { username, password })
export const getMe = () => api.get('/auth/me')

// ── 电路 ──
export const uploadCircuit = (qasm) => api.post('/circuit/upload', { qasm_content: qasm })
export const getCircuitInfo = (id) => api.get(`/circuit/info/${id}`)

// ── 分区 ──
export const runPartition = (params) => api.post('/partition/run', params)
export const getTaskStatus = (taskId) => api.get(`/partition/status/${taskId}`)
export const getPartitionResult = (taskId) => api.get(`/partition/result/${taskId}`)

// ── 芯片映射 ──
export const getTopologyPresets = () => api.get('/mapping/topology-presets')
export const findMapping = (taskId, edges) => api.post('/mapping/find', { task_id: taskId, topology_edges: edges })
export const compareTopologies = (taskId, topologies) => api.post('/mapping/compare', { task_id: taskId, topologies })

// ── 可视化数据 ──
export const getGraphData = (taskId) => api.get(`/export/graph-data/${taskId}`)

// ── 导出 ──
export const getPartitionGraphPngUrl = (taskId) => `/api/export/graph/${taskId}/png`
export const getReportDownloadUrl = (taskId) => `/api/export/report/${taskId}/download`

// ── AI 对话 ──
export const getChatHistory = () => api.get('/chat/history')
export const clearChatHistory = () => api.delete('/chat/clear')

export default api
