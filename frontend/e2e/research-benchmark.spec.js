import { expect, test } from '@playwright/test'

const WORKFLOW_ID = 'workflow-literature-001'
const BENCHMARK_ID = 'benchmark-fe-n4-c66-li2s4'

test('登录后可搜索候选、创建文献复现工作流并查看 Artifact', async ({ page }) => {
  await mockResearchBenchmarkApi(page)

  await page.goto('/auth?tab=login&redirect=/app/research-benchmarks')
  await page.locator('#login-username').fill('researcher')
  await page.locator('#login-password').fill('valid-password')
  await page.getByRole('button', { name: '登录并进入系统' }).click()

  await expect(page).toHaveURL('/app/research-benchmarks')
  await expect(page.getByText('仅文献复现基线').first()).toBeVisible()
  await page.getByRole('button', { name: '查看文献候选' }).click()

  await expect(page).toHaveURL(`/app/research-benchmarks/${BENCHMARK_ID}`)
  await expect(page.locator('.candidate-row')).toHaveCount(19)
  await page.getByPlaceholder('按文献候选 ID 精确搜索').fill('literature-2119')
  await expect(page.getByText('literature-2119')).toBeVisible()
  await page.getByRole('button', { name: '查看' }).click()

  await expect(page.getByText('candidate-coordinate.json')).toBeVisible()
  await page.getByRole('button', { name: '以此构型创建文献复现工作流' }).click()
  await page.getByRole('button', { name: '创建复现输入' }).click()

  await expect(page).toHaveURL(`/app/structure-workflows/${WORKFLOW_ID}`)
  await expect(page.locator('.top-bar .top-right')).toHaveCount(0)
  await expect(page.getByText('公开文献数据集').first()).toBeVisible()
  await expect(page.getByText('candidate-coordinate.json')).toBeVisible()
  await expect(page.getByText('尚未开始').first()).toBeVisible()
})

async function mockResearchBenchmarkApi(page) {
  const candidates = Array.from({ length: 2119 }, (_, index) => makeCandidate(index + 1))
  await page.route(url => new URL(url).pathname.startsWith('/api/'), async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()

    if (path === '/api/auth/login' && method === 'POST') {
      await fulfillJson(route, { token: 'e2e-token', user_id: 7, username: 'researcher', message: '登录成功' })
      return
    }
    if (path === '/api/platform/research-benchmarks' && method === 'GET') {
      await fulfillJson(route, { items: [makeBenchmark()], can_import: false })
      return
    }
    if (path === `/api/platform/research-benchmarks/${BENCHMARK_ID}` && method === 'GET') {
      await fulfillJson(route, makeBenchmark())
      return
    }
    if (path === `/api/platform/research-benchmarks/${BENCHMARK_ID}/candidates` && method === 'GET') {
      await fulfillJson(route, { benchmark_id: BENCHMARK_ID, items: candidates })
      return
    }
    if (path === `/api/platform/research-benchmarks/${BENCHMARK_ID}/candidates/candidate-2119/artifact`) {
      await fulfillJson(route, candidateArtifact())
      return
    }
    if (path === `/api/platform/research-benchmarks/${BENCHMARK_ID}/candidates/candidate-2119/select` && method === 'POST') {
      await fulfillJson(route, { workflow_id: WORKFLOW_ID, status: 'literature_reproduction_input_selected' }, 201)
      return
    }
    if (path === `/api/platform/structure-screening-workflows/${WORKFLOW_ID}` && method === 'GET') {
      await fulfillJson(route, makeWorkflow())
      return
    }
    if (path === `/api/platform/structure-screening-workflows/${WORKFLOW_ID}/artifacts/artifact-coordinate`) {
      await fulfillJson(route, { ...candidateArtifact(), artifact_id: 'artifact-coordinate' })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: { message: `未模拟接口：${method} ${path}` } }) })
  })
}

function makeBenchmark() {
  return {
    benchmark_id: BENCHMARK_ID,
    title: 'FeN4C66-Li2S4 Materials Cloud literature reproduction baseline',
    source_url: 'https://archive.materialscloud.org/records/f5t2r-6qf35',
    source_doi: '10.1002/qua.26956',
    source_license: 'CC-BY-4.0',
    source_dataset_version: 'materialscloud:2022.48 v2',
    candidate_count: 2119,
    scientific_validation_level: 'reproduction_baseline_only',
    dft_metadata: { software: 'CASTEP', xc_functional: 'PBE', plane_wave_cutoff: '500 eV', k_points: [3, 3, 1], dispersion: { sedc_scheme: 'g06' }, vacuum_layer_z_angstrom: 18, spin_polarized: 'TRUE' },
  }
}

function makeCandidate(index) {
  const sourceCandidateId = `literature-${String(index).padStart(4, '0')}`
  return {
    candidate_id: `candidate-${index}`,
    source_candidate_id: sourceCandidateId,
    source_energy: -100 - index / 1000,
    source_energy_unit: 'dataset_native_unit_not_confirmed',
    priority_rank: index,
    status: 'literature_candidate',
    coordinate_artifact_id: `artifact-${index}`,
    source_metadata: {
      composition_validation: 'passed',
      element_counts: { C: 66, Fe: 1, N: 4, Li: 2, S: 4 },
      lattice_matrix_angstrom: [[10, 0, 0], [0, 10, 0], [0, 0, 18]],
      source_energy_semantics: 'Materials Cloud dataset-native candidate energy; not a project adsorption energy.',
    },
  }
}

function candidateArtifact() {
  return {
    artifact_id: 'artifact-coordinate',
    artifact_role: 'literature_candidate_geometry',
    resource_type: 'research_benchmark_candidate',
    resource_id: 'candidate-2119',
    filename: 'candidate-coordinate.json',
    media_type: 'application/json',
    size_bytes: 4096,
    checksum_sha256: 'e2e-sha256',
  }
}

function makeWorkflow() {
  const readyStage = (stageName, status, artifacts = []) => ({
    stage_name: stageName,
    status,
    created_at: '2026-07-15T10:00:00Z',
    warnings: stageName === 'geometry_and_dft' ? ['文献几何，不等于平台独立 DFT 重算。'] : [],
    objects: [{ object_type: stageName, object_id: `${stageName}-1`, status, created_at: '2026-07-15T10:00:00Z', warnings: [] }],
    artifacts,
    confirmations: [],
  })
  return {
    workflow_id: WORKFLOW_ID,
    status: 'literature_reproduction_geometry_ready',
    data_source: 'literature_open_dataset',
    scientific_validation_level: 'reproduction_baseline_only',
    payload: { source_doi: '10.1002/qua.26956' },
    created_at: '2026-07-15T10:00:00Z',
    stages: [
      readyStage('structure', 'completed', [{ artifact_id: 'artifact-coordinate', artifact_role: 'literature_candidate_geometry', resource_type: 'research_benchmark_candidate' }]),
      readyStage('active_site', 'confirmed'),
      readyStage('adsorption_model', 'literature_selected'),
      readyStage('geometry_and_dft', 'completed'),
    ],
  }
}

async function fulfillJson(route, body, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}
