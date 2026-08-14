import assert from 'node:assert/strict'
import test from 'node:test'
import {
  assistantErrorMessage,
  assistantTaskLink,
  consumeAssistantSse,
  createAssistantConversationState,
  reduceAssistantSseEvent,
} from '../src/services/assistantSseService.js'
import {
  clearRecentAssistantSession,
  readRecentAssistantSession,
  saveRecentAssistantSession,
} from '../src/services/assistantSessionStorage.js'
import { streamAssistantMessage } from '../src/api/assistantApi.js'
import { assistantDataBoundary } from '../src/services/assistantDataBoundary.js'

function chunks(...values) {
  const encoder = new TextEncoder()
  return {
    async *[Symbol.asyncIterator]() {
      for (const value of values) yield encoder.encode(value)
    },
  }
}

function byteChunks(value, splitAt) {
  const bytes = new TextEncoder().encode(value)
  return {
    async *[Symbol.asyncIterator]() {
      yield bytes.slice(0, splitAt)
      yield bytes.slice(splitAt)
    },
  }
}

test('SSE parser combines arbitrary byte chunks and emits all assistant event types', async () => {
  const received = []
  await consumeAssistantSse(
    chunks(
      'event: tool_started\ndata: {"execution_id":"exec-1","tool_name":"platform_capabilities"}\n\n',
      'event: tool_completed\ndata: {"execution_id":"exec-1","tool_name":"platform_capabilities","tool_kind":"read","status":"completed"}\n\n',
      'event: message_delta\ndata: {"delta":"量子"}\n\nevent: message_',
      'delta\ndata: {"delta":"模拟"}\n\nevent: message_completed\ndata: {"message_id":"msg-1","content":"量子模拟"}\n\nevent: error\ndata: {"code":"assistant_model_timeout","message":"timeout"}\n\nevent: done\ndata: {}\n\n',
    ),
    event => received.push(event),
  )

  assert.deepEqual(received.map(event => event.type), ['tool_started', 'tool_completed', 'message_delta', 'message_delta', 'message_completed', 'error', 'done'])
  assert.equal(received[2].data.delta + received[3].data.delta, '量子模拟')
})

test('SSE parser preserves UTF-8 text when a network chunk ends inside one character', async () => {
  const received = []
  const payload = 'event: message_delta\ndata: {"delta":"量子"}\n\nevent: done\ndata: {}\n\n'
  const splitAt = new TextEncoder().encode('event: message_delta\ndata: {"delta":"量').length
  await consumeAssistantSse(byteChunks(payload, splitAt), event => received.push(event))
  assert.equal(received[0].data.delta, '量子')
  assert.equal(received[1].type, 'done')
})

test('event reducer preserves partial assistant text after error without inventing a completed message', () => {
  let state = createAssistantConversationState()
  state = reduceAssistantSseEvent(state, { type: 'message_delta', data: { delta: 'partial ' } })
  state = reduceAssistantSseEvent(state, { type: 'error', data: { code: 'assistant_model_timeout', message: 'timeout' } })
  state = reduceAssistantSseEvent(state, { type: 'done', data: {} })

  assert.equal(state.streamingText, 'partial ')
  assert.equal(state.messages.length, 0)
  assert.equal(state.streamError.code, 'assistant_model_timeout')
  assert.equal(state.done, true)
})

test('event reducer merges tool lifecycle and pending draft confirmation without task creation', () => {
  let state = createAssistantConversationState()
  state = reduceAssistantSseEvent(state, { type: 'tool_started', data: { tool_name: 'draft_molecular_study' } })
  state = reduceAssistantSseEvent(state, {
    type: 'tool_completed',
    data: {
      execution_id: 'exec-draft', tool_name: 'draft_molecular_study', tool_kind: 'draft', status: 'pending_confirmation',
      parameter_summary: 'H2 / three architectures', confirmation_id: 'confirm-1', confirmation_expires_at: '2026-08-14T12:00:00Z',
    },
  })

  assert.equal(state.toolExecutions.length, 1)
  assert.deepEqual(state.toolExecutions, [{
    execution_id: 'exec-draft', tool_name: 'draft_molecular_study', tool_kind: 'draft', status: 'pending_confirmation',
    parameter_summary: 'H2 / three architectures', confirmation_id: 'confirm-1', confirmation_expires_at: '2026-08-14T12:00:00Z',
  }])
})

test('assistant session storage isolates the recent session by current user and stores no conversation content', () => {
  const values = new Map()
  globalThis.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }

  saveRecentAssistantSession({ id: 7 }, 'session-owner-7')
  saveRecentAssistantSession({ id: 8 }, 'session-owner-8')

  assert.equal(readRecentAssistantSession({ id: 7 }), 'session-owner-7')
  assert.equal(readRecentAssistantSession({ id: 8 }), 'session-owner-8')
  assert.equal([...values.values()].some(value => value.includes('message')), false)
  clearRecentAssistantSession({ id: 7 })
  assert.equal(readRecentAssistantSession({ id: 7 }), '')
  delete globalThis.localStorage
})

test('stream request sends only a plain message and handles streamed events', async () => {
  let request
  const received = []
  await streamAssistantMessage('session-1', '这个平台能做什么', {
    fetchImpl: async (_url, init) => {
      request = init
      return { ok: true, body: chunks('event: message_delta\ndata: {"delta":"可以"}\n\nevent: done\ndata: {}\n\n') }
    },
    onEvent: event => received.push(event),
    token: 'test-token',
  })

  assert.deepEqual(JSON.parse(request.body), { message: '这个平台能做什么' })
  assert.equal(received[0].type, 'message_delta')
  assert.equal(received[1].type, 'done')
})

test('assistant error messages preserve configured recovery semantics', () => {
  assert.equal(assistantErrorMessage('assistant_schema_not_ready'), 'Copilot 数据结构尚未由管理员启用')
  assert.equal(assistantErrorMessage('assistant_model_unconfigured'), 'Copilot 模型尚未由管理员配置')
  assert.match(assistantErrorMessage('assistant_model_rate_limited'), /稍后重试/)
})

test('confirmed task links route to the matching molecular result page', () => {
  assert.equal(assistantTaskLink({ task_type: 'molecule_workflow', task_id: 'wf-1' }), '/app/molecule-workflows/wf-1')
  assert.equal(assistantTaskLink({ task_type: 'molecular_study', task_id: 'study-1' }), '/app/molecular-studies/study-1')
  assert.equal(assistantTaskLink({ task_type: 'molecular_bond_scan', task_id: 'scan-1' }), '/app/molecular-bond-scans/scan-1')
})

test('third-party model data boundary names DeepSeek, the allowed context, exclusions and confirmation control', () => {
  assert.match(assistantDataBoundary.summary, /DeepSeek/)
  assert.match(assistantDataBoundary.summary, /logical_virtual_qpu/)
  assert.match(assistantDataBoundary.summary, /is_real_qpu=false/)
  assert.match(assistantDataBoundary.sent.join(' '), /六个受控工具/)
  assert.match(assistantDataBoundary.sent.join(' '), /紧凑摘要/)
  assert.match(assistantDataBoundary.excluded.join(' '), /完整 QASM/)
  assert.match(assistantDataBoundary.excluded.join(' '), /VQE 迭代历史/)
  assert.match(assistantDataBoundary.controls.join(' '), /用户确认/)
  assert.equal(assistantDataBoundary.sent.join(' ').includes('sk-'), false)
  assert.equal(assistantDataBoundary.excluded.join(' ').includes('sk-'), false)
})
