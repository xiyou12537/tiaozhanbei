import apiClient from './index.js'
import { shouldRedirectUnauthorized } from './authRedirectPolicy.js'
import { clearAuthSession, readToken } from '../services/authStorage.js'
import { consumeAssistantSse } from '../services/assistantSseService.js'

export class AssistantRequestError extends Error {
  constructor({ status, code, message }) {
    super(message || 'Copilot 请求失败。')
    this.status = status
    this.code = code
  }
}

export async function createAssistantSession(title = null) {
  const response = await apiClient.post('/assistant/sessions', title ? { title } : {})
  return response.data
}

export async function getAssistantSession(sessionId) {
  const response = await apiClient.get(`/assistant/sessions/${encodeURIComponent(sessionId)}`)
  return response.data
}

export async function confirmAssistantTool(sessionId, confirmation) {
  const response = await apiClient.post(`/assistant/sessions/${encodeURIComponent(sessionId)}/tool-confirmations`, confirmation)
  return response.data
}

export async function streamAssistantMessage(sessionId, message, options = {}) {
  const fetchImpl = options.fetchImpl || fetch
  const token = options.token ?? readToken()
  const response = await fetchImpl(`/api/assistant/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ message }),
    signal: options.signal,
  })
  if (!response.ok) {
    const error = await assistantResponseError(response)
    if (error.status === 401) redirectUnauthorized('/assistant/sessions')
    throw error
  }
  if (!response.body) throw new AssistantRequestError({ status: 0, code: 'assistant_stream_unavailable', message: 'Copilot 流式响应不可用。' })
  await consumeAssistantSse(response.body, options.onEvent)
}

async function assistantResponseError(response) {
  let detail = {}
  try { detail = (await response.json())?.detail || {} } catch {}
  return new AssistantRequestError({ status: response.status, code: detail.code, message: detail.message })
}

function redirectUnauthorized(url) {
  const token = readToken()
  if (!shouldRedirectUnauthorized({ status: 401, url, currentPath: window.location.pathname, hasToken: Boolean(token) })) return
  clearAuthSession()
  const redirect = `${window.location.pathname}${window.location.search}`
  window.location.href = `/auth?tab=login&redirect=${encodeURIComponent(redirect)}`
}
