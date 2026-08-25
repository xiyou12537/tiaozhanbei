const STORAGE_PREFIX = 'molecular-copilot:pending-draft:'
const DRAFT_VERSION = 1
const DRAFT_MAX_AGE_MS = 15 * 60 * 1000
const TASK_TYPES = new Set(['molecule_workflow', 'molecular_study', 'molecular_bond_scan'])
const TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$/

const taskLabels = {
  molecule_workflow: 'Workflow',
  molecular_study: 'Molecular Study',
  molecular_bond_scan: 'LiH Bond Scan',
}

const userFacingTaskLabels = {
  molecule_workflow: '单次分子计算',
  molecular_study: '方案比较',
  molecular_bond_scan: 'LiH 键长扫描',
}

function userId(user) {
  return user?.id === null || user?.id === undefined || user?.id === '' ? '' : String(user.id)
}

function validTaskId(taskId) {
  return typeof taskId === 'string' && TASK_ID_PATTERN.test(taskId)
}

function createDraft({ source, taskType = null, taskId = null, message }) {
  return { version: DRAFT_VERSION, source, taskType, taskId, message, createdAt: Date.now() }
}

export function pendingCopilotStorageKey(user) {
  const id = userId(user)
  return id ? `${STORAGE_PREFIX}${id}` : ''
}

export function copilotTaskTypeLabel(taskType) {
  return userFacingTaskLabels[taskType] || ''
}

export function createCopilotSelectionDraft() {
  return createDraft({
    source: 'workbench',
    message: '我不懂，帮我选择计算方式。请用通俗中文比较单次分子计算、方案比较和 LiH 键长扫描分别适合解决什么问题；请先解释，不要创建任务。',
  })
}

export function createCopilotSettingsDraft(taskType) {
  const messages = {
    molecule_workflow: '我不懂这些分子计算设置。请用通俗中文解释推荐配置，以及什么时候需要打开高级设置；请不要创建任务。',
    molecular_study: '我想比较不同方案，但不懂分区、连接、拓扑和路由。请用通俗中文解释推荐配置和何时修改高级设置；请不要创建任务。',
    molecular_bond_scan: '我想做 LiH 键长扫描，但不懂范围、间隔和架构。请用通俗中文解释推荐配置和什么时候修改高级设置；请不要创建任务。',
  }
  return TASK_TYPES.has(taskType) ? createDraft({ source: 'settings', taskType, message: messages[taskType] }) : null
}

export function createCopilotResultDraft(taskType, taskId) {
  if (!TASK_TYPES.has(taskType) || !validTaskId(taskId)) return null
  const label = taskLabels[taskType]
  return createDraft({
    source: 'result', taskType, taskId,
    message: `请解释我的 ${label} 结果（${label} ID：${taskId}）。请先说明任务是否完成、最重要结果、可信度或复核原因和下一步；请只读取我有权限的紧凑结果摘要。`,
  })
}

function isValidDraft(draft, now) {
  if (!draft || typeof draft !== 'object' || draft.version !== DRAFT_VERSION) return false
  if (!Object.keys(draft).every(key => ['version', 'source', 'taskType', 'taskId', 'message', 'createdAt'].includes(key))) return false
  if (typeof draft.message !== 'string' || !draft.message.trim() || draft.message.length > 1200) return false
  if (!Number.isFinite(draft.createdAt) || draft.createdAt > now || now - draft.createdAt > DRAFT_MAX_AGE_MS) return false
  if (draft.source === 'workbench') return draft.taskType === null && draft.taskId === null
  if (draft.source === 'settings') return TASK_TYPES.has(draft.taskType) && draft.taskId === null
  return draft.source === 'result' && TASK_TYPES.has(draft.taskType) && validTaskId(draft.taskId)
}

export function savePendingCopilotDraft(user, draft) {
  const key = pendingCopilotStorageKey(user)
  if (!key || !isValidDraft(draft, Date.now())) return false
  localStorage.setItem(key, JSON.stringify(draft))
  return true
}

export function consumePendingCopilotDraft(user, { now = Date.now() } = {}) {
  const key = pendingCopilotStorageKey(user)
  if (!key) return null
  const raw = localStorage.getItem(key)
  if (!raw) return null
  localStorage.removeItem(key)
  try {
    const draft = JSON.parse(raw)
    return isValidDraft(draft, now) ? draft : null
  } catch {
    return null
  }
}
