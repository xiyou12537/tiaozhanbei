import { computed, reactive } from 'vue'
import { fetchCurrentUser, loginUser, registerUser } from '../api/authApi'
import {
  clearAuthSession,
  hasAuthSession,
  readToken,
  readUser,
  saveAuthSession,
} from '../services/authStorage'

const authState = reactive({
  token: readToken(),
  user: readUser(),
  loading: false,
})

export function useAuth() {
  const isLoggedIn = computed(() => !!authState.token)
  const username = computed(() => authState.user?.username || '用户')

  async function login(usernameValue, password) {
    authState.loading = true
    try {
      const { data } = await loginUser(usernameValue, password)
      saveAuthSession(data)
      authState.token = data.token
      authState.user = { id: data.user_id, username: data.username }
      return data
    } finally {
      authState.loading = false
    }
  }

  async function register(usernameValue, password) {
    authState.loading = true
    try {
      const { data } = await registerUser(usernameValue, password)
      saveAuthSession(data)
      authState.token = data.token
      authState.user = { id: data.user_id, username: data.username }
      return data
    } finally {
      authState.loading = false
    }
  }

  async function refreshUser() {
    if (!hasAuthSession()) return null
    const { data } = await fetchCurrentUser()
    authState.user = {
      id: data.user_id,
      username: data.username,
      created_at: data.created_at,
    }
    return data
  }

  function logout() {
    clearAuthSession()
    authState.token = ''
    authState.user = {}
  }

  return {
    authState,
    isLoggedIn,
    username,
    login,
    register,
    refreshUser,
    logout,
  }
}
