import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const completedStudy = JSON.parse(await readFile(new URL('../../docs/fixtures/molecular-study-h2-three-architecture-success.json', import.meta.url), 'utf8'))
const capabilities = {
  distance_range_angstrom: [0.5, 5], minimum_point_count: 2, maximum_point_count: 16,
  supported_basis_sets: ['sto-3g'], active_space_orbital_range: [1, 6], deployment_architecture_count_range: [3, 12],
}
const scan = {
  scan_id: 'scan_p15b', molecule_type: 'LiH', status: 'completed', completed_point_count: 2, total_point_count: 2, failed_point_count: 0, needs_review_point_count: 0, current_point_index: null,
  result: {
    points: [{ point_index: 0, distance_angstrom: 1, status: 'completed', validation_status: 'passed', hf_energy_hartree: -7.7, vqe_energy_hartree: -7.8, fci_reference: { status: 'available', energy_hartree: -7.81 }, vqe_fci_scientific_error_hartree: .01 }],
    hf_discrete_minimum: { point_index: 0, distance_angstrom: 1, energy_hartree: -7.7, minimum_at_boundary: false },
    vqe_discrete_minimum: { point_index: 0, distance_angstrom: 1, energy_hartree: -7.8, minimum_at_boundary: false },
    scientific_vqe_discrete_minimum: { point_index: 0, distance_angstrom: 1, energy_hartree: -7.8, minimum_at_boundary: false },
    fci_discrete_minimum: { point_index: 0, distance_angstrom: 1, energy_hartree: -7.81, minimum_at_boundary: false },
    engineering_only_deployment: false, summary: { issues: [] }, deployment_reference_point_index: null, deployment_result: [],
  },
}

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'p15b-token')
    localStorage.setItem('user', JSON.stringify({ id: 25, username: 'p15b-user' }))
  })
}

async function mockApi(page) {
  await page.route('**/api/molecule-workflows**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 }) }))
  await page.route('**/api/molecular-bond-scans/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(route.request().url().endsWith('/capabilities') ? capabilities : scan) }))
  await page.route('**/api/molecular-studies/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(completedStudy) }))
}

test('工作台导航可进入任务历史、方案比较和键长扫描', async ({ page }) => {
  const consoleErrors = []
  const failedRequests = []
  const unexpectedApiResponses = []
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => {
    if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(response.status())
  })
  await authenticate(page)
  await mockApi(page)
  await page.goto('/app')
  await page.getByRole('link', { name: '计算任务', exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: '计算任务', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '方案比较', exact: true }).click()
  await expect(page.getByRole('heading', { name: /比较哪种连接方案/ })).toBeVisible()
  await page.getByRole('link', { name: '键长扫描', exact: true }).click()
  await expect(page.getByRole('heading', { name: /观察 LiH 距离变化/ })).toBeVisible()
  await expect(page.locator('.platform-main a button, .platform-main button a')).toHaveCount(0)
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedApiResponses).toEqual([])
})

test('Study 与键长扫描的推荐路径保留可键盘展开的高级设置', async ({ page }) => {
  await authenticate(page)
  await mockApi(page)
  await page.goto('/app/molecular-studies/new')
  const studyAdvanced = page.locator('.advanced-settings').first()
  await studyAdvanced.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(studyAdvanced).toHaveAttribute('open', '')
  await page.goto('/app/molecular-bond-scans/new')
  await expect(page.getByRole('heading', { name: /观察 LiH 距离变化/ })).toBeVisible()
  await page.getByRole('button', { name: '下一步' }).click()
  const scanAdvanced = page.locator('.advanced-settings:visible').first()
  await scanAdvanced.locator('summary').focus()
  await scanAdvanced.locator('summary').press('Enter')
  await expect(scanAdvanced).toHaveAttribute('open', '')
})

for (const [status, expected] of [['completed', '评估完成'], ['needs_review', '需要复核'], ['partial', '部分完成'], ['failed', 'Study 未完成']]) {
  test(`Study ${status} 首屏诚实显示结论，专业证据仍可展开`, async ({ page }) => {
    await authenticate(page)
    const fixture = structuredClone(completedStudy)
    fixture.status = status
    fixture.study_id = `study_p15b_${status}`
    await page.route(`**/api/molecular-studies/${fixture.study_id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }))
    await page.goto(`/app/molecular-studies/${fixture.study_id}`)
    await expect(page.getByText(expected, { exact: true }).first()).toBeVisible()
    await expect(page.locator('.study-decision')).toContainText('整体比较')
    await expect(page.locator('.study-evidence')).not.toHaveAttribute('open', '')
    await page.locator('.study-evidence > summary').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { name: '架构比较', exact: true })).toBeVisible()
  })
}

test('Study 首屏只将部署验证明确 passed 的架构作为候选，并诚实标注未完成状态', async ({ page }) => {
  await authenticate(page)
  for (const [status, expectedOverall, expectedCandidate] of [
    ['completed', '整体比较已完成。', 'verified-a'],
    ['partial', '整体比较尚未完成；以下只展示已验证子结果，不能作为最终推荐。', '已验证子结果：verified-a'],
    ['failed', '整体比较未完成；以下只展示已验证子结果，不能作为最终推荐。', '已验证子结果：verified-a'],
    ['needs_review', '整体比较需要复核；以下只展示已验证子结果，不能作为最终推荐。', '已验证子结果：verified-a'],
  ]) {
    const fixture = structuredClone(completedStudy)
    fixture.status = status
    fixture.study_id = `study_p15b_honest_${status}`
    fixture.result.deployment_evaluations = [
      { architecture_name: 'verified-a', status: 'completed', is_deployable: true, deployment_validation: { status: 'passed' } },
      { architecture_name: 'pending-b', status: 'completed', is_deployable: true, deployment_validation: { status: 'running' } },
      { architecture_name: 'unknown-c', status: 'completed', is_deployable: true, deployment_validation: { status: 'unknown' } },
      { architecture_name: 'missing-d', status: 'completed', is_deployable: true },
      { architecture_name: 'failed-e', status: 'completed', is_deployable: true, deployment_validation: { status: 'failed' } },
    ]
    await page.route(`**/api/molecular-studies/${fixture.study_id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }))
    await page.goto(`/app/molecular-studies/${fixture.study_id}`)
    const decision = page.locator('.study-decision')
    await expect(decision).toContainText(expectedOverall)
    await expect(decision).toContainText(expectedCandidate)
    await expect(decision).not.toContainText('pending-b')
    await expect(decision).not.toContainText('unknown-c')
    await expect(decision).not.toContainText('missing-d')
    await expect(decision).not.toContainText('failed-e')
  }
})

test('Bond Scan 首屏按科学最低点的边界证据给出下一步，而非恒定扩大范围', async ({ page }) => {
  const consoleErrors = []
  const failedRequests = []
  const unexpectedApiResponses = []
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => { if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(response.status()) })
  await authenticate(page)
  for (const [id, status, minimum, expected] of [
    ['boundary', 'completed', { distance_angstrom: 1, minimum_at_boundary: true }, '建议扩大扫描范围后再判断趋势。'],
    ['interior', 'completed', { distance_angstrom: 1, minimum_at_boundary: false }, '建议缩小该区间的间隔，并复核科学验证。'],
    ['legacy', 'completed', { distance_angstrom: 1, minimum_at_boundary: null }, '请查看旧记录字段、刷新结果或重新扫描。'],
    ['waiting', 'running', null, '等待更多扫描点完成'],
  ]) {
    const fixture = structuredClone(scan)
    fixture.scan_id = `scan_p15b_${id}`
    fixture.status = status
    fixture.result.scientific_vqe_discrete_minimum = minimum
    await page.route(`**/api/molecular-bond-scans/${fixture.scan_id}`, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }))
    await page.goto(`/app/molecular-bond-scans/${fixture.scan_id}`)
    const decision = page.locator('.scan-decision')
    await expect(decision).toContainText(expected)
    if (id === 'legacy') await expect(decision).toContainText('边界位置未知')
    if (id === 'waiting') await expect(decision).toContainText('尚无科学 VQE 离散最低点')
    await expect(decision).not.toContainText('undefined Å')
  }
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedApiResponses).toEqual([])
})

test('五类页面在移动端无页面级横向溢出，宽证据只在详情内展开', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticate(page)
  await mockApi(page)
  const pages = [
    ['/app/molecule-workflows', '.workflow-history-page'],
    ['/app/molecular-studies/new', '.study-create-page'],
    [`/app/molecular-studies/${completedStudy.study_id}`, '.study-result-page'],
    ['/app/molecular-bond-scans/new', '.bond-create-page'],
    ['/app/molecular-bond-scans/scan_p15b', '.scan-result'],
  ]
  for (const [path, root] of pages) {
    await page.goto(path)
    await expect(page.locator(root)).toBeVisible()
    await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([390, 390])
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  for (const [path, root] of pages) {
    await page.goto(path)
    await expect(page.locator(root)).toBeVisible()
    await expect.poll(() => page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])).toEqual([1440, 1440])
  }
})
