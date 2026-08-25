import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const completedFixture = JSON.parse(await readFile(new URL('../../docs/fixtures/molecular-study-h2-three-architecture-success.json', import.meta.url), 'utf8'))

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'molecular-study-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 9, username: 'study-researcher' }))
  })
}

function copy(value) { return JSON.parse(JSON.stringify(value)) }

test('202 提交后进入 Study、轮询 partial result 并在后端终态停止', async ({ page }) => {
  await authenticate(page)
  let postPayload
  let getCount = 0
  const runningFixture = copy(completedFixture)
  runningFixture.status = 'running'
  runningFixture.current_stage = 'deployment_evaluation'
  runningFixture.completed_evaluation_count = 1
  runningFixture.result.deployment_evaluations = runningFixture.result.deployment_evaluations.slice(0, 1)
  runningFixture.result.summary.completed_evaluation_count = 1

  await page.route('**/api/molecular-studies**', async route => {
    if (route.request().method() === 'POST') {
      postPayload = route.request().postDataJSON()
      return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ study_id: completedFixture.study_id, molecular_problem_id: completedFixture.molecular_problem_id, status: 'queued' }) })
    }
    getCount += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(getCount === 1 ? runningFixture : completedFixture) })
  })

  await page.goto('/app/molecular-studies/new')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '提交 Study' }).click()
  await expect(page).toHaveURL(new RegExp(`/app/molecular-studies/${completedFixture.study_id}$`))
  await expect(page.getByText('评估中', { exact: true })).toBeVisible()
  expect(postPayload.architectures).toHaveLength(3)
  expect(new Set(postPayload.architectures.map(item => item.architecture_id)).size).toBe(3)
  expect(postPayload.execution_mode).toBe('logical_virtual_qpu')
  expect(postPayload.architectures[0].partition.inter_qpu_topology).toBeDefined()
  expect(postPayload.architectures[0].partition.virtual_qpus[0].physical_coupling_map).toBeDefined()
  await expect.poll(() => getCount, { timeout: 7_000 }).toBeGreaterThanOrEqual(2)
  await expect(page.getByText('评估完成', { exact: true })).toBeVisible()
  const stoppedAt = getCount
  await page.waitForTimeout(2_800)
  expect(getCount).toBe(stoppedAt)
  await page.locator('.study-evidence > summary').click()
  await expect(page.getByText('未配置 FCI 参考', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('路由后计划已实际消费', { exact: true }).first()).toBeVisible()
})

test('刷新 Study 链接从 GET 恢复完整部署报告', async ({ page }) => {
  await authenticate(page)
  await page.route(`**/api/molecular-studies/${completedFixture.study_id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(completedFixture) }))
  await page.goto(`/app/molecular-studies/${completedFixture.study_id}`)
  await expect(page.getByText(completedFixture.study_id, { exact: false })).toBeVisible()
  await page.locator('.study-evidence > summary').click()
  await expect(page.getByRole('heading', { name: '架构比较', exact: true })).toBeVisible()
  await expect(page.getByText('forced-swap', { exact: false }).first()).toBeVisible()
  await page.reload()
  await page.locator('.study-evidence > summary').click()
  await expect(page.getByRole('heading', { name: '架构独立评估进度', exact: true })).toBeVisible()
})

for (const scenario of [
  { status: 401, detail: 'invalid token', title: '登录状态失效' },
  { status: 404, detail: { message: 'missing study', study_id: 'study_missing' }, title: 'Study 不存在' },
  { status: 422, detail: [{ loc: ['path', 'study_id'], msg: 'invalid' }], title: '请求字段不合法' },
  { status: 503, detail: { code: 'scheduler_unavailable', message: 'scheduler unavailable', study_id: 'study_busy' }, title: '服务暂不可用' },
]) {
  test(`${scenario.status} Study 查询保留错误语义`, async ({ page }) => {
    await authenticate(page)
    await page.route('**/api/molecular-studies/study_error', route => route.fulfill({ status: scenario.status, contentType: 'application/json', body: JSON.stringify({ detail: scenario.detail }) }))
    await page.goto('/app/molecular-studies/study_error')
    await expect(page.getByText(scenario.title, { exact: true })).toBeVisible()
    if (scenario.status === 503) await expect(page.getByRole('button', { name: '重试查询' })).toBeVisible()
  })
}
