const AUTH_ENDPOINTS = ['/auth/login', '/auth/register']

export function shouldRedirectUnauthorized({ status, url = '', currentPath = '', hasToken = false }) {
  if (status !== 401) return false
  if (AUTH_ENDPOINTS.some(endpoint => url.includes(endpoint))) return false
  if (currentPath.startsWith('/auth')) return false
  return hasToken
}
