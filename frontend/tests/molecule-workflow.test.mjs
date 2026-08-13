import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  MOLECULE_STAGE_DEFINITIONS,
  buildMoleculeWorkflowPayload,
  clonePreset,
  normalizeMoleculeWorkflowError,
  submitMoleculeWorkflow,
  validateMoleculeWorkflowForm,
} from '../src/services/moleculeWorkflowService.js'
import { saveRecentMoleculeWorkflow } from '../src/services/moleculeWorkflowStorage.js'
import lihPassedFixture from './fixtures/lih-passed-molecule-workflow.mjs'
import needsReviewFixture from './fixtures/needs-review-molecule-workflow.mjs'
import * as moleculeWorkflowModule from '../src/services/moleculeWorkflowService.js'

const fixture = JSON.parse(await readFile(new URL('./fixtures/h2-molecule-workflow.json', import.meta.url), 'utf8'))
const entrySource = await readFile(new URL('../src/views/MoleculesPage.vue', import.meta.url), 'utf8')
const resultSource = await readFile(new URL('../src/views/MoleculeWorkflowResultPage.vue', import.meta.url), 'utf8')
const validationPanelsSource = await readFile(new URL('../src/components/ScientificValidationPanels.vue', import.meta.url), 'utf8')
const serviceSource = await readFile(new URL('../src/services/moleculeWorkflowService.js', import.meta.url), 'utf8')
const indexSource = await readFile(new URL('../index.html', import.meta.url), 'utf8')

test('H2 预置生成后端约定的固定执行请求', () => {
  const form = clonePreset('H2')
  assert.deepEqual(validateMoleculeWorkflowForm(form), [])
  const payload = buildMoleculeWorkflowPayload(form)
  assert.equal(payload.molecule_name, 'H2')
  assert.deepEqual(payload.geometry[1], { element: 'H', coordinates_angstrom: [0, 0, 0.735] })
  assert.equal(payload.mapping_method, 'jordan_wigner')
  assert.equal(payload.execution_mode, 'logical_virtual_qpu')
})

test('表单限制覆盖原子、数值范围和拓扑边', () => {
  const form = clonePreset('H2')
  form.geometry[0].element = 'hydrogen'
  form.geometry[1].coordinates[2] = Number.NaN
  form.activeSpaceOrbitals = 0
  form.pauliCoefficientCutoff = 0
  form.ansatzLayers = 0
  form.maxIterations = 0
  form.partitionCount = 2
  form.interQpuTopology = [{ source: 1, target: 1 }]
  const errors = validateMoleculeWorkflowForm(form).join('\n')
  assert.match(errors, /元素符号不合法/)
  assert.match(errors, /三维坐标必须是有限数值/)
  assert.match(errors, /活性空间轨道数/)
  assert.match(errors, /Pauli 截断阈值/)
  assert.match(errors, /VQE 层数/)
  assert.match(errors, /VQE 迭代数/)
  assert.match(errors, /不允许自环/)
})

test('网络重试复用同一个 Idempotency-Key', async () => {
  const calls = []
  const request = async (_payload, idempotencyKey) => {
    calls.push(idempotencyKey)
    if (calls.length === 1) throw new Error('socket disconnected')
    return { data: fixture }
  }
  const response = await submitMoleculeWorkflow({ molecule_name: 'H2' }, {
    idempotencyKey: 'molwf-fixed-test-key',
    request,
    networkRetryCount: 1,
  })
  assert.equal(response.data.workflow_id, fixture.workflow_id)
  assert.deepEqual(calls, ['molwf-fixed-test-key', 'molwf-fixed-test-key'])
})

test('401、标准 422、业务 422 和 503 被转换为明确错误', () => {
  const unauthorized = normalizeMoleculeWorkflowError({ response: { status: 401, data: { detail: 'invalid token' } } })
  assert.equal(unauthorized.title, '登录状态失效')

  const validation = normalizeMoleculeWorkflowError({ response: { status: 422, data: { detail: [{ loc: ['body', 'charge'], msg: 'Input should be greater than -10' }] } } })
  assert.equal(validation.title, '表单字段不合法')
  assert.match(validation.message, /charge/)

  const business = normalizeMoleculeWorkflowError({ response: { status: 422, data: { detail: { message: '量子比特超限', stage: 'qubit_mapping', workflow_id: 'molwf_failed' } } } })
  assert.equal(business.stage, 'qubit_mapping')
  assert.equal(business.workflowId, 'molwf_failed')

  const unavailable = normalizeMoleculeWorkflowError({ response: { status: 503, data: { detail: { message: 'PySCF unavailable', stage: 'electronic_structure', workflow_id: 'molwf_runtime' } } } })
  assert.equal(unavailable.title, '计算运行时不可用')
  assert.equal(unavailable.workflowId, 'molwf_runtime')
})

test('H2 成功 Fixture 包含能量对比和十阶段真实结果', () => {
  assert.equal(fixture.molecule.molecule_name, 'H2')
  assert.equal(fixture.stages.length, 10)
  assert.deepEqual(fixture.stages.map(stage => stage.stage), MOLECULE_STAGE_DEFINITIONS.map(stage => stage.id))
  assert.deepEqual(MOLECULE_STAGE_DEFINITIONS[8], { id: 'chip_topology_routing', label: '芯片拓扑映射与路由' })
  assert.equal(fixture.energies.unpartitioned_benchmark_energy_hartree, -1.12)
  assert.equal(fixture.energies.distributed_simulation_energy_hartree, -1.1199999999)
  assert.equal(fixture.energies.absolute_error_hartree, 0.0000000001)
})

test('等待页渲染十个预计阶段且结果页以后端 stages 数组为准', () => {
  for (const stage of MOLECULE_STAGE_DEFINITIONS) {
    assert.match(serviceSource, new RegExp(stage.label))
  }
  assert.match(entrySource, /十个预计阶段/)
  assert.match(resultSource, /result\.stages\?\.length/)
  assert.match(resultSource, /v-for="\(stage,index\) in result\.stages \|\| \[\]"/)
  assert.match(resultSource, /模拟器/)
  assert.match(resultSource, /虚拟节点逻辑分布式模拟/)
  assert.match(resultSource, /result\?\.is_real_qpu === false/)
  assert.match(resultSource, /非真实 QPU/)
  assert.doesNotMatch(`${entrySource}\n${resultSource}`, /真实量子芯片执行/)
})

test('LiH passed Fixture 使用 Powell 并允许 nfev 大于 max_iterations', () => {
  assert.equal(lihPassedFixture.status, 'completed')
  assert.equal(lihPassedFixture.validation_status, 'passed')
  assert.equal(lihPassedFixture.vqe.optimizer, 'Powell')
  assert.ok(lihPassedFixture.vqe.optimizer_diagnostics.nfev > 80)
  assert.match(resultSource, /ScientificValidationPanels/)
  assert.doesNotMatch(resultSource, /计算通过/)
  assert.match(resultSource, /目标函数评估次数/)
  assert.doesNotMatch(resultSource, /nfev[^\n]*迭代次数/)
})

test('needs_review Fixture 不冒充计算通过并保留完整结果结构', () => {
  assert.equal(needsReviewFixture.status, 'completed')
  assert.equal(needsReviewFixture.validation_status, 'needs_review')
  assert.equal(needsReviewFixture.validation_issues[0].iteration_count, 80)
  assert.doesNotMatch(resultSource, /计算通过/)
  assert.match(resultSource, /validation_issues/)
})

test('最近任务持久化 validation_status', () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  }
  const recent = saveRecentMoleculeWorkflow(lihPassedFixture)
  assert.equal(recent[0].validationStatus, 'passed')
  delete globalThis.localStorage
})

test('应用声明 favicon，避免真实浏览器产生默认 404', () => {
  assert.match(indexSource, /<link rel="icon"/)
})

test('Workflow 服务提供受认证历史查询与 URL Query 规范化能力', () => {
  assert.equal(typeof moleculeWorkflowModule.listMoleculeWorkflows, 'function')
  assert.equal(typeof moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryQuery, 'function')
  assert.equal(typeof moleculeWorkflowModule.formatMoleculeWorkflowHistoryValue, 'function')
  assert.equal(typeof moleculeWorkflowModule.moleculeWorkflowExecutionMeta, 'function')
  assert.equal(typeof moleculeWorkflowModule.moleculeWorkflowValidationMeta, 'function')
  assert.equal(typeof moleculeWorkflowModule.canUseMoleculeWorkflowLocalFallback, 'function')
  assert.equal(typeof moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryError, 'function')
})

test('历史查询保留分页和组合筛选并拒绝非法 URL Query', () => {
  const valid = moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryQuery({
    page: '2',
    page_size: '10',
    molecule_name: ' LiH ',
    status: 'completed',
    validation_status: 'passed',
  })
  assert.deepEqual(valid, {
    filters: {
      page: 2,
      page_size: 10,
      molecule_name: 'LiH',
      status: 'completed',
      validation_status: 'passed',
    },
    issues: [],
  })

  const invalid = moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryQuery({
    page: '0',
    page_size: '101',
    molecule_name: '   ',
    status: 'done',
    validation_status: 'unknown',
  })
  assert.deepEqual(invalid.filters, { page: 1, page_size: 20 })
  assert.equal(invalid.issues.length, 5)
})

test('历史查询向服务端原样发送组合筛选', async () => {
  let captured
  const expected = { items: [], page: 3, page_size: 20, total: 0, total_pages: 0 }
  const result = await moleculeWorkflowModule.listMoleculeWorkflows({
    page: 3,
    page_size: 20,
    molecule_name: 'LiH',
    status: 'completed',
    validation_status: 'passed',
  }, {
    request: async params => {
      captured = params
      return { data: expected }
    },
  })
  assert.equal(captured.validation_status, 'passed')
  assert.equal(captured.status, 'completed')
  assert.equal(result, expected)
})

test('历史旧记录空字段显示破折号且真实零值不被当成空值', () => {
  assert.equal(moleculeWorkflowModule.formatMoleculeWorkflowHistoryValue(null), '—')
  assert.equal(moleculeWorkflowModule.formatMoleculeWorkflowHistoryValue(undefined), '—')
  assert.equal(moleculeWorkflowModule.formatMoleculeWorkflowHistoryValue(0), '0')
  assert.equal(moleculeWorkflowModule.formatMoleculeWorkflowHistoryValue(0, { digits: 8 }), '0.00000000')
})

test('执行状态与质量状态严格分离', () => {
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowExecutionMeta('completed'), { label: '已完成', type: 'info' })
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowExecutionMeta('running'), { label: '运行中', type: 'warning' })
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowExecutionMeta('failed'), { label: '失败', type: 'danger' })
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowValidationMeta('passed'), { label: '计算通过', type: 'success' })
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowValidationMeta('needs_review'), { label: '需要复核', type: 'warning' })
  assert.deepEqual(moleculeWorkflowModule.moleculeWorkflowValidationMeta(null), { label: '—', type: 'info' })
  assert.notEqual(moleculeWorkflowModule.moleculeWorkflowExecutionMeta('completed').label, '计算通过')
})

test('仅服务不可用时允许使用本机缓存兜底', () => {
  assert.equal(moleculeWorkflowModule.canUseMoleculeWorkflowLocalFallback(new Error('network down')), true)
  assert.equal(moleculeWorkflowModule.canUseMoleculeWorkflowLocalFallback({ response: { status: 503 } }), true)
  assert.equal(moleculeWorkflowModule.canUseMoleculeWorkflowLocalFallback({ response: { status: 401 } }), false)
  assert.equal(moleculeWorkflowModule.canUseMoleculeWorkflowLocalFallback({ response: { status: 422 } }), false)
})

test('历史 GET 错误不冒充 POST 计算运行时错误', () => {
  const unavailable = moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryError({ response: { status: 503, data: { detail: 'unavailable' } } })
  assert.equal(unavailable.title, '历史服务暂不可用')
  assert.equal(unavailable.retryable, true)
  assert.notEqual(unavailable.title, '计算运行时不可用')

  const unauthorized = moleculeWorkflowModule.normalizeMoleculeWorkflowHistoryError({ response: { status: 401, data: { detail: 'invalid token' } } })
  assert.equal(unauthorized.title, '登录状态失效')
  assert.equal(unauthorized.retryable, false)
})
