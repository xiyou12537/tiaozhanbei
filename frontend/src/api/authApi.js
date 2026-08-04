import apiClient from './index'

export function registerUser(username, password) {
  return apiClient.post('/auth/register', { username, password })
}

export function loginUser(username, password) {
  return apiClient.post('/auth/login', { username, password })
}

export function fetchCurrentUser() {
  return apiClient.get('/auth/me')
}
