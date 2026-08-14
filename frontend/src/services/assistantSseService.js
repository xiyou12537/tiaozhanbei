const EVENT_TYPES = new Set(['tool_started', 'tool_completed', 'message_delta', 'message_completed', 'error', 'done'])

export function createAssistantConversationState() {
  return { messages: [], toolExecutions: [], streamingText: '', streamError: null, done: false }
}

export async function consumeAssistantSse(stream, onEvent) {
  const decoder = new TextDecoder()
  let buffer = ''
  for await (const chunk of stream) {
    buffer += decoder.decode(chunk, { stream: true })
    buffer = consumeBlocks(buffer, onEvent)
  }
  buffer += decoder.decode()
  consumeBlocks(buffer, onEvent)
}

function consumeBlocks(buffer, onEvent) {
  let boundary
  while ((boundary = buffer.match(/\r?\n\r?\n/))) {
    const index = boundary.index
    const block = buffer.slice(0, index)
    buffer = buffer.slice(index + boundary[0].length)
    const event = parseSseBlock(block)
    if (event) onEvent(event)
  }
  return buffer
}

function parseSseBlock(block) {
  let type = 'message'
  const data = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) type = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!EVENT_TYPES.has(type) || data.length === 0) return null
  try { return { type, data: JSON.parse(data.join('\n')) } } catch { return { type: 'error', data: { code: 'assistant_stream_invalid_event', message: 'Copilot 返回了无法解析的流式事件。' } } }
}

export function reduceAssistantSseEvent(state, event) {
  const next = { ...state, messages: [...state.messages], toolExecutions: [...state.toolExecutions] }
  if (event.type === 'message_delta') {
    next.streamingText += typeof event.data?.delta === 'string' ? event.data.delta : ''
    return next
  }
  if (event.type === 'message_completed') {
    const content = typeof event.data?.content === 'string' ? event.data.content : next.streamingText
    if (content) next.messages.push({ message_id: event.data?.message_id || `stream-${next.messages.length}`, role: 'assistant', content, created_at: null })
    next.streamingText = ''
    return next
  }
  if (event.type === 'tool_started' || event.type === 'tool_completed') {
    const incoming = { ...event.data }
    const exactIndex = incoming.execution_id ? next.toolExecutions.findIndex(item => item.execution_id === incoming.execution_id) : -1
    const index = exactIndex >= 0 ? exactIndex : next.toolExecutions.findIndex(item => item.tool_name === incoming.tool_name && item.status === 'running')
    const execution = { ...(index >= 0 ? next.toolExecutions[index] : {}), ...incoming, status: event.type === 'tool_started' ? 'running' : incoming.status || 'completed' }
    if (index >= 0) next.toolExecutions.splice(index, 1, execution)
    else next.toolExecutions.push(execution)
    return next
  }
  if (event.type === 'error') {
    next.streamError = event.data || { code: 'assistant_stream_error', message: 'Copilot 请求失败。' }
    return next
  }
  if (event.type === 'done') next.done = true
  return next
}

export function assistantErrorMessage(code) {
  return {
    assistant_schema_not_ready: 'Copilot 数据结构尚未由管理员启用',
    assistant_model_unconfigured: 'Copilot 模型尚未由管理员配置',
    assistant_model_timeout: 'Copilot 模型响应超时，请重试。',
    assistant_model_rate_limited: 'Copilot 模型请求过于频繁，请稍后重试。',
    assistant_model_unavailable: 'Copilot 模型当前不可用，请稍后重试。',
  }[code] || 'Copilot 暂时无法完成本次请求，请重试。'
}

export function assistantTaskLink(result = {}) {
  if (result.task_type === 'molecule_workflow' && result.task_id) return `/app/molecule-workflows/${encodeURIComponent(result.task_id)}`
  if (result.task_type === 'molecular_study' && result.task_id) return `/app/molecular-studies/${encodeURIComponent(result.task_id)}`
  if (result.task_type === 'molecular_bond_scan' && result.task_id) return `/app/molecular-bond-scans/${encodeURIComponent(result.task_id)}`
  return ''
}
