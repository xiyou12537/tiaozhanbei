import { expect, test } from '@playwright/test'
import lihPassedFixture from '../tests/fixtures/lih-passed-molecule-workflow.mjs'

const workflowCapabilities = {
  contract_version: '2.0', supported_elements: ['H', 'Li', 'O'], supported_basis_sets: ['sto-3g'], max_atom_count: 10, max_mapped_qubits: 12,
  partition_counts: [2, 3], partition_strategies: ['sequential_greedy'], initial_layout_methods: ['identity'], routing_methods: ['shortest_path_swap'], execution_modes: ['logical_virtual_qpu'], is_real_qpu: false,
}

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'beginner-experience-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 18, username: 'new-user' }))
  })
}

test('new user can choose a task and reveal recommended advanced settings by keyboard', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows**', route => {
    if (route.request().url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(workflowCapabilities) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  })
  await page.goto('/app/molecules')
  await expect(page.locator('.task-choice-guide')).toContainText('单次分子计算')
  await expect(page.locator('.task-choice-guide')).toContainText('方案比较')
  await expect(page.locator('.task-choice-guide')).toContainText('键长扫描')
  await expect(page.locator('.task-choice-guide a')).toHaveCount(3)
  await expect(page.locator('.task-choice-guide a').nth(0)).toHaveAttribute('href', '/app/molecules')
  await expect(page.locator('.task-choice-guide a').nth(1)).toHaveAttribute('href', '/app/molecular-studies/new')
  await expect(page.locator('.task-choice-guide a').nth(2)).toHaveAttribute('href', '/app/molecular-bond-scans/new')
  await page.getByRole('button', { name: '下一步' }).click()
  const advanced = page.locator('.advanced-settings').first()
  await expect(advanced).not.toHaveAttribute('open', '')
  await advanced.locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(advanced).toHaveAttribute('open', '')
  await expect(page.locator('.settings-guide').first()).toContainText('推荐设置')
})

test('all three result pages lead with an honest beginner summary and retain technical evidence', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecule-workflows/molwf_lih_passed_fixture', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(lihPassedFixture) }))
  await page.goto('/app/molecule-workflows/molwf_lih_passed_fixture')
  await expect(page.getByTestId('workflow-beginner-summary')).toContainText('任务是否完成')
  await expect(page.getByTestId('workflow-beginner-summary')).toContainText('最重要结果')
  await expect(page.getByTestId('workflow-beginner-summary')).toContainText('可信度 / 复核原因')
  await expect(page.getByRole('heading', { name: 'Qubit Hamiltonian' })).toBeVisible()
  await page.getByTestId('workflow-beginner-summary').locator('summary').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('workflow-beginner-summary')).toContainText('科学验证')
  await expect(page.getByTestId('workflow-beginner-summary')).toContainText('部署验证')

  const study = { study_id: 'study_beginner', status: 'completed', completed_evaluation_count: 1, total_evaluation_count: 1, result: { molecular_problem: { molecule: { molecule_name: 'LiH' } }, summary: { deployable_evaluation_count: 1, non_deployable_evaluation_count: 0, failed_evaluation_count: 0 }, deployment_evaluations: [{ architecture_id: 'linear', status: 'completed', is_deployable: true }] } }
  await page.route('**/api/molecular-studies/study_beginner', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(study) }))
  await page.goto('/app/molecular-studies/study_beginner')
  await expect(page.getByTestId('study-beginner-summary')).toContainText('1 / 1 个方案标记为可部署')
  await expect(page.getByText('架构比较', { exact: true })).toBeVisible()

  const scan = { scan_id: 'scan_beginner', status: 'completed', completed_point_count: 0, total_point_count: 0, failed_point_count: 0, needs_review_point_count: 0, result: { points: [], scientific_vqe_discrete_minimum: null, deployment_reference_point_index: null } }
  await page.route('**/api/molecular-bond-scans/scan_beginner', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(scan) }))
  await page.goto('/app/molecular-bond-scans/scan_beginner')
  await expect(page.getByTestId('bond-scan-beginner-summary')).toContainText('没有通过科学验证的离散候选点')
  await expect(page.getByText('势能曲线', { exact: true })).toBeVisible()
  await expect(page.getByText('logical_virtual_qpu', { exact: true })).toBeVisible()
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
})

test('wide technical evidence scrolls inside its own container instead of widening the page', async ({ page }) => {
  await authenticate(page)
  const consoleErrors = []
  const failedRequests = []
  const unexpectedApiResponses = []
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', request => failedRequests.push(request.url()))
  page.on('response', response => {
    if (response.url().includes('/api/') && response.status() >= 400) unexpectedApiResponses.push(`${response.status()} ${response.url()}`)
  })
  await page.route('**/api/molecule-workflows**', route => {
    if (route.request().url().endsWith('/capabilities')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(workflowCapabilities) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/app/molecules')
  await expect(page.locator('.atom-editor')).toBeVisible()
  const moleculeWidths = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(moleculeWidths.scrollWidth).toBeLessThanOrEqual(moleculeWidths.clientWidth)
  const atomWidths = await page.locator('.atom-editor').evaluate(element => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
  expect(atomWidths.scrollWidth).toBeGreaterThan(atomWidths.clientWidth)
  await page.screenshot({ path: test.info().outputPath('molecules-390x844.png'), fullPage: true })

  const study = { study_id: 'study_overflow', status: 'completed', completed_evaluation_count: 1, total_evaluation_count: 1, result: { molecular_problem: { molecule: { molecule_name: 'LiH' } }, summary: { deployable_evaluation_count: 1, non_deployable_evaluation_count: 0, failed_evaluation_count: 0 }, deployment_evaluations: [{ architecture_id: 'linear', status: 'completed', is_deployable: true }] } }
  await page.route('**/api/molecular-studies/study_overflow', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(study) }))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/app/molecular-studies/study_overflow')
  await expect(page.locator('.report-table-wrap')).toBeVisible()
  const studyWidths = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
  expect(studyWidths.scrollWidth).toBeLessThanOrEqual(studyWidths.clientWidth)
  const reportWidths = await page.locator('.report-table-wrap').evaluate(element => ({ scrollWidth: element.scrollWidth, clientWidth: element.clientWidth }))
  expect(reportWidths.scrollWidth).toBeGreaterThan(reportWidths.clientWidth)
  await page.screenshot({ path: test.info().outputPath('study-1440x900.png'), fullPage: true })
  expect(consoleErrors).toEqual([])
  expect(failedRequests).toEqual([])
  expect(unexpectedApiResponses).toEqual([])
  console.log(`layout widths: molecules ${moleculeWidths.scrollWidth}/${moleculeWidths.clientWidth}; study ${studyWidths.scrollWidth}/${studyWidths.clientWidth}; console=${consoleErrors.length}; requestfailed=${failedRequests.length}; unexpected-api=${unexpectedApiResponses.length}`)
})
