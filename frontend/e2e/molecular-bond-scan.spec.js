import { expect, test } from '@playwright/test'

const capabilities = {
  supported_molecule_types: ['LiH'],
  distance_range_angstrom: [0.5, 5],
  minimum_point_count: 2,
  maximum_point_count: 16,
  supported_basis_sets: ['sto-3g'],
  active_space_orbital_range: [1, 6],
  fci_supported: true,
  deployment_architecture_count_range: [3, 12],
  execution_mode: 'logical_virtual_qpu',
  is_real_qpu: false,
}

function point(index, distance, status = 'completed') {
  return {
    point_index: index, distance_angstrom: distance, status,
    validation_status: status === 'completed' ? 'passed' : null,
    validation_issues: [], optimizer_validation: status === 'completed' ? { status: 'passed', optimizer: 'Powell', success: true, termination_reason: 'optimizer_reported_success', nfev: 30 } : null,
    scientific_validation: status === 'completed' ? { status: 'passed', target_electron_count: 2, particle_number_expectation: 2, particle_number_variance: 5e-14, hf_reference_energy_hartree: -7.8, hf_determinant_energy_hartree: -7.8, zero_parameter_energy_hartree: -7.8, first_objective_energy_hartree: -7.79, hf_reference_error_hartree: 0, fci_reference_energy_hartree: -7.81, exact_qubit_ground_energy_hartree: -7.81, vqe_fci_error_hartree: 1e-5, chemical_accuracy_threshold_hartree: 0.0016, chemical_accuracy_reached: true, variational_bound_satisfied: true, minimum_consistency_status: 'passed', core_energy_hartree: 0, active_electrons: 2, active_orbitals: [0, 1], qubit_ordering: 'jordan_wigner', spin_square: 0, expected_spin_square: 0, spin_contamination: 0, issues: [] } : null,
    deployment_validation: status === 'completed' ? { status: 'passed', distributed_execution_error_hartree: 0, actual_routed_plan_consumption: true, state_norm: 1 } : null,
    molecular_problem_id: status === 'completed' ? `mprob_${index}` : null,
    hf_energy_hartree: status === 'completed' ? -7.8 - index / 100 : null,
    vqe_energy_hartree: status === 'completed' ? -7.79 - index / 100 : null,
    vqe_converged: status === 'completed', optimizer_diagnostics: null,
    fci_reference: { status: status === 'completed' ? 'available' : 'not_configured', method: null, energy_hartree: status === 'completed' ? -7.81 - index / 100 : null, message: null },
    vqe_fci_scientific_error_hartree: status === 'completed' ? 0.02 : null, qubit_count: 4, pauli_term_count: 15, qasm: status === 'completed' ? 'OPENQASM 2.0;' : null, stages: [], error: null,
  }
}

function scanFixture(status = 'completed', points = [point(0, 1), point(1, 1.2)]) {
  return {
    scan_id: 'bondscan_e2e', molecule_type: 'LiH', status, current_stage: status === 'completed' ? 'completed' : 'vqe_optimization', execution_mode: 'logical_virtual_qpu', is_real_qpu: false, created_at: '2026-08-12T00:00:00Z', started_at: null, completed_at: status === 'completed' ? '2026-08-12T00:01:00Z' : null,
    total_point_count: 2, queued_point_count: 0, running_point_count: status === 'running' ? 1 : 0, completed_point_count: points.filter(item => item.status === 'completed').length, failed_point_count: points.filter(item => item.status === 'failed').length, needs_review_point_count: 0, current_point_index: status === 'running' ? 1 : null,
    result: { points, summary: { issues: [], minimum_at_boundary: false }, hf_discrete_minimum: { point_index: 1, distance_angstrom: 1.2, energy_hartree: -7.81, minimum_at_boundary: false, message: null }, vqe_discrete_minimum: { point_index: 1, distance_angstrom: 1.2, energy_hartree: -7.8, minimum_at_boundary: false, message: null }, scientific_vqe_discrete_minimum: { point_index: 1, distance_angstrom: 1.2, energy_hartree: -7.8, minimum_at_boundary: false, message: null }, engineering_only_deployment: false, fci_discrete_minimum: { point_index: 1, distance_angstrom: 1.2, energy_hartree: -7.82, minimum_at_boundary: false, message: null }, deployment_reference_point_index: 1, deployment_study_id: null, deployment_result: [{ evaluation_id: 'deval', architecture_id: 'forced-swap', architecture_name: 'forced-swap', status: 'completed', is_deployable: true, failure_reason: null, partition_summary: { partition_count: 2, partition_sizes: [2, 2], partitions: [] }, architecture: { inter_qpu_topology: [{ source: 0, target: 1 }], virtual_qpus: [], initial_layout: 'identity', routing_method: 'shortest_path_swap' }, metrics: { abstract_swap_count: 1, cross_partition_communication_count: 24, original_operation_count: 9, routed_operation_count: 12, original_two_qubit_operation_count: 3, routed_two_qubit_operation_count: 6, native_two_qubit_gate_equivalent_count: 5 }, energy_validation: { unpartitioned_vqe_energy_hartree: -7.8, distributed_simulation_energy_hartree: -7.8, distributed_execution_error_hartree: 0 }, deployment_validation: { status: 'passed', distributed_execution_error_hartree: 0, actual_routed_plan_consumption: true, state_norm: 1 }, distribution: { state_norm: 1, actual_partition_consumption: true, actual_routed_plan_consumption: true, routed_execution_plan: [{ execution_index: 0, original_gate_index: 0, operation: 'swap', scope: 'intra_qpu' }, { execution_index: 1, original_gate_index: 1, operation: 'cx', scope: 'inter_qpu' }], communication_events: [] } }] },
    error: null,
  }
}

async function authenticate(page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'bond-scan-e2e-token')
    localStorage.setItem('user', JSON.stringify({ id: 12, username: 'scan-researcher' }))
  })
}

test('202 提交后立即进入 Scan、合并 partial result 并在终态停止轮询', async ({ page }) => {
  await authenticate(page)
  let postPayload
  let postKey
  let getCount = 0
  await page.route('**/api/molecular-bond-scans/capabilities', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(capabilities) }))
  await page.route('**/api/molecular-bond-scans', async route => {
    if (route.request().method() !== 'POST') return route.fallback()
    postPayload = route.request().postDataJSON()
    postKey = route.request().headers()['idempotency-key']
    await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ scan_id: 'bondscan_e2e', status: 'queued', current_stage: 'input_validation', created_at: '2026-08-12T00:00:00Z', total_point_count: 2 }) })
  })
  await page.route('**/api/molecular-bond-scans/bondscan_e2e', route => {
    getCount += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(getCount === 1 ? scanFixture('running', [point(0, 1)]) : scanFixture()) })
  })
  await page.goto('/app/molecular-bond-scans/new')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('button', { name: '提交键长扫描' }).click()
  await expect(page).toHaveURL(/\/app\/molecular-bond-scans\/bondscan_e2e$/)
  expect(postPayload.molecule_type).toBe('LiH')
  expect(postPayload.deployment_architectures).toHaveLength(3)
  expect(new Set(postPayload.deployment_architectures.map(item => item.architecture_id)).size).toBe(3)
  expect(postKey).toMatch(/^molwf-/)
  await expect.poll(() => getCount, { timeout: 7_000 }).toBeGreaterThanOrEqual(2)
  await expect(page.getByText('非真实 QPU', { exact: true })).toBeVisible()
  await page.getByText('分区、映射与路由证据', { exact: true }).click()
  await expect(page.getByText('路由后计划已实际消费').first()).toBeVisible()
  const stoppedAt = getCount
  await page.waitForTimeout(2_800)
  expect(getCount).toBe(stoppedAt)
})

test('刷新通过 GET 恢复三曲线、最低点和部署报告', async ({ page }) => {
  await authenticate(page)
  await page.route('**/api/molecular-bond-scans/bondscan_e2e', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(scanFixture()) }))
  await page.goto('/app/molecular-bond-scans/bondscan_e2e')
  await expect(page.getByRole('heading', { name: 'LiH 离散势能曲线' })).toBeVisible()
  await expect(page.getByText('HF 离散最低点', { exact: true })).toBeVisible()
  await expect(page.getByText('科学验证后的 VQE 最低点', { exact: true })).toBeVisible()
  await expect(page.getByText('科学验证通过', { exact: true })).toBeVisible()
  await expect(page.getByText('particle number expectation', { exact: true })).toBeVisible()
  await expect(page.getByText('最低 VQE 点部署报告', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('VQE–FCI scientific error', { exact: true })).toBeVisible()
})

test('科学需复核、FCI 不可用和仅工程部署不伪装成可信近似键长', async ({ page }) => {
  await authenticate(page)
  const fixture = scanFixture()
  fixture.result.scientific_vqe_discrete_minimum = null
  fixture.result.engineering_only_deployment = true
  fixture.result.points[0].scientific_validation = { status: 'needs_review', target_electron_count: 2, particle_number_expectation: 1.5, particle_number_variance: 0.2, chemical_accuracy_threshold_hartree: 0.0016, chemical_accuracy_reached: false, variational_bound_satisfied: true, minimum_consistency_status: 'needs_review', active_electrons: 2, active_orbitals: [0, 1], qubit_ordering: 'jordan_wigner', issues: [{ code: 'particle_number_mismatch', message: 'particle number is not conserved' }] }
  fixture.result.points[0].fci_reference = { status: 'unavailable', method: null, energy_hartree: null, message: 'FCI unavailable' }
  await page.route('**/api/molecular-bond-scans/bondscan_science_review', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...fixture, scan_id: 'bondscan_science_review' }) }))
  await page.goto('/app/molecular-bond-scans/bondscan_science_review')
  await expect(page.getByText('科学结果需复核', { exact: true })).toBeVisible()
  await expect(page.getByText('没有通过科学验证的 VQE 最低点', { exact: true })).toBeVisible()
  await expect(page.getByText(/仅进行工程部署验证/)).toBeVisible()
  await expect(page.getByText('FCI 不可用', { exact: true })).toBeVisible()
})

test('engineering_only_deployment 的 pending、legacy、scientific 与 engineering 语义严格区分并在刷新后保留', async ({ page }) => {
  await authenticate(page)
  const running = scanFixture('running', [point(0, 1)])
  running.result.engineering_only_deployment = null
  const legacy = scanFixture()
  legacy.result.engineering_only_deployment = null
  legacy.result.summary.issues = [{ code: 'legacy_result_missing_release_fields' }]
  const scientific = scanFixture()
  scientific.result.engineering_only_deployment = false
  const engineering = scanFixture()
  engineering.result.engineering_only_deployment = true

  await page.route('**/api/molecular-bond-scans/bondscan_pending', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(running) }))
  await page.goto('/app/molecular-bond-scans/bondscan_pending')
  await expect(page.getByText('尚未形成部署结论', { exact: true })).toBeVisible()
  await expect(page.getByText('仅工程部署证据', { exact: true })).toHaveCount(0)

  await page.route('**/api/molecular-bond-scans/bondscan_legacy', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...legacy, scan_id: 'bondscan_legacy' }) }))
  await page.goto('/app/molecular-bond-scans/bondscan_legacy')
  await expect(page.getByText('旧版结果，未记录部署依据', { exact: true })).toBeVisible()
  await expect(page.getByText('科学验证点部署', { exact: true })).toHaveCount(0)

  await page.route('**/api/molecular-bond-scans/bondscan_scientific', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...scientific, scan_id: 'bondscan_scientific' }) }))
  await page.goto('/app/molecular-bond-scans/bondscan_scientific')
  await expect(page.getByText('科学验证点部署', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('科学验证点部署', { exact: true })).toBeVisible()

  await page.route('**/api/molecular-bond-scans/bondscan_engineering', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...engineering, scan_id: 'bondscan_engineering' }) }))
  await page.goto('/app/molecular-bond-scans/bondscan_engineering')
  await expect(page.getByText('仅工程部署证据', { exact: true })).toBeVisible()
})

test('queued Scan 在尚未返回 result 时仍显示尚未形成部署结论', async ({ page }) => {
  await authenticate(page)
  const queued = { scan_id: 'bondscan_queued_empty', molecule_type: 'LiH', status: 'queued', current_stage: 'input_validation', total_point_count: 8, queued_point_count: 8, running_point_count: 0, completed_point_count: 0, failed_point_count: 0, needs_review_point_count: 0, current_point_index: null, result: null, error: null }
  await page.route('**/api/molecular-bond-scans/bondscan_queued_empty', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(queued) }))
  await page.goto('/app/molecular-bond-scans/bondscan_queued_empty')
  await expect(page.getByText('尚未形成部署结论', { exact: true })).toBeVisible()
})

for (const scenario of [
  { status: 401, detail: 'invalid token', title: '登录状态失效' },
  { status: 404, detail: { message: 'missing scan', scan_id: 'bondscan_missing' }, title: '键长扫描不存在' },
  { status: 409, detail: { code: 'idempotency_key_conflict', message: 'conflicting request', scan_id: 'bondscan_conflict', stage: 'input_validation' }, title: '幂等请求冲突' },
  { status: 422, detail: [{ loc: ['path', 'scan_id'], msg: 'invalid' }], title: '请求字段不合法' },
  { status: 503, detail: { code: 'runtime_unavailable', message: 'unavailable', scan_id: 'bondscan_busy' }, title: '服务暂不可用' },
]) {
  test(`${scenario.status} Scan 查询展示契约错误语义`, async ({ page }) => {
    await authenticate(page)
    await page.route('**/api/molecular-bond-scans/bondscan_error', route => route.fulfill({ status: scenario.status, contentType: 'application/json', body: JSON.stringify({ detail: scenario.detail }) }))
    await page.goto('/app/molecular-bond-scans/bondscan_error')
    if (scenario.status === 401) await expect(page).toHaveURL(/\/auth\?/) 
    else await expect(page.getByText(scenario.title, { exact: true })).toBeVisible()
  })
}
