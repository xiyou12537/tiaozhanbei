import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import lihPassedFixture from '../tests/fixtures/lih-passed-molecule-workflow.mjs'
import needsReviewFixture from '../tests/fixtures/needs-review-molecule-workflow.mjs'

const h2Fixture = JSON.parse(await readFile(new URL('../tests/fixtures/h2-molecule-workflow.json', import.meta.url), 'utf8'))

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'molecule-workflow-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 8, username: 'molecule-researcher' }))
  })
}

test('H2 同步请求只显示预计阶段，成功后展示完整模拟结果', async ({ page }) => {
  await authenticate(page)
  let capturedRequest
  await page.route('**/api/molecule-workflows**', async route => {
    const request = route.request()
    if (request.method() === 'POST') {
      capturedRequest = {
        headers: request.headers(),
        payload: request.postDataJSON(),
      }
      await new Promise(resolve => setTimeout(resolve, 500))
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(h2Fixture) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(h2Fixture) })
  })

  await page.goto('/app/molecules')
  await expect(page.locator('.molecule-page-head').getByRole('heading', { name: '小分子量子计算', exact: true })).toBeVisible()
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '开始计算' }).click()

  await expect(page.getByText('正在计算', { exact: true })).toBeVisible()
  await expect(page.locator('.estimated-stages li')).toHaveCount(9)
  await expect(page.locator('.estimated-stages')).toContainText('预计阶段')
  await expect(page.locator('.estimated-stages')).not.toContainText('已完成')

  await expect(page).toHaveURL(/\/app\/molecule-workflows\/molwf_h2_frontend_fixture$/)
  await expect(page.locator('.actual-stages li')).toHaveCount(9)
  await expect(page.getByText('后端真实状态')).toBeVisible()
  await expect(page.getByText('未分区基准能量')).toBeVisible()
  await expect(page.getByText('分布式模拟能量')).toBeVisible()
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
  await expect(page.getByText('真实量子芯片执行')).toHaveCount(0)

  expect(capturedRequest.headers.authorization).toBe('Bearer molecule-workflow-e2e-token')
  expect(capturedRequest.headers['idempotency-key']).toMatch(/^molwf-/)
  expect(capturedRequest.payload.mapping_method).toBe('jordan_wigner')
  expect(capturedRequest.payload.execution_mode).toBe('logical_virtual_qpu')
})

for (const scenario of [
  {
    name: '401 登录失效',
    status: 401,
    detail: 'invalid token',
    expected: '登录状态失效',
  },
  {
    name: '标准 422 字段错误',
    status: 422,
    detail: [{ loc: ['body', 'charge'], msg: 'Input should be less than or equal to 10', type: 'less_than_equal' }],
    expected: '表单字段不合法',
  },
  {
    name: '503 运行时不可用',
    status: 503,
    detail: { code: 'electronic_structure_runtime_unavailable', message: 'PySCF/OpenFermion 计算运行时不可用。', stage: 'electronic_structure', workflow_id: 'molwf_runtime_error' },
    expected: '计算运行时不可用',
  },
]) {
  test(`${scenario.name}展示明确反馈并保留可用的 Workflow ID`, async ({ page }) => {
    await authenticate(page)
    await page.route('**/api/molecule-workflows', route => route.fulfill({
      status: scenario.status,
      contentType: 'application/json',
      body: JSON.stringify({ detail: scenario.detail }),
    }))
    await page.goto('/app/molecules')
    await page.getByRole('button', { name: '开始计算' }).click()
    await expect(page.getByText(scenario.expected, { exact: true })).toBeVisible()
    if (scenario.detail?.workflow_id) {
      await expect(page.getByText(`Workflow ID：${scenario.detail.workflow_id}`)).toBeVisible()
    }
  })
}

test('LiH completed + passed 显示计算通过和 Powell 优化器诊断', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows/molwf_lih_passed_fixture', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(lihPassedFixture),
  }))
  await page.goto('/app/molecule-workflows/molwf_lih_passed_fixture')
  await expect(page.locator('.validation-summary').getByRole('heading', { name: '计算通过', exact: true })).toBeVisible()
  await expect(page.getByText('Powell', { exact: true })).toBeVisible()
  await expect(page.getByText('目标函数评估次数', { exact: true })).toBeVisible()
  await expect(page.getByText('142', { exact: true })).toBeVisible()
  await expect(page.getByText('最佳迭代', { exact: true })).toBeVisible()
  await expect(page.getByText('能量变化', { exact: true })).toBeVisible()
})

test('completed + needs_review 不显示计算通过但完整结果仍可查看', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows/molwf_needs_review_fixture', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(needsReviewFixture),
  }))
  await page.goto('/app/molecule-workflows/molwf_needs_review_fixture')
  await expect(page.locator('.validation-summary').getByRole('heading', { name: '计算完成，需要复核', exact: true })).toBeVisible()
  await expect(page.getByText('计算通过', { exact: true })).toHaveCount(0)
  await expect(page.locator('.validation-summary > .el-tag--warning')).toBeVisible()
  await expect(page.locator('.molecule-result-page .el-tag--success')).toHaveCount(0)
  await expect(page.getByText('vqe_not_converged', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'VQE 优化与线路', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '线路分区', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '跨分区通信', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '能量结果对比', exact: true })).toBeVisible()
})
