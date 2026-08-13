import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import lihPassedFixture from '../tests/fixtures/lih-passed-molecule-workflow.mjs'
import needsReviewFixture from '../tests/fixtures/needs-review-molecule-workflow.mjs'
import forcedSwapFixture from '../tests/fixtures/forced-swap-molecule-workflow.mjs'
import zeroSwapFixture from '../tests/fixtures/zero-swap-molecule-workflow.mjs'

const h2Fixture = JSON.parse(await readFile(new URL('../tests/fixtures/h2-molecule-workflow.json', import.meta.url), 'utf8'))
const capabilities = {
  contract_version: '2.0', supported_elements: ['H', 'Li', 'O'], supported_basis_sets: ['sto-3g'],
  max_atom_count: 10, max_mapped_qubits: 12, partition_counts: [2, 3],
  partition_strategies: ['sequential_greedy'], inter_qpu_topologies: ['user_supplied_undirected_edge_list'],
  physical_coupling_maps: ['user_supplied_undirected_edge_list'], initial_layout_methods: ['identity'],
  routing_methods: ['shortest_path_swap'], execution_modes: ['logical_virtual_qpu'], is_real_qpu: false,
}

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'molecule-workflow-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 8, username: 'molecule-researcher' }))
  })
}

async function reachConfirmation(page) {
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await expect(page.getByRole('heading', { name: '确认并执行', exact: true })).toBeVisible()
}

test('四步表单从能力接口构建并提交分离的两类拓扑', async ({ page }) => {
  await authenticate(page)
  let capturedRequest
  await page.route('**/api/molecule-workflows**', async route => {
    const request = route.request()
    if (request.url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(capabilities) })
    if (request.method() === 'POST') {
      capturedRequest = { headers: request.headers(), payload: request.postDataJSON() }
      await new Promise(resolve => setTimeout(resolve, 350))
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(h2Fixture) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], page: 1, page_size: 5, total: 0, total_pages: 0 }) })
  })

  await page.goto('/app/molecules')
  await expect(page.locator('.molecule-page-head').getByRole('heading', { name: '新建分子计算', exact: true })).toBeVisible()
  await expect(page.locator('.workflow-steps')).toContainText('分子与几何')
  await expect(page.locator('.workflow-steps')).toContainText('电子结构 / VQE 参数')
  await expect(page.getByText('非真实 QPU', { exact: true }).first()).toBeVisible()
  await reachConfirmation(page)
  await page.getByRole('button', { name: '开始计算' }).click()

  await expect(page.getByText('正在计算', { exact: true })).toBeVisible()
  await expect(page.getByText('同步长请求返回前仅展示十个预计阶段，不代表任何阶段已经完成。', { exact: true })).toBeVisible()
  await expect(page.locator('.estimated-stages li')).toHaveCount(10)
  await expect(page.locator('.estimated-stages')).not.toContainText('已完成')
  await expect(page).toHaveURL(/\/app\/molecule-workflows\/molwf_h2_frontend_fixture$/)
  expect(capturedRequest.headers.authorization).toBe('Bearer molecule-workflow-e2e-token')
  expect(capturedRequest.headers['idempotency-key']).toMatch(/^molwf-/)
  expect(capturedRequest.payload.partition.inter_qpu_topology).toEqual([{ source: 0, target: 1 }])
  expect(capturedRequest.payload.partition.virtual_qpus).toHaveLength(2)
  expect(capturedRequest.payload.partition.virtual_qpus[0].physical_coupling_map.length).toBeGreaterThan(0)
  expect(capturedRequest.payload.partition.topology_edges).toBeUndefined()
})

for (const scenario of [
  { name: '401 登录失效', status: 401, detail: 'invalid token', expected: '登录状态失效' },
  { name: '标准 422 字段错误', status: 422, detail: [{ loc: ['body', 'charge'], msg: 'invalid charge' }], expected: '表单字段不合法' },
  { name: '503 运行时不可用', status: 503, detail: { message: 'PySCF/OpenFermion 计算运行时不可用。', stage: 'electronic_structure', workflow_id: 'molwf_runtime_error' }, expected: '计算运行时不可用' },
]) {
  test(`${scenario.name}展示明确反馈并保留 Workflow ID`, async ({ page }) => {
    await authenticate(page)
    await page.route('**/api/molecule-workflows**', route => {
      if (route.request().url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(capabilities) })
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], page: 1, page_size: 5, total: 0, total_pages: 0 }) })
      return route.fulfill({ status: scenario.status, contentType: 'application/json', body: JSON.stringify({ detail: scenario.detail }) })
    })
    await page.goto('/app/molecules')
    await reachConfirmation(page)
    await page.getByRole('button', { name: '开始计算' }).click()
    await expect(page.getByText(scenario.expected, { exact: true })).toBeVisible()
    if (scenario.detail?.workflow_id) await expect(page.getByText(`Workflow ID：${scenario.detail.workflow_id}`)).toBeVisible()
  })
}

test('LiH passed 展示 Powell 诊断且 nfev 使用正确中文名称', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows/molwf_lih_passed_fixture', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(lihPassedFixture) }))
  await page.goto('/app/molecule-workflows/molwf_lih_passed_fixture')
  await expect(page.locator('.validation-summary').getByRole('heading', { name: 'Workflow 执行已完成', exact: true })).toBeVisible()
  await expect(page.getByText('计算通过', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Powell', { exact: true })).toBeVisible()
  await expect(page.getByText('目标函数评估次数', { exact: true })).toBeVisible()
  await expect(page.getByText('142', { exact: true })).toBeVisible()
})

test('needs_review 不冒充通过且完整结果仍可查看', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows/molwf_needs_review_fixture', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(needsReviewFixture) }))
  await page.goto('/app/molecule-workflows/molwf_needs_review_fixture')
  await expect(page.locator('.validation-summary').getByRole('heading', { name: 'Workflow 执行已完成', exact: true })).toBeVisible()
  await expect(page.getByText('计算通过', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'VQE 优化与线路', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '线路分区', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '跨分区通信', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '能量与质量状态', exact: true })).toBeVisible()
})

for (const scenario of [
  { fixture: zeroSwapFixture, id: 'molwf_zero_swap_fixture', swaps: '0', path: 'q0 → q1', label: '零 SWAP' },
  { fixture: forcedSwapFixture, id: 'molwf_forced_swap_fixture', swaps: '1', path: 'q0 → q2 → q1', label: '强制 SWAP' },
]) {
  test(`${scenario.label} 结果分开呈现拓扑、布局、路径和开销`, async ({ page }) => {
    await authenticate(page)
    await page.route(`**/api/molecule-workflows/${scenario.id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(scenario.fixture) }))
    await page.goto(`/app/molecule-workflows/${scenario.id}`)
    await expect(page.getByRole('heading', { name: '分区间虚拟 QPU 拓扑', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '芯片内部物理耦合拓扑', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'SWAP 路径', exact: true })).toBeVisible()
    await expect(page.locator('.routing-cost article').first()).toContainText(scenario.swaps)
    await expect(page.getByText(scenario.path, { exact: true })).toBeVisible()
    await expect(page.getByText('路由后计划已实际消费', { exact: true })).toBeVisible()
    await expect(page.getByText('actual_routed_plan_consumption=true', { exact: true })).toBeVisible()
    if (scenario.label === '强制 SWAP') {
      await expect(page.getByText('q0 ↔ q2', { exact: true })).toBeVisible()
      await expect(page.getByText('q0→p0 · q1→p1', { exact: true })).toBeVisible()
      await expect(page.getByText('q0→p2 · q1→p1', { exact: true })).toBeVisible()
    }
  })
}

test('首页和应用导航不再出现旧领域入口', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => {
    if (route.request().url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(capabilities) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], page: 1, page_size: 5, total: 0, total_pages: 0 }) })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /分子量子/ })).toBeVisible()
  const visibleText = await page.locator('body').innerText()
  expect(visibleText).not.toMatch(/锂硫电池|Li₂S₄|Li2S4|FeN₄|FeN4|吸附|文献基准/)
  await page.goto('/app/molecules')
  await expect(page.getByRole('navigation', { name: '主导航' }).getByRole('link')).toHaveCount(5)
})
