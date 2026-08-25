import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import workflowResult from '../tests/fixtures/lih-passed-molecule-workflow.mjs'

const studyResult = JSON.parse(await readFile(new URL('../../docs/fixtures/molecular-study-h2-three-architecture-success.json', import.meta.url), 'utf8'))
const scanResult = JSON.parse(await readFile(new URL('../../docs/fixtures/molecular-bond-scan-lih-success.json', import.meta.url), 'utf8'))
const session = { session_id: 'asst_p15c', title: null, messages: [], tool_executions: [] }

function sse(events) { return events.map(({ type, data }) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`).join('') }

async function authenticate(page, user = { id: 95, username: 'copilot-context-user' }) {
  await page.addInitScript(storedUser => {
    localStorage.setItem('token', 'p15c-token')
    localStorage.setItem('user', JSON.stringify(storedUser))
  }, user)
}

async function mockAssistant(page, requests) {
  await page.route('**/api/assistant/sessions/asst_p15c/messages/stream', route => {
    requests.stream += 1
    requests.body = route.request().postDataJSON()
    return route.fulfill({ status: 200, contentType: 'text/event-stream', body: sse([{ type: 'message_completed', data: { content: '已收到你的问题。' } }, { type: 'done', data: {} }]) })
  })
  await page.route('**/api/assistant/sessions/asst_p15c', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) }))
  await page.route('**/api/assistant/sessions', route => route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(session) }))
}

test('工作台进入 Copilot 只预填新手问题，编辑后才以 {message} 发送且刷新不重复', async ({ page }) => {
  const requests = { stream: 0, body: null }
  const consoleErrors = []; const failedRequests = []; const unexpectedApiResponses = []
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => { if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(response.status()) })
  await authenticate(page)
  await mockAssistant(page, requests)
  await page.route('**/api/molecule-workflows**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], page: 1, page_size: 6, total: 0, total_pages: 0 }) }))
  await page.goto('/app')
  await page.getByTestId('copilot-choose-task').click()
  await expect(page).toHaveURL('/app/copilot')
  const sourceContext = page.getByTestId('copilot-source-context')
  await expect(sourceContext).toContainText('工作台 · 选择计算方式')
  await expect(sourceContext).not.toContainText(/任务类型|任务 ID|任务编号/)
  await expect(page.getByTestId('copilot-input')).toHaveValue(/我不懂，帮我选择计算方式/)
  expect(requests.stream).toBe(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([390, 390])
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByTestId('copilot-input').fill('请用一句话帮助我选择')
  await page.getByTestId('copilot-send').click()
  await expect(page.getByText('已收到你的问题。', { exact: true })).toBeVisible()
  expect(requests.body).toEqual({ message: '请用一句话帮助我选择' })
  expect(requests.stream).toBe(1)
  await page.reload()
  await expect(page.getByTestId('copilot-input')).toHaveValue('')
  expect(requests.stream).toBe(1)
  expect(consoleErrors).toEqual([]); expect(failedRequests).toEqual([]); expect(unexpectedApiResponses).toEqual([])
})

for (const scenario of [
  { name: 'Workflow', type: 'molecule_workflow', label: '单次分子计算', id: 'molwf_lih_passed_fixture', path: '/app/molecule-workflows/molwf_lih_passed_fixture', pattern: /Workflow ID：molwf_lih_passed_fixture/, route: '**/api/molecule-workflows/molwf_lih_passed_fixture', body: workflowResult },
  { name: 'Study', type: 'molecular_study', label: '方案比较', id: studyResult.study_id, path: `/app/molecular-studies/${studyResult.study_id}`, pattern: new RegExp(`Molecular Study ID：${studyResult.study_id}`), route: `**/api/molecular-studies/${studyResult.study_id}`, body: studyResult },
  { name: 'Bond Scan', type: 'molecular_bond_scan', label: 'LiH 键长扫描', id: scanResult.scan_id, path: `/app/molecular-bond-scans/${scanResult.scan_id}`, pattern: new RegExp(`LiH Bond Scan ID：${scanResult.scan_id}`), route: `**/api/molecular-bond-scans/${scanResult.scan_id}`, body: scanResult },
]) {
  test(`${scenario.name} 结果页进入 Copilot 只传任务指向，不自动读取或发送完整证据`, async ({ page }) => {
    const requests = { stream: 0, body: null }
    await authenticate(page)
    await mockAssistant(page, requests)
    await page.route(scenario.route, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(scenario.body) }))
    await page.goto(scenario.path)
    await page.getByTestId('copilot-explain-result').click()
    await expect(page).toHaveURL('/app/copilot')
    const sourceContext = page.getByTestId('copilot-source-context')
    await expect(sourceContext).toContainText('结果页 · 解释当前任务')
    await expect(sourceContext).toContainText(scenario.label)
    await expect(sourceContext).toContainText(`任务编号：${scenario.id}`)
    await expect(sourceContext).not.toContainText(scenario.type)
    await expect(sourceContext).not.toContainText('任务 ID：null')
    await expect(page.getByTestId('copilot-input')).toHaveValue(scenario.pattern)
    expect(requests.stream).toBe(0)
    const stored = await page.evaluate(() => JSON.stringify(localStorage))
    expect(stored).not.toMatch(/OPENQASM|routed_execution_plan|optimizer_history/)
  })
}

test('创建页帮助和切换用户上下文不会自动发送或串用', async ({ page }) => {
  const requests = { stream: 0, body: null }
  await authenticate(page)
  await mockAssistant(page, requests)
  await page.route('**/api/molecule-workflows**', route => {
    const body = route.request().url().endsWith('/capabilities')
      ? { contract_version: '2', supported_elements: ['H'], supported_basis_sets: ['sto-3g'], max_atom_count: 4, max_mapped_qubits: 4, partition_counts: [2], partition_strategies: ['sequential_greedy'], inter_qpu_topologies: [], physical_coupling_maps: [], initial_layout_methods: ['identity'], routing_methods: ['shortest_path_swap'] }
      : { items: [], page: 1, page_size: 6, total: 0, total_pages: 0 }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/app/molecules')
  await page.getByTestId('copilot-help-settings').click()
  await expect(page.getByTestId('copilot-input')).toHaveValue(/推荐配置/)
  expect(requests.stream).toBe(0)
  await page.evaluate(() => {
    localStorage.setItem('molecular-copilot:pending-draft:95', JSON.stringify({ version: 1, source: 'result', taskType: 'molecule_workflow', taskId: 'workflow-owner-95', message: '只属于用户 95 的问题', createdAt: Date.now() }))
    localStorage.setItem('user', JSON.stringify({ id: 96, username: 'other-user' }))
  })
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '新建分子计算' }).click()
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: 'Molecular Copilot' }).click()
  await expect(page.getByTestId('copilot-source-context')).toHaveCount(0)
  await expect(page.getByTestId('copilot-input')).toHaveValue('')
  expect(requests.stream).toBe(0)
})

test('Study 与 Bond Scan 创建页只预填设置帮助，不自动提交任务或发送模型请求', async ({ page }) => {
  const requests = { stream: 0, body: null }
  await authenticate(page)
  await mockAssistant(page, requests)
  await page.route('**/api/molecular-bond-scans/capabilities', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ supported_molecule_types: ['LiH'], distance_range_angstrom: [0.5, 5], minimum_point_count: 2, maximum_point_count: 16, supported_basis_sets: ['sto-3g'], active_space_orbital_range: [1, 6], deployment_architecture_count_range: [3, 12] }) }))
  await page.goto('/app/molecular-studies/new')
  await page.getByTestId('copilot-help-settings').click()
  const studySourceContext = page.getByTestId('copilot-source-context')
  await expect(studySourceContext).toContainText('创建页 · 理解设置')
  await expect(studySourceContext).toContainText('方案比较')
  await expect(studySourceContext).not.toContainText(/任务 ID：null|任务编号|molecular_study/)
  await expect(page.getByTestId('copilot-input')).toHaveValue(/分区、连接、拓扑和路由/)
  expect(requests.stream).toBe(0)
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '键长扫描' }).click()
  await page.getByTestId('copilot-help-settings').click()
  const scanSourceContext = page.getByTestId('copilot-source-context')
  await expect(scanSourceContext).toContainText('LiH 键长扫描')
  await expect(scanSourceContext).not.toContainText(/任务 ID：null|任务编号|molecular_bond_scan/)
  await expect(page.getByTestId('copilot-input')).toHaveValue(/范围、间隔和架构/)
  expect(requests.stream).toBe(0)
})
