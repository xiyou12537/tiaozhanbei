const TOKEN_KEY = 'token'
const USER_KEY = 'user'

export function readToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function readUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || '{}')
  } catch {
    return {}
  }
}

export function saveAuthSession(payload) {
  localStorage.setItem(TOKEN_KEY, payload.token)
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({
      id: payload.user_id,
      username: payload.username,
    })
  )
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function hasAuthSession() {
  return !!readToken()
}
