import { expect, test } from '@playwright/test'

const session = { session_id: 'asst_e2e', title: null, created_at: '2026-08-14T00:00:00Z', updated_at: '2026-08-14T00:00:00Z', messages: [], tool_executions: [] }

function sse(events) {
  return events.map(({ type, data }) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`).join('')
}

async function authenticate(page, sessionId = '') {
  await page.addInitScript(({ storedSessionId }) => {
    localStorage.setItem('token', 'copilot-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 88, username: 'copilot-researcher' }))
    if (storedSessionId) localStorage.setItem('molecular-copilot:recent-session:88', storedSessionId)
  }, { storedSessionId: sessionId })
}

async function mockNewSession(page) {
  await page.route('**/api/assistant/sessions', route => route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(session) }))
}

test('creates a session, streams normal chat and exposes logical virtual-QPU boundary', async ({ page }) => {
  await authenticate(page)
  await mockNewSession(page)
  let requestBody
  const consoleErrors = []
  const failedRequests = []
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  await page.route('**/api/assistant/sessions/asst_e2e/messages/stream', route => {
    requestBody = route.request().postDataJSON()
    return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([
      { type: 'message_delta', data: { delta: '平台可以创建 Workflow。' } },
      { type: 'message_completed', data: { content: '平台可以创建 Workflow。' } },
      { type: 'done', data: {} },
    ]) })
  })
  await page.goto('/app/copilot')
  await page.getByTestId('copilot-input').fill('这个平台能做什么')
  await page.getByTestId('copilot-send').click()
  await expect(page.getByText('平台可以创建 Workflow。', { exact: true })).toBeVisible()
  await expect(page.getByText('logical_virtual_qpu', { exact: true })).toBeVisible()
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
  await expect(page.getByTestId('copilot-data-boundary')).toContainText('DeepSeek')
  await expect(page.getByTestId('copilot-data-boundary')).toContainText('is_real_qpu=false')
  await page.getByTestId('copilot-data-details').click()
  await expect(page.getByText('会发送什么', { exact: true })).toBeVisible()
  await expect(page.getByText('不会发送什么', { exact: true })).toBeVisible()
  await expect(page.getByText(/完整 QASM/)).toBeVisible()
  expect(requestBody).toEqual({ message: '这个平台能做什么' })
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
})

test('shows two tool executions and confirms a draft only once with the returned task link', async ({ page }) => {
  await authenticate(page)
  await mockNewSession(page)
  await page.route('**/api/assistant/sessions/asst_e2e/messages/stream', route => route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([
    { type: 'tool_started', data: { tool_name: 'platform_capabilities' } },
    { type: 'tool_completed', data: { execution_id: 'read-1', tool_name: 'platform_capabilities', tool_kind: 'read', status: 'completed', parameter_summary: 'read' } },
    { type: 'tool_started', data: { tool_name: 'draft_molecular_bond_scan' } },
    { type: 'tool_completed', data: { execution_id: 'draft-1', tool_name: 'draft_molecular_bond_scan', tool_kind: 'draft', status: 'pending_confirmation', parameter_summary: 'sha256:fixture', confirmation_id: 'confirm-1', confirmation_expires_at: '2026-08-14T12:00:00Z' } },
    { type: 'message_delta', data: { delta: '草稿已准备。' } },
    { type: 'message_completed', data: { content: '草稿已准备。' } },
    { type: 'done', data: {} },
  ]) }))
  let confirmationCount = 0
  await page.route('**/api/assistant/sessions/asst_e2e/tool-confirmations', route => {
    confirmationCount += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ execution_id: 'draft-1', tool_name: 'draft_molecular_bond_scan', tool_kind: 'draft', status: 'confirmed', parameter_summary: 'sha256:fixture', confirmation_id: 'confirm-1', result: { task_type: 'molecular_bond_scan', task_id: 'bondscan_created', status: 'queued' }, already_confirmed: false }) })
  })
  await page.goto('/app/copilot')
  await page.getByTestId('copilot-input').fill('帮我准备 LiH Bond Scan')
  await page.getByTestId('copilot-send').click()
  await expect(page.getByTestId('tool-execution-read-1')).toContainText('已完成')
  await expect(page.getByTestId('draft-confirmation-draft-1')).toBeVisible()
  await page.getByTestId('confirm-draft-1').dblclick()
  await expect(page.getByTestId('confirmed-task-draft-1')).toHaveAttribute('href', '/app/molecular-bond-scans/bondscan_created')
  expect(confirmationCount).toBe(1)
})

test('reload restores messages and tool executions through the user-scoped recent session', async ({ page }) => {
  await authenticate(page, 'asst_saved')
  await page.route('**/api/assistant/sessions/asst_saved', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...session, session_id: 'asst_saved', messages: [{ message_id: 'm1', role: 'assistant', content: '已恢复最近会话。', created_at: '2026-08-14T00:01:00Z' }], tool_executions: [{ execution_id: 'saved-read', tool_name: 'platform_capabilities', tool_kind: 'read', status: 'completed', parameter_summary: 'read' }] }) }))
  await page.goto('/app/copilot')
  await expect(page.getByText('已恢复最近会话。', { exact: true })).toBeVisible()
  await expect(page.getByTestId('tool-execution-saved-read')).toContainText('已完成')
  await page.reload()
  await expect(page.getByText('已恢复最近会话。', { exact: true })).toBeVisible()
  await expect(page.getByTestId('copilot-data-boundary')).toContainText('DeepSeek')
})

test('a missing saved session is cleared and replaced without restoring another account session', async ({ page }) => {
  await authenticate(page, 'asst_stale')
  await page.route('**/api/assistant/sessions/asst_stale', route => route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'assistant_session_not_found' } }) }))
  await mockNewSession(page)
  await page.goto('/app/copilot')
  await expect(page.getByTestId('copilot-input')).toBeEnabled()
  expect(await page.evaluate(() => localStorage.getItem('molecular-copilot:recent-session:88'))).toBe('asst_e2e')
})

test('a failed draft confirmation stays retryable and succeeds without duplicate confirmation clicks', async ({ page }) => {
  await authenticate(page)
  await mockNewSession(page)
  await page.route('**/api/assistant/sessions/asst_e2e/messages/stream', route => route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([
    { type: 'tool_started', data: { tool_name: 'draft_molecule_workflow' } },
    { type: 'tool_completed', data: { execution_id: 'draft-retry', tool_name: 'draft_molecule_workflow', tool_kind: 'draft', status: 'pending_confirmation', parameter_summary: 'sha256:retry', confirmation_id: 'confirm-retry', confirmation_expires_at: '2026-08-14T12:00:00Z' } },
    { type: 'done', data: {} },
  ]) }))
  let confirmationCount = 0
  await page.route('**/api/assistant/sessions/asst_e2e/tool-confirmations', route => {
    confirmationCount += 1
    if (confirmationCount === 1) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'assistant_task_creation_failed' } }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ execution_id: 'draft-retry', tool_name: 'draft_molecule_workflow', tool_kind: 'draft', status: 'confirmed', parameter_summary: 'sha256:retry', confirmation_id: 'confirm-retry', result: { task_type: 'molecule_workflow', task_id: 'workflow_retry', status: 'completed' } }) })
  })
  await page.goto('/app/copilot')
  await page.getByTestId('copilot-input').fill('准备 Workflow')
  await page.getByTestId('copilot-send').click()
  await page.getByTestId('confirm-draft-retry').click()
  await expect(page.getByTestId('draft-confirmation-draft-retry')).toBeVisible()
  await page.getByTestId('confirm-draft-retry').click()
  await expect(page.getByTestId('confirmed-task-draft-retry')).toHaveAttribute('href', '/app/molecule-workflows/workflow_retry')
  expect(confirmationCount).toBe(2)
})

test('error followed by done preserves partial text without a false completed response', async ({ page }) => {
  await authenticate(page)
  await mockNewSession(page)
  await page.route('**/api/assistant/sessions/asst_e2e/messages/stream', route => route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([
    { type: 'message_delta', data: { delta: '这是未完成内容。' } },
    { type: 'error', data: { code: 'assistant_model_timeout', message: 'timeout' } },
    { type: 'done', data: {} },
  ]) }))
  await page.goto('/app/copilot')
  await page.getByTestId('copilot-input').fill('解释任务')
  await page.getByTestId('copilot-send').click()
  await expect(page.getByTestId('copilot-partial')).toContainText('这是未完成内容。')
  await expect(page.getByText('Copilot 模型响应超时，请重试。', { exact: true })).toBeVisible()
  await expect(page.getByTestId('assistant-message-final')).toHaveCount(0)
})

for (const scenario of [
  { status: 503, code: 'assistant_schema_not_ready', title: 'Copilot 数据结构尚未由管理员启用' },
  { status: 503, code: 'assistant_model_unconfigured', title: 'Copilot 模型尚未由管理员配置' },
]) {
  test(`session creation shows ${scenario.code}`, async ({ page }) => {
    await authenticate(page)
    await page.route('**/api/assistant/sessions', route => route.fulfill({ status: scenario.status, contentType: 'application/json', body: JSON.stringify({ detail: { code: scenario.code, message: 'server message' } }) }))
    await page.goto('/app/copilot')
    await expect(page.getByText(scenario.title, { exact: true })).toBeVisible()
  })
}

for (const scenario of [
  ['assistant_model_timeout', 'Copilot 模型响应超时，请重试。'],
  ['assistant_model_rate_limited', 'Copilot 模型请求过于频繁，请稍后重试。'],
  ['assistant_model_unavailable', 'Copilot 模型当前不可用，请稍后重试。'],
]) {
  test(`stream shows ${scenario[0]} as retryable`, async ({ page }) => {
    await authenticate(page)
    await mockNewSession(page)
    await page.route('**/api/assistant/sessions/asst_e2e/messages/stream', route => route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([{ type: 'error', data: { code: scenario[0], message: 'server message' } }, { type: 'done', data: {} }]) }))
    await page.goto('/app/copilot')
    await page.getByTestId('copilot-input').fill('请解释')
    await page.getByTestId('copilot-send').click()
    await expect(page.getByText(scenario[1], { exact: true })).toBeVisible()
    await expect(page.getByTestId('copilot-retry')).toBeVisible()
  })
}

test('401 session request uses the existing login-expiry redirect', async ({ page }) => {
  await authenticate(page, 'asst_unauthorized')
  await page.route('**/api/assistant/sessions/asst_unauthorized', route => route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'invalid token' }) }))
  await page.goto('/app/copilot')
  await expect(page).toHaveURL(/\/auth\?tab=login/)
})
