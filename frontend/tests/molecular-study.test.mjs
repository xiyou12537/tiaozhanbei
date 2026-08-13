import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  buildMolecularStudyPayload,
  createMolecularStudyForm,
  isMolecularStudyTerminalStatus,
  mergeMolecularStudy,
  normalizeMolecularStudyError,
  resolveMolecularProblemId,
  validateMolecularStudyForm,
} from '../src/services/molecularStudyService.js'

const createPageSource = await readFile(new URL('../src/views/MolecularStudyCreatePage.vue', import.meta.url), 'utf8')

test('Study 请求共用一个分子问题，并要求至少三个唯一架构', () => {
  const form = createMolecularStudyForm('H2')
  assert.equal(form.architectures.length, 3)
  assert.deepEqual(validateMolecularStudyForm(form), [])

  const payload = buildMolecularStudyPayload(form)
  assert.equal(payload.mapping_method, 'jordan_wigner')
  assert.equal(payload.execution_mode, 'logical_virtual_qpu')
  assert.equal(payload.architectures.length, 3)
  assert.equal(payload.architectures[0].partition.inter_qpu_topology[0].source, 0)
  assert.equal(payload.architectures[0].partition.virtual_qpus[0].physical_coupling_map[0].target, 1)

  form.architectures[2].architectureId = form.architectures[0].architectureId
  form.architectures.splice(1, 1)
  const errors = validateMolecularStudyForm(form).join('\n')
  assert.match(errors, /至少需要 3 个架构方案/)
  assert.match(errors, /架构 ID 必须唯一/)
})

test('Study 表单拒绝越界的芯片间和芯片内边', () => {
  const form = createMolecularStudyForm('H2')
  form.architectures[0].partition.interQpuTopology = [{ source: 0, target: 3 }]
  form.architectures[0].partition.virtualQpus[0].physicalCouplingMap = [{ source: 0, target: 9 }]
  const errors = validateMolecularStudyForm(form).join('\n')
  assert.match(errors, /芯片间拓扑边/)
  assert.match(errors, /物理耦合边/)
})

test('单物理比特芯片允许空 physical coupling map', () => {
  const form = createMolecularStudyForm('H2')
  form.architectures[0].partition.virtualQpus[0].physicalQubitCount = 1
  form.architectures[0].partition.virtualQpus[0].physicalCouplingMap = []
  assert.deepEqual(validateMolecularStudyForm(form), [])
})

test('架构编辑器中的物理 Qubits 控件保留可用宽度', () => {
  assert.match(createPageSource, /\.chip-editor>header\s*:deep\(\.el-input-number\)\s*\{width:135px\}/)
})

test('Study 只根据后端 status 枚举决定轮询终止，并合并稳定 partial result', () => {
  assert.equal(isMolecularStudyTerminalStatus('queued'), false)
  assert.equal(isMolecularStudyTerminalStatus('running'), false)
  assert.equal(isMolecularStudyTerminalStatus('completed'), true)
  assert.equal(isMolecularStudyTerminalStatus('failed'), true)

  const previous = {
    study_id: 'study_partial',
    molecular_problem_id: 'mprob_current',
    status: 'running',
    result: {
      molecular_problem: { molecular_problem_id: 'mprob_current', status: 'running' },
      deployment_evaluations: [{ evaluation_id: 'evaluation-a', architecture_id: 'linear-a', status: 'completed' }],
      summary: { total_evaluation_count: 3, completed_evaluation_count: 1 },
    },
  }
  const next = {
    study_id: 'study_partial',
    molecular_problem_id: 'mprob_current',
    status: 'running',
    result: {
      molecular_problem: { molecular_problem_id: 'mprob_current', status: 'running' },
      deployment_evaluations: [{ evaluation_id: 'evaluation-b', architecture_id: 'linear-b', status: 'running' }],
      summary: { total_evaluation_count: 3, completed_evaluation_count: 1 },
    },
  }
  const merged = mergeMolecularStudy(previous, next)
  assert.equal(merged.result.deployment_evaluations.length, 2)
  assert.equal(merged.result.deployment_evaluations[0].architecture_id, 'linear-a')
})

test('Molecular problem ID 使用新字段并只为旧记录回退 deprecated problem_id', () => {
  assert.equal(resolveMolecularProblemId({ molecular_problem_id: 'mprob_new', problem_id: 'problem_old' }), 'mprob_new')
  assert.equal(resolveMolecularProblemId({ problem_id: 'problem_old' }), 'problem_old')
})

test('FCI 未配置、不可部署架构与业务错误保持科学状态和原因', () => {
  const nonDeployable = {
    status: 'completed',
    is_deployable: false,
    failure_reason: { code: 'physical_capacity_insufficient', message: 'QPU capacity is insufficient', stage: 'virtual_node_mapping' },
  }
  assert.equal(nonDeployable.is_deployable, false)
  assert.equal(nonDeployable.failure_reason.code, 'physical_capacity_insufficient')
  const fciReference = { status: 'not_configured', energy_hartree: null }
  assert.equal(fciReference.energy_hartree, null)

  const error = normalizeMolecularStudyError({ response: { status: 422, data: { detail: { code: 'architecture_invalid', message: 'Topology is disconnected', stage: 'chip_topology_routing', study_id: 'study_bad', molecular_problem_id: 'mprob_bad', architecture_id: 'forced-swap' } } } })
  assert.equal(error.code, 'architecture_invalid')
  assert.equal(error.stage, 'chip_topology_routing')
  assert.equal(error.studyId, 'study_bad')
  assert.equal(error.molecularProblemId, 'mprob_bad')
})
