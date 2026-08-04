import axios from 'axios'
import { clearAuthSession, readToken } from '../services/authStorage'
import { shouldRedirectUnauthorized } from './authRedirectPolicy'

const apiClient = axios.create({ baseURL: '/api' })

apiClient.interceptors.request.use((config) => {
  const token = readToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const token = readToken()
    const shouldRedirect = shouldRedirectUnauthorized({
      status: error.response?.status,
      url: error.config?.url || '',
      currentPath: window.location.pathname,
      hasToken: Boolean(token),
    })

    if (shouldRedirect) {
      clearAuthSession()
      const redirect = `${window.location.pathname}${window.location.search}`
      const authUrl = `/auth?tab=login&redirect=${encodeURIComponent(redirect)}`
      window.location.href = authUrl
    }
    return Promise.reject(error)
  }
)

export default apiClient
