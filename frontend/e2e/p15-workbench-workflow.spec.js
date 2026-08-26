import { expect, test } from '@playwright/test'
import passedFixture from '../tests/fixtures/lih-passed-molecule-workflow.mjs'

const capabilities = {
  contract_version: '2.0', supported_elements: ['H', 'Li', 'O'], supported_basis_sets: ['sto-3g'], max_atom_count: 10,
  max_mapped_qubits: 12, partition_counts: [2, 3], partition_strategies: ['sequential_greedy'],
  inter_qpu_topologies: ['user_supplied_undirected_edge_list'], physical_coupling_maps: ['user_supplied_undirected_edge_list'],
  initial_layout_methods: ['identity'], routing_methods: ['shortest_path_swap'], execution_modes: ['logical_virtual_qpu'], is_real_qpu: false,
}

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'p15-workbench-token')
    localStorage.setItem('user', JSON.stringify({ id: 15, username: 'workbench-user' }))
  })
}

async function mockWorkflowApi(page, fixture = passedFixture) {
  await page.route('**/api/molecule-workflows**', route => {
    const request = route.request()
    if (request.url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(capabilities) })
    if (request.method() === 'GET' && request.url().includes('molwf_')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      items: [{ workflow_id: fixture.workflow_id, molecule_name: fixture.molecule?.molecule_name || 'LiH', status: fixture.status, validation_status: fixture.validation_status }],
      page: 1, page_size: 6, total: 1, total_pages: 1,
    }) })
  })
}

async function readTypography(page, selector) {
  return page.locator(selector).evaluate(element => {
    const style = window.getComputedStyle(element)
    const fontSize = Number.parseFloat(style.fontSize)
    const lineHeight = Number.parseFloat(style.lineHeight)
    return {
      lineHeight: style.lineHeight,
      fontSize,
      ratio: lineHeight / fontSize,
    }
  })
}

function expectReadableChineseType({ lineHeight, ratio }) {
  expect(lineHeight).not.toBe('normal')
  expect(ratio).toBeGreaterThanOrEqual(1.25)
  expect(ratio).toBeLessThanOrEqual(1.4)
}

function expectReadableChineseBody({ lineHeight, ratio }) {
  expect(lineHeight).not.toBe('normal')
  expect(ratio).toBeGreaterThanOrEqual(1.65)
  expect(ratio).toBeLessThanOrEqual(1.85)
}

test('中文行高 Token 在首页和工作台具有有效计算样式并保留响应式标题层级', async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)

    await page.goto('/')
    expectReadableChineseType(await readTypography(page, '.hero-title'))
    expectReadableChineseBody(await readTypography(page, '.hero-copy > p:not(.hero-disclaimer)'))
    await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([viewport.width, viewport.width])

    await authenticate(page)
    await mockWorkflowApi(page)
    await page.goto('/app')
    const workbenchTitle = await readTypography(page, '.workbench-hero h2')
    expectReadableChineseType(workbenchTitle)
    expectReadableChineseBody(await readTypography(page, '.workbench-hero p'))
    expect(workbenchTitle.fontSize).toBeGreaterThanOrEqual(viewport.width === 1440 ? 70 : 36)
    await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([viewport.width, viewport.width])
  }
})

test('从工作台通过主要操作进入推荐 Workflow 创建页', async ({ page }) => {
  await authenticate(page)
  await mockWorkflowApi(page)
  await page.goto('/app')
  await expect(page.getByRole('heading', { name: /下一项分子计算/ })).toBeVisible()
  await expect(page.getByText('逻辑虚拟 QPU 模拟', { exact: true })).toBeVisible()
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
  await expect(page.locator('.execution-boundary code')).not.toBeVisible()
  await page.locator('.execution-boundary summary').focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.execution-boundary code')).toContainText('execution_mode=logical_virtual_qpu')
  await expect(page.locator('.workbench-page a button, .workbench-page button a')).toHaveCount(0)
  await page.locator('.workbench-hero-actions').getByRole('button', { name: '新建分子计算', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/molecules$/)
  await expect(page.locator('.molecule-page-head').getByRole('heading', { name: '新建分子计算', exact: true })).toBeVisible()
})

test('返回平台首页入口保留认证状态，并与退出登录保持独立', async ({ page }) => {
  const consoleErrors = []
  const failedRequests = []
  const unexpectedApiResponses = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => {
    if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(response.status())
  })
  await authenticate(page)
  await mockWorkflowApi(page)
  await page.goto('/app')

  const homeLink = page.getByRole('link', { name: '返回平台首页', exact: true })
  await expect(homeLink).toBeVisible()
  await expect(page.locator('.platform-home-link a, .platform-home-link button')).toHaveCount(0)
  await homeLink.click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: /分子量子/ })).toBeVisible()
  await expect.poll(() => page.evaluate(() => ({ token: localStorage.getItem('token'), user: localStorage.getItem('user') }))).toEqual({ token: 'p15-workbench-token', user: JSON.stringify({ id: 15, username: 'workbench-user' }) })

  await page.goto('/app')
  await expect(page).toHaveURL(/\/app\/?$/)
  const desktopToggle = page.getByRole('button', { name: '收起侧栏' })
  await desktopToggle.click()
  await expect(page.getByRole('button', { name: '展开侧栏' })).toHaveAttribute('aria-expanded', 'false')
  const compactHomeLink = page.getByRole('link', { name: '返回平台首页', exact: true })
  await expect(compactHomeLink).toBeVisible()
  await compactHomeLink.click()
  await expect(page).toHaveURL(/\/$/)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('token'))).toBe('p15-workbench-token')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/app')
  const mobileToggle = page.getByRole('button', { name: '打开导航菜单' })
  await mobileToggle.focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: '导航菜单' })
  const mobileHomeLink = drawer.getByRole('link', { name: '返回平台首页', exact: true })
  await expect(mobileHomeLink).toBeVisible()
  await expect(page.locator('.mobile-drawer-home a, .mobile-drawer-home button')).toHaveCount(0)
  await mobileHomeLink.click()
  await expect(drawer).toHaveCount(0)
  await expect(page).toHaveURL(/\/$/)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('token'))).toBe('p15-workbench-token')
  await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([390, 390])

  await page.goto('/app')
  await page.getByRole('button', { name: '打开导航菜单' }).click()
  await page.getByRole('dialog', { name: '导航菜单' }).getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect.poll(() => page.evaluate(() => ({ token: localStorage.getItem('token'), user: localStorage.getItem('user') }))).toEqual({ token: null, user: null })
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedApiResponses).toEqual([])
})

test('移动端导航提供名称、键盘抽屉操作、路由跳转和退出入口', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const consoleErrors = []
  const failedRequests = []
  const unexpectedApiResponses = []
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => {
    if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(response.status())
  })
  await authenticate(page)
  await mockWorkflowApi(page)
  await page.route('**/api/assistant/sessions', route => route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ session_id: 'nav_session', messages: [], tool_executions: [] }) }))
  await page.goto('/app')

  const toggle = page.getByRole('button', { name: '打开导航菜单' })
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: '导航菜单' })
  await expect(drawer).toBeVisible()
  await expect(drawer.getByRole('link', { name: '工作台', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(drawer.getByRole('link', { name: '计算任务', exact: true })).toBeVisible()
  await expect(drawer.getByRole('link', { name: 'Molecular Copilot', exact: true })).toBeVisible()
  await expect(drawer.getByRole('button', { name: '关闭导航菜单' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([390, 390])
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')

  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute('aria-label'))).toBe('打开导航菜单')
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('')

  await toggle.click()
  await drawer.getByRole('link', { name: '工作台', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/?$/)

  await toggle.click()
  await drawer.getByRole('link', { name: '计算任务', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/molecule-workflows/)
  await expect(drawer).toHaveCount(0)

  await page.getByRole('button', { name: '打开导航菜单' }).click()
  await page.getByRole('dialog', { name: '导航菜单' }).getByRole('link', { name: 'Molecular Copilot', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/copilot/)

  await page.getByRole('button', { name: '打开导航菜单' }).click()
  await page.getByRole('dialog', { name: '导航菜单' }).getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/$/)
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedApiResponses).toEqual([])
})

test('默认配置保持可提交，高级设置可用键盘展开', async ({ page }) => {
  await authenticate(page)
  await mockWorkflowApi(page)
  await page.goto('/app/molecules')
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByText('推荐配置已生效', { exact: true })).toBeVisible()
  const advanced = page.locator('details.advanced-settings').first()
  await advanced.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(advanced).toHaveAttribute('open', '')
  await expect(page.getByLabel('活性空间轨道数')).toBeVisible()
})

for (const scenario of [
  ['completed', 'passed', '已完成'],
  ['needs_review', 'needs_review', '需要复核'],
  ['partial', null, '部分完成'],
  ['failed', null, '未完成'],
]) {
  test(`${scenario[0]} 结果首屏如实呈现状态且保留专业证据`, async ({ page }) => {
    const fixture = structuredClone(passedFixture)
    fixture.status = scenario[0]
    fixture.validation_status = scenario[1]
    await authenticate(page)
    await mockWorkflowApi(page, fixture)
    await page.goto(`/app/molecule-workflows/${fixture.workflow_id}`)
    await expect(page.getByTestId('workflow-beginner-summary')).toContainText(scenario[2])
    await expect(page.getByText('完成不等于质量验证通过', { exact: true })).toBeVisible()
    const evidence = page.locator('.workflow-evidence')
    await expect(evidence).not.toHaveAttribute('open', '')
    await evidence.locator('> summary').focus()
    await page.keyboard.press('Enter')
    await expect(evidence).toHaveAttribute('open', '')
    await expect(page.getByRole('heading', { name: 'VQE 优化与线路', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '分区间虚拟 QPU 拓扑', exact: true })).toBeVisible()
  })
}

test('工作台、创建页和 Workflow 结果在移动端没有页面级横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticate(page)
  await mockWorkflowApi(page)
  for (const path of ['/app', '/app/molecules', `/app/molecule-workflows/${passedFixture.workflow_id}`]) {
    await page.goto(path)
    await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([390, 390])
  }
})
