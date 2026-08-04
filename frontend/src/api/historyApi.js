import apiClient from './index'

export function fetchUserHistory() {
  return apiClient.get('/user/history')
}
