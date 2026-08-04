import apiClient from './index'

export function fetchChatHistory() {
  return apiClient.get('/chat/history')
}

export function clearChatHistoryApi() {
  return apiClient.delete('/chat/clear')
}
