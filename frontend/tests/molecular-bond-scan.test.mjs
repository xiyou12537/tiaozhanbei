import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildBondScanPayload,
  bondScanDeploymentReferenceView,
  createBondScanArchitectures,
  createBondScanForm,
  isBondScanTerminalStatus,
  mergeMolecularBondScan,
  previewBondDistances,
  scanCurveSeries,
  scanMinimumCards,
  submitMolecularBondScan,
  validateBondScanForm,
} from '../src/services/molecularBondScanService.js'
import { saveRecentMolecularBondScan } from '../src/services/molecularBondScanStorage.js'

const architectures = [
  { architectureId: 'linear-a', partition: { partitionCount: 2, partitionStrategy: 'sequential_greedy', interQpuTopology: [{ source: 0, target: 1 }], virtualQpus: [{ virtualQpuId: 'T1', physicalQubitCount: 2, physicalCouplingMap: [{ source: 0, target: 1 }] }, { virtualQpuId: 'T2', physicalQubitCount: 2, physicalCouplingMap: [{ source: 0, target: 1 }] }], initialLayout: 'identity', routingMethod: 'shortest_path_swap' } },
  { architectureId: 'forced-swap', partition: { partitionCount: 2, partitionStrategy: 'sequential_greedy', interQpuTopology: [{ source: 0, target: 1 }], virtualQpus: [{ virtualQpuId: 'T1', physicalQubitCount: 3, physicalCouplingMap: [{ source: 0, target: 2 }, { source: 2, target: 1 }] }, { virtualQpuId: 'T2', physicalQubitCount: 2, physicalCouplingMap: [{ source: 0, target: 1 }] }], initialLayout: 'identity', routingMethod: 'shortest_path_swap' } },
  { architectureId: 'linear-b', partition: { partitionCount: 2, partitionStrategy: 'sequential_greedy', interQpuTopology: [{ source: 0, target: 1 }], virtualQpus: [{ virtualQpuId: 'T1', physicalQubitCount: 2, physicalCouplingMap: [{ source: 0, target: 1 }] }, { virtualQpuId: 'T2', physicalQubitCount: 2, physicalCouplingMap: [{ source: 0, target: 1 }] }], initialLayout: 'identity', routingMethod: 'shortest_path_swap' } },
]

test('LiH 扫描按 capabilities 范围生成后端规则的离散距离点并复用 Study 架构', () => {
  const form = createBondScanForm(architectures)
  assert.deepEqual(previewBondDistances(1, 2.4, 8), [1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.4])
  assert.deepEqual(validateBondScanForm(form, { distance_range_angstrom: [0.5, 5], minimum_point_count: 2, maximum_point_count: 16, supported_basis_sets: ['sto-3g'], active_space_orbital_range: [1, 6], deployment_architecture_count_range: [3, 12] }), [])
  const payload = buildBondScanPayload(form)
  assert.equal(payload.molecule_type, 'LiH')
  assert.equal(payload.deployment_architectures.length, form.architectures.length)
  assert.equal(payload.deployment_architectures[1].architecture_id, 'forced-swap')
})

test('部署架构在提交前校验唯一 ID、芯片间拓扑和芯片内耦合边', () => {
  const invalid = structuredClone(architectures)
  invalid[1].architectureId = 'linear-a'
  invalid[2].partition.interQpuTopology = []
  invalid[0].partition.virtualQpus[0].physicalCouplingMap = [{ source: 0, target: 3 }]
  const form = createBondScanForm(invalid)
  const errors = validateBondScanForm(form, {
    distance_range_angstrom: [0.5, 5], minimum_point_count: 2, maximum_point_count: 16,
    supported_basis_sets: ['sto-3g'], active_space_orbital_range: [1, 6], deployment_architecture_count_range: [3, 12],
  })
  assert.equal(errors.some(error => error.includes('唯一')), true)
  assert.equal(errors.some(error => error.includes('芯片间拓扑')), true)
  assert.equal(errors.some(error => error.includes('物理耦合边')), true)
})

test('默认三架构覆盖线性与强制 SWAP 路由情形，而不携带任何结果数据', () => {
  const defaults = createBondScanArchitectures()
  assert.deepEqual(defaults.map(item => item.architectureId), ['linear-a', 'forced-swap', 'linear-b'])
  assert.deepEqual(defaults[1].partition.virtualQpus[0].physicalCouplingMap, [{ source: 0, target: 2 }, { source: 2, target: 1 }])
  assert.equal(Object.hasOwn(defaults[1], 'metrics'), false)
  assert.equal(Object.hasOwn(defaults[1], 'energyValidation'), false)
})

test('partial scan 合并保留已完成点，且只以后端终态停止轮询', () => {
  assert.equal(isBondScanTerminalStatus('queued'), false)
  assert.equal(isBondScanTerminalStatus('running'), false)
  assert.equal(isBondScanTerminalStatus('completed'), true)
  assert.equal(isBondScanTerminalStatus('failed'), true)
  const first = { scan_id: 'bondscan_partial', status: 'running', result: { points: [{ point_index: 0, status: 'completed', distance_angstrom: 1, fci_reference: { status: 'available', energy_hartree: -7.9 } }], summary: {} } }
  const second = { scan_id: 'bondscan_partial', status: 'running', result: { points: [{ point_index: 1, status: 'running', distance_angstrom: 1.2, fci_reference: { status: 'available', energy_hartree: null } }], summary: {} } }
  assert.deepEqual(mergeMolecularBondScan(first, second).result.points.map(point => point.point_index), [0, 1])
})

test('partial response 的 null 字段不能覆盖已获得的点能量和 QASM', () => {
  const first = {
    status: 'running',
    result: {
      points: [{ point_index: 0, status: 'completed', distance_angstrom: 1, vqe_energy_hartree: -7.8, qasm: 'OPENQASM 2.0;', fci_reference: { status: 'available', energy_hartree: -7.9 } }],
      summary: {},
    },
  }
  const laterPartial = {
    status: 'running',
    result: {
      points: [{ point_index: 0, status: 'completed', distance_angstrom: 1, vqe_energy_hartree: null, qasm: null, fci_reference: { status: 'available', energy_hartree: null } }],
      summary: {},
    },
  }
  const point = mergeMolecularBondScan(first, laterPartial).result.points[0]
  assert.equal(point.vqe_energy_hartree, -7.8)
  assert.equal(point.qasm, 'OPENQASM 2.0;')
  assert.equal(point.fci_reference.energy_hartree, -7.9)
})

test('network retry keeps the same Idempotency-Key for one scan submission', async () => {
  const keys = []
  let attempts = 0
  const request = async (_payload, key) => {
    keys.push(key)
    attempts += 1
    if (attempts === 1) {
      const error = new Error('offline')
      error.code = 'ERR_NETWORK'
      throw error
    }
    return { data: { scan_id: 'bondscan_retry', status: 'queued' } }
  }
  const result = await submitMolecularBondScan({ molecule_type: 'LiH' }, { request, idempotencyKey: 'bondscan-key', networkRetryCount: 1 })
  assert.equal(result.data.scan_id, 'bondscan_retry')
  assert.deepEqual(keys, ['bondscan-key', 'bondscan-key'])
  assert.equal(result.idempotencyKey, 'bondscan-key')
})

test('三条离散曲线跳过 failed 和 null FCI，科学误差不与执行误差混合', () => {
  const points = [
    { point_index: 0, distance_angstrom: 1, status: 'completed', validation_status: 'passed', hf_energy_hartree: -7.7, vqe_energy_hartree: -7.8, fci_reference: { status: 'available', energy_hartree: -7.81 }, vqe_fci_scientific_error_hartree: 0.01 },
    { point_index: 1, distance_angstrom: 1.2, status: 'failed', fci_reference: { status: 'unavailable', energy_hartree: null } },
    { point_index: 2, distance_angstrom: 1.4, status: 'completed', validation_status: 'needs_review', hf_energy_hartree: -7.75, vqe_energy_hartree: -7.78, fci_reference: { status: 'unavailable', energy_hartree: null }, vqe_fci_scientific_error_hartree: null },
  ]
  const series = scanCurveSeries(points)
  assert.deepEqual(series.hf.map(point => point.pointIndex), [0, 2])
  assert.deepEqual(series.fci.map(point => point.pointIndex), [0])
  assert.equal(series.vqe[1].needsReview, true)
  assert.notEqual(series.hf[0].energy, series.fci[0].energy)
})

test('三种最低点分开展示，扫描边界与 FCI 空值语义不被伪造', () => {
  const cards = scanMinimumCards({
    hf_discrete_minimum: { point_index: 3, distance_angstrom: 1.6, energy_hartree: -7.9, minimum_at_boundary: false },
    vqe_discrete_minimum: { point_index: 4, distance_angstrom: 1.8, energy_hartree: -7.88, minimum_at_boundary: true },
    fci_discrete_minimum: { point_index: 3, distance_angstrom: 1.6, energy_hartree: -7.91, minimum_at_boundary: false },
  })
  assert.deepEqual(cards.map(card => card.distance), [1.6, 1.8, null, 1.6])
  assert.equal(cards[1].minimumAtBoundary, true)
  assert.equal(cards[3].energy, -7.91)
})

test('科学验证后的 VQE 最低点独立于仅优化器通过的 VQE 最低点', () => {
  const cards = scanMinimumCards({
    hf_discrete_minimum: { point_index: 3, distance_angstrom: 1.6, energy_hartree: -7.9, minimum_at_boundary: false },
    vqe_discrete_minimum: { point_index: 4, distance_angstrom: 1.8, energy_hartree: -7.88, minimum_at_boundary: false },
    scientific_vqe_discrete_minimum: { point_index: 3, distance_angstrom: 1.6, energy_hartree: -7.87, minimum_at_boundary: false },
    fci_discrete_minimum: { point_index: 3, distance_angstrom: 1.6, energy_hartree: -7.91, minimum_at_boundary: false },
  })
  assert.deepEqual(cards.map(card => card.label), ['HF 离散最低点', '优化器通过的 VQE 离散最低点', '科学验证后的 VQE 最低点', 'FCI 离散最低点'])
  assert.deepEqual(cards.map(card => card.distance), [1.6, 1.8, 1.6, 1.6])
})

test('engineering_only_deployment preserves null, false and true as three distinct deployment conclusions', () => {
  assert.deepEqual(
    bondScanDeploymentReferenceView({ status: 'running', result: { engineering_only_deployment: null, summary: { issues: [] } } }),
    { kind: 'pending', title: '尚未形成部署结论', message: '部署参考点仍由后端计算中；当前不解释为科学验证后部署。' },
  )
  assert.deepEqual(
    bondScanDeploymentReferenceView({ status: 'completed', result: { engineering_only_deployment: null, summary: { issues: [{ code: 'legacy_result_missing_release_fields' }] } } }),
    { kind: 'legacy', title: '旧版结果，未记录部署依据', message: '旧版结果未提供 engineering_only_deployment，不能推断为科学验证后部署。' },
  )
  assert.equal(bondScanDeploymentReferenceView({ status: 'completed', result: { engineering_only_deployment: false, summary: { issues: [] } } }).title, '科学验证点部署')
  assert.equal(bondScanDeploymentReferenceView({ status: 'completed', result: { engineering_only_deployment: true, summary: { issues: [] } } }).title, '仅工程部署证据')
})

test('partial merge and recent storage do not coerce engineering_only_deployment null to false', () => {
  const partial = { scan_id: 'bondscan-null', status: 'running', result: { engineering_only_deployment: null, points: [], summary: { issues: [] } } }
  const completed = { scan_id: 'bondscan-null', status: 'completed', result: { engineering_only_deployment: false, points: [], summary: { issues: [] } } }
  assert.equal(mergeMolecularBondScan(partial, completed).result.engineering_only_deployment, false)
  assert.equal(mergeMolecularBondScan(completed, { ...completed, result: { ...completed.result, engineering_only_deployment: null } }).result.engineering_only_deployment, null)

  const storage = new Map()
  globalThis.localStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) }
  const saved = saveRecentMolecularBondScan(partial)
  assert.equal(saved[0].engineeringOnlyDeployment, null)
  delete globalThis.localStorage
})
