import { expect, test } from '@playwright/test'
import {
  historyResponse,
  legacyHistoryItem,
  needsReviewHistoryItem,
  passedHistoryItem,
} from '../tests/fixtures/molecule-workflow-history.mjs'

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'molecule-history-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 9, username: 'history-researcher' }))
  })
}

test('任务中心区分 passed、needs_review 和旧记录空字段', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(historyResponse([passedHistoryItem, needsReviewHistoryItem, legacyHistoryItem])),
  }))

  await page.goto('/app/molecule-workflows')
  await expect(page.getByRole('heading', { level: 2, name: '计算任务', exact: true })).toBeVisible()
  const taskTable = page.locator('.history-table')
  await expect(taskTable.getByText('计算通过', { exact: true })).toHaveCount(1)
  await expect(taskTable.getByText('需要复核', { exact: true })).toHaveCount(1)
  await expect(taskTable.getByText('已完成', { exact: true })).toHaveCount(2)
  const legacyRow = page.locator('tr', { hasText: 'molwf_history_legacy' })
  await expect(legacyRow).toContainText('失败')
  await expect(legacyRow.locator('td')).toContainText(['H2'])
  await expect(legacyRow).toContainText('—')
  await expect(legacyRow).not.toContainText('0.00000000')
})

test('组合筛选、分页和刷新恢复同步到 URL Query', async ({ page }) => {
  await authenticate(page)
  const queries = []
  await page.route('**/api/molecule-workflows**', route => {
    const url = new URL(route.request().url())
    queries.push(Object.fromEntries(url.searchParams))
    const currentPage = Number(url.searchParams.get('page') || 1)
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(historyResponse([passedHistoryItem], { page: currentPage, page_size: 10, total: 21, total_pages: 3 })),
    })
  })

  await page.goto('/app/molecule-workflows?page=1&page_size=10')
  await page.getByLabel('分子名称').fill('LiH')
  await page.locator('.filter-grid .el-form-item').nth(1).locator('.el-select__wrapper').click()
  await page.getByRole('option', { name: '已完成' }).click()
  await page.locator('.filter-grid .el-form-item').nth(2).locator('.el-select__wrapper').click()
  await page.getByRole('option', { name: '计算通过' }).click()
  await page.getByRole('button', { name: '筛选', exact: true }).click()

  await expect(page).toHaveURL(/molecule_name=LiH/)
  await expect(page).toHaveURL(/status=completed/)
  await expect(page).toHaveURL(/validation_status=passed/)
  await page.getByRole('button', { name: '下一页' }).click()
  await expect(page).toHaveURL(/page=2/)
  await page.reload()
  await expect(page.getByLabel('分子名称')).toHaveValue('LiH')
  expect(queries.at(-1)).toMatchObject({
    page: '2',
    page_size: '10',
    molecule_name: 'LiH',
    status: 'completed',
    validation_status: 'passed',
  })
})

test('非法筛选被提示并使用安全 Query 恢复', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(historyResponse([])),
  }))
  await page.goto('/app/molecule-workflows?page=0&page_size=101&status=done&validation_status=unknown')
  await expect(page.getByText('筛选条件不合法', { exact: true })).toBeVisible()
  await expect(page).toHaveURL(/page=1/)
  await expect(page).toHaveURL(/page_size=20/)
  await expect(page).not.toHaveURL(/status=done/)
})

test('401 权限错误提供重新登录入口', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'invalid token' }),
  }))
  await page.goto('/app/molecule-workflows')
  await expect(page.getByText('登录状态失效', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '重新登录' })).toBeVisible()
})

test('服务异常保留已展示数据并可重试', async ({ page }) => {
  await authenticate(page)
  let requestCount = 0
  await page.route('**/api/molecule-workflows**', route => {
    requestCount += 1
    if (requestCount === 2) {
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unavailable' }) })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(historyResponse([passedHistoryItem])),
    })
  })
  await page.goto('/app/molecule-workflows')
  await expect(page.getByText('molwf_history_lih_passed', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '刷新任务' }).click()
  await expect(page.getByText('历史服务暂不可用', { exact: true })).toBeVisible()
  await expect(page.getByText('molwf_history_lih_passed', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('历史服务暂不可用', { exact: true })).toHaveCount(0)
  await expect(page.getByText('molwf_history_lih_passed', { exact: true })).toBeVisible()
})

test('接口不可用时只显示明确标注的本机缓存且可进入详情', async ({ page }) => {
  await authenticate(page)
  await page.addInitScript(() => {
    localStorage.setItem('molecule-workflow-recent-tasks', JSON.stringify([{
      workflowId: 'molwf_local_cache',
      moleculeName: 'LiH',
      validationStatus: 'passed',
      completedAt: '2026-08-06T03:54:35+00:00',
    }]))
  })
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'unavailable' }),
  }))
  await page.goto('/app/molecule-workflows')
  await expect(page.getByText('本机缓存', { exact: true })).toBeVisible()
  await page.getByText('molwf_local_cache', { exact: true }).click()
  await expect(page).toHaveURL(/\/app\/molecule-workflows\/molwf_local_cache$/)
})

test('点击服务端任务进入现有详情页', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(historyResponse([passedHistoryItem])),
  }))
  await page.goto('/app/molecule-workflows')
  await page.getByText('molwf_history_lih_passed', { exact: true }).click()
  await expect(page).toHaveURL(/\/app\/molecule-workflows\/molwf_history_lih_passed$/)
})

test('加载中和空列表都有明确状态', async ({ page }) => {
  await authenticate(page)
  let releaseRequest
  const pendingRequest = new Promise(resolve => { releaseRequest = resolve })
  await page.route('**/api/molecule-workflows**', async route => {
    await pendingRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(historyResponse([])),
    })
  })
  await page.goto('/app/molecule-workflows')
  await expect(page.getByText('正在加载计算任务…', { exact: true })).toBeVisible()
  releaseRequest()
  await expect(page.getByText('没有符合条件的计算任务', { exact: true })).toBeVisible()
})

test('小分子入口只展示服务端最近 5 条并提供全部任务入口', async ({ page }) => {
  await authenticate(page)
  await page.addInitScript(() => {
    localStorage.setItem('molecule-workflow-recent-tasks', JSON.stringify([{
      workflowId: 'molwf_should_not_mix',
      moleculeName: 'Local-only',
      validationStatus: 'passed',
      completedAt: '2026-08-01T00:00:00+00:00',
    }]))
  })
  const serverItems = Array.from({ length: 6 }, (_, index) => ({
    ...passedHistoryItem,
    workflow_id: `molwf_server_recent_${index + 1}`,
    molecule_name: index === 0 ? 'LiH' : `H2-${index}`,
  }))
  await page.route('**/api/molecule-workflows**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(route.request().url().endsWith('/capabilities') ? {
      contract_version: '2.0', supported_elements: ['H', 'Li', 'O'], supported_basis_sets: ['sto-3g'], max_atom_count: 10,
      max_mapped_qubits: 12, partition_counts: [2, 3], partition_strategies: ['sequential_greedy'],
      initial_layout_methods: ['identity'], routing_methods: ['shortest_path_swap'], execution_modes: ['logical_virtual_qpu'], is_real_qpu: false,
    } : historyResponse(serverItems, { page_size: 5, total: 6, total_pages: 2 })),
  }))
  await page.goto('/app/molecules')
  await expect(page.locator('.recent-panel').getByText('服务端记录', { exact: true })).toBeVisible()
  await expect(page.locator('.recent-list a')).toHaveCount(5)
  await expect(page.getByText('molwf_should_not_mix', { exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: /查看全部任务/ }).click()
  await expect(page).toHaveURL(/\/app\/molecule-workflows$/)
})
