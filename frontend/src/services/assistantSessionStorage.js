const STORAGE_PREFIX = 'molecular-copilot:recent-session:'

function storageKey(user) {
  const userId = user?.id
  return userId === null || userId === undefined || userId === '' ? '' : `${STORAGE_PREFIX}${userId}`
}

export function readRecentAssistantSession(user) {
  const key = storageKey(user)
  return key ? localStorage.getItem(key) || '' : ''
}

export function saveRecentAssistantSession(user, sessionId) {
  const key = storageKey(user)
  if (!key || !sessionId) return
  localStorage.setItem(key, sessionId)
}

export function clearRecentAssistantSession(user) {
  const key = storageKey(user)
  if (key) localStorage.removeItem(key)
}
