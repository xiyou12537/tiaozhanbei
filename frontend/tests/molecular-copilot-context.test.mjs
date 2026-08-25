import assert from 'node:assert/strict'
import test from 'node:test'
import {
  consumePendingCopilotDraft,
  copilotTaskTypeLabel,
  createCopilotResultDraft,
  createCopilotSelectionDraft,
  createCopilotSettingsDraft,
  pendingCopilotStorageKey,
  savePendingCopilotDraft,
} from '../src/services/assistantCopilotContext.js'

test('Copilot 内部任务类型始终映射为面向用户的通俗名称', () => {
  assert.equal(copilotTaskTypeLabel('molecule_workflow'), '单次分子计算')
  assert.equal(copilotTaskTypeLabel('molecular_study'), '方案比较')
  assert.equal(copilotTaskTypeLabel('molecular_bond_scan'), 'LiH 键长扫描')
  assert.equal(copilotTaskTypeLabel('unknown_task_type'), '')
})

function installStorage() {
  const values = new Map()
  globalThis.localStorage = {
    getItem: key => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  }
  return values
}

test('Copilot 场景草稿只生成可编辑的通俗问题，不携带结果对象', () => {
  const selection = createCopilotSelectionDraft()
  const result = createCopilotResultDraft('molecular_study', 'study-42')
  const settings = createCopilotSettingsDraft('molecular_bond_scan')

  assert.match(selection.message, /我不懂，帮我选择计算方式/)
  assert.match(result.message, /Molecular Study ID：study-42/)
  assert.match(result.message, /紧凑结果摘要/)
  assert.match(settings.message, /范围、间隔和架构/)
  assert.deepEqual(Object.keys(result).sort(), ['createdAt', 'message', 'source', 'taskId', 'taskType', 'version'])
  assert.equal(JSON.stringify(result).includes('qasm'), false)
  assert.equal(JSON.stringify(result).includes('routing'), false)
})

test('Copilot 待发送草稿按当前用户隔离，消费后不再保留以防刷新重复发送', () => {
  const values = installStorage()
  const userA = { id: 41 }
  const userB = { id: 42 }
  const draftA = createCopilotResultDraft('molecule_workflow', 'workflow-a')
  const draftB = createCopilotSelectionDraft()

  assert.equal(savePendingCopilotDraft(userA, draftA), true)
  assert.equal(savePendingCopilotDraft(userB, draftB), true)
  assert.equal(consumePendingCopilotDraft(userB).message, draftB.message)
  assert.equal(consumePendingCopilotDraft(userA).taskId, 'workflow-a')
  assert.equal(consumePendingCopilotDraft(userA), null)
  assert.equal(values.has(pendingCopilotStorageKey(userA)), false)
  delete globalThis.localStorage
})

test('Copilot 非法、过期或其他用户格式的上下文会安全清除', () => {
  const values = installStorage()
  const user = { id: 51 }
  const key = pendingCopilotStorageKey(user)
  values.set(key, JSON.stringify({ version: 1, source: 'result', taskType: 'molecular_study', taskId: 'study-1', message: 'x', createdAt: 1, result: { full: 'must not persist' } }))
  assert.equal(consumePendingCopilotDraft(user, { now: 2 }), null)
  assert.equal(values.has(key), false)

  values.set(key, JSON.stringify({ version: 1, source: 'result', taskType: 'molecular_study', taskId: 'study-1', message: 'x', createdAt: 1 }))
  assert.equal(consumePendingCopilotDraft(user, { now: 900_002 }), null)
  assert.equal(values.has(key), false)

  assert.equal(savePendingCopilotDraft(user, createCopilotResultDraft('molecular_study', 'bad id with spaces')), false)
  assert.equal(values.has(key), false)
  delete globalThis.localStorage
})
