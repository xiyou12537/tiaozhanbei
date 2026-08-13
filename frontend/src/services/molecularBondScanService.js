import { createMolecularBondScanRequest, fetchMolecularBondScanCapabilitiesRequest, fetchMolecularBondScanRequest } from '../api/molecularBondScanApi.js'
import { createArchitecture } from './molecularStudyService.js'
import { createIdempotencyKey, isNetworkFailure } from './moleculeWorkflowService.js'

export const BOND_SCAN_RUNNING_STATUSES = ['queued', 'running']
export const BOND_SCAN_TERMINAL_STATUSES = ['completed', 'failed']

export function createBondScanArchitectures() {
  const linearA = createArchitecture(1)
  const forcedSwap = createArchitecture(2)
  const linearB = createArchitecture(3)
  linearA.architectureId = 'linear-a'
  forcedSwap.architectureId = 'forced-swap'
  linearB.architectureId = 'linear-b'
  for (const architecture of [linearA, forcedSwap, linearB]) {
    architecture.partition.virtualQpus.forEach((chip, index) => { chip.virtualQpuId = `T${index + 1}` })
  }
  forcedSwap.partition.virtualQpus[0].physicalQubitCount = 3
  forcedSwap.partition.virtualQpus[0].physicalCouplingMap = [{ source: 0, target: 2 }, { source: 2, target: 1 }]
  forcedSwap.partition.virtualQpus[1].physicalQubitCount = 2
  forcedSwap.partition.virtualQpus[1].physicalCouplingMap = [{ source: 0, target: 1 }]
  return [linearA, forcedSwap, linearB]
}

export function createBondScanForm(architectures = createBondScanArchitectures()) {
  return {
    startDistance: 1,
    endDistance: 2.4,
    pointCount: 8,
    charge: 0,
    spinMultiplicity: 1,
    basisSet: 'sto-3g',
    activeSpaceOrbitals: 2,
    pauliCoefficientCutoff: 0.000001,
    ansatzLayers: 1,
    maxIterations: 80,
    architectures,
  }
}

export function previewBondDistances(start, end, pointCount) {
  const count = Number(pointCount)
  const startValue = Number(start)
  const endValue = Number(end)
  if (!Number.isInteger(count) || count < 2 || !Number.isFinite(startValue) || !Number.isFinite(endValue)) return []
  return Array.from({ length: count }, (_, index) => Number((startValue + index * (endValue - startValue) / (count - 1)).toFixed(12)))
}

export function validateBondScanForm(form, capabilities = {}) {
  const errors = []
  const [minimumDistance, maximumDistance] = capabilities.distance_range_angstrom || []
  const [minimumOrbital, maximumOrbital] = capabilities.active_space_orbital_range || [1, 6]
  const [minimumArchitectures, maximumArchitectures] = capabilities.deployment_architecture_count_range || [3, 12]
  if (!Number.isFinite(Number(form.startDistance)) || Number(form.startDistance) < minimumDistance || Number(form.startDistance) > maximumDistance) errors.push('起始距离不在当前 capabilities 范围内')
  if (!Number.isFinite(Number(form.endDistance)) || Number(form.endDistance) < minimumDistance || Number(form.endDistance) > maximumDistance || Number(form.endDistance) <= Number(form.startDistance)) errors.push('终止距离必须大于起始距离且在当前 capabilities 范围内')
  if (!Number.isInteger(Number(form.pointCount)) || Number(form.pointCount) < capabilities.minimum_point_count || Number(form.pointCount) > capabilities.maximum_point_count) errors.push('扫描点数不在当前 capabilities 范围内')
  if (!Number.isInteger(Number(form.charge))) errors.push('电荷必须是整数')
  if (!Number.isInteger(Number(form.spinMultiplicity)) || Number(form.spinMultiplicity) < 1) errors.push('自旋多重度必须是正整数')
  if (!capabilities.supported_basis_sets?.includes(form.basisSet)) errors.push('基组不在当前 capabilities 范围内')
  if (!Number.isInteger(Number(form.activeSpaceOrbitals)) || Number(form.activeSpaceOrbitals) < minimumOrbital || Number(form.activeSpaceOrbitals) > maximumOrbital) errors.push('活性空间轨道数不在当前 capabilities 范围内')
  if (!(Number(form.pauliCoefficientCutoff) > 0 && Number(form.pauliCoefficientCutoff) <= 0.01)) errors.push('Pauli 截断阈值不合法')
  if (!Number.isInteger(Number(form.ansatzLayers)) || Number(form.ansatzLayers) < 1 || Number(form.ansatzLayers) > 4) errors.push('VQE 层数不合法')
  if (!Number.isInteger(Number(form.maxIterations)) || Number(form.maxIterations) < 1 || Number(form.maxIterations) > 500) errors.push('最大迭代数不合法')
  if (!Array.isArray(form.architectures) || form.architectures.length < minimumArchitectures || form.architectures.length > maximumArchitectures) errors.push('部署架构数量不在当前 capabilities 范围内')
  const ids = new Set()
  for (const architecture of form.architectures || []) {
    if (!architecture.architectureId || ids.has(architecture.architectureId)) errors.push('架构 ID 必须唯一')
    ids.add(architecture.architectureId)
    const partition = architecture.partition || {}
    const count = Number(partition.partitionCount)
    if (!Number.isInteger(count) || count < 2 || count > 3 || partition.virtualQpus?.length !== count) errors.push(`架构 ${architecture.architectureId} 的分区或虚拟 QPU 不合法`)
    if (!Array.isArray(partition.interQpuTopology) || partition.interQpuTopology.length < 1) errors.push(`架构 ${architecture.architectureId} 至少需要一条芯片间拓扑边`)
    for (const edge of partition.interQpuTopology || []) if (!Number.isInteger(Number(edge.source)) || !Number.isInteger(Number(edge.target)) || edge.source < 0 || edge.target < 0 || edge.source >= count || edge.target >= count || edge.source === edge.target) errors.push(`架构 ${architecture.architectureId} 的芯片间拓扑边不合法`)
    for (const chip of partition.virtualQpus || []) for (const edge of chip.physicalCouplingMap || []) if (!Number.isInteger(Number(edge.source)) || !Number.isInteger(Number(edge.target)) || edge.source < 0 || edge.target < 0 || edge.source >= chip.physicalQubitCount || edge.target >= chip.physicalQubitCount || edge.source === edge.target) errors.push(`架构 ${architecture.architectureId} 的物理耦合边不合法`)
  }
  return errors
}

export function buildBondScanPayload(form) {
  return {
    molecule_type: 'LiH',
    scan: { start_distance_angstrom: Number(form.startDistance), end_distance_angstrom: Number(form.endDistance), point_count: Number(form.pointCount) },
    chemistry: { charge: Number(form.charge), spin_multiplicity: Number(form.spinMultiplicity), basis_set: form.basisSet, active_space_orbitals: Number(form.activeSpaceOrbitals), pauli_coefficient_cutoff: Number(form.pauliCoefficientCutoff), vqe: { ansatz_layers: Number(form.ansatzLayers), max_iterations: Number(form.maxIterations), convergence_tolerance: 0.0001, shots: 1024 } },
    deployment_architectures: form.architectures.map(architecture => ({
      architecture_id: architecture.architectureId,
      partition: { partition_count: Number(architecture.partition.partitionCount), partition_strategy: architecture.partition.partitionStrategy, inter_qpu_topology: architecture.partition.interQpuTopology.map(edge => ({ source: Number(edge.source), target: Number(edge.target) })), virtual_qpus: architecture.partition.virtualQpus.map(chip => ({ virtual_qpu_id: chip.virtualQpuId, physical_qubit_count: Number(chip.physicalQubitCount), physical_coupling_map: chip.physicalCouplingMap.map(edge => ({ source: Number(edge.source), target: Number(edge.target) })) })), initial_layout: architecture.partition.initialLayout, routing_method: architecture.partition.routingMethod },
    })),
  }
}

export function isBondScanTerminalStatus(status) { return BOND_SCAN_TERMINAL_STATUSES.includes(status) }

export function bondScanDeploymentReferenceView(scan = {}) {
  const result = scan.result || {}
  const value = result.engineering_only_deployment
  const issues = result.summary?.issues || []
  const hasLegacyReleaseGap = issues.some(issue => (typeof issue === 'string' ? issue : issue?.code) === 'legacy_result_missing_release_fields')

  if (value === true) return { kind: 'engineering', title: '仅工程部署证据', message: '当前部署使用优化器有效点，尚未形成可信的科学 VQE 最低点。' }
  if (value === false) return { kind: 'scientific', title: '科学验证点部署', message: '部署使用通过科学验证的 VQE 离散最低点。' }
  if (isBondScanTerminalStatus(scan.status) && hasLegacyReleaseGap) return { kind: 'legacy', title: '旧版结果，未记录部署依据', message: '旧版结果未提供 engineering_only_deployment，不能推断为科学验证后部署。' }
  if (!isBondScanTerminalStatus(scan.status)) return { kind: 'pending', title: '尚未形成部署结论', message: '部署参考点仍由后端计算中；当前不解释为科学验证后部署。' }
  return { kind: 'unknown', title: '未记录部署依据', message: '后端未提供部署依据，不能推断为科学验证后部署。' }
}

export function mergeMolecularBondScan(previous, next) {
  if (!previous) return next
  if (!next) return previous
  if (!previous.result || !next.result) return { ...previous, ...next, result: next.result || previous.result || null }
  const points = new Map((previous.result.points || []).map(point => [point.point_index, point]))
  for (const point of next.result.points || []) {
    const previousPoint = points.get(point.point_index) || {}
    points.set(point.point_index, mergeScanPoint(previousPoint, point))
  }
  return { ...previous, ...next, result: { ...previous.result, ...next.result, points: [...points.values()].sort((left, right) => left.point_index - right.point_index), summary: next.result.summary || previous.result.summary } }
}

function mergeScanPoint(previousPoint, nextPoint) {
  const merged = { ...previousPoint }
  for (const [key, value] of Object.entries(nextPoint)) {
    if (value !== null && value !== undefined) {
      merged[key] = key === 'fci_reference' && previousPoint.fci_reference
        ? mergeNonNullObject(previousPoint.fci_reference, value)
        : value
    }
  }
  return merged
}

function mergeNonNullObject(previous, next) {
  const merged = { ...previous }
  for (const [key, value] of Object.entries(next)) if (value !== null && value !== undefined) merged[key] = value
  return merged
}

function curvePoint(point, energy, needsReview) { return { pointIndex: point.point_index, distance: point.distance_angstrom, energy, needsReview, status: point.status, converged: point.vqe_converged } }
export function scanCurveSeries(points = []) {
  const completed = points.filter(point => point.status === 'completed')
  return {
    hf: completed.filter(point => point.hf_energy_hartree !== null && point.hf_energy_hartree !== undefined).map(point => curvePoint(point, point.hf_energy_hartree, point.validation_status === 'needs_review')),
    vqe: completed.filter(point => point.vqe_energy_hartree !== null && point.vqe_energy_hartree !== undefined).map(point => curvePoint(point, point.vqe_energy_hartree, point.validation_status === 'needs_review')),
    fci: completed.filter(point => point.fci_reference?.energy_hartree !== null && point.fci_reference?.energy_hartree !== undefined).map(point => curvePoint(point, point.fci_reference.energy_hartree, point.validation_status === 'needs_review')),
  }
}

export function scanMinimumCards(result = {}) {
  return [
    ['HF 离散最低点', result.hf_discrete_minimum],
    ['优化器通过的 VQE 离散最低点', result.vqe_discrete_minimum],
    ['科学验证后的 VQE 最低点', result.scientific_vqe_discrete_minimum],
    ['FCI 离散最低点', result.fci_discrete_minimum],
  ].map(([label, minimum]) => minimum ? { label, pointIndex: minimum.point_index, distance: minimum.distance_angstrom, energy: minimum.energy_hartree, minimumAtBoundary: minimum.minimum_at_boundary, message: minimum.message || null } : { label, pointIndex: null, distance: null, energy: null, minimumAtBoundary: false, message: null })
}

export function normalizeMolecularBondScanError(error) {
  const status = error?.response?.status ?? null
  const detail = error?.response?.data?.detail
  const business = detail && !Array.isArray(detail) && typeof detail === 'object' ? detail : {}
  const ids = { scanId: business.scan_id || null, pointIndex: business.point_index ?? null, molecularProblemId: business.molecular_problem_id || null, code: business.code || null, stage: business.stage || null }
  if (status === 401) return { ...ids, status, title: '登录状态失效', message: '请重新登录后恢复键长扫描。', retryable: false }
  if (status === 404) return { ...ids, status, title: '键长扫描不存在', message: business.message || 'Scan 不存在或不属于当前用户。', retryable: false }
  if (status === 409) return { ...ids, status, title: '幂等请求冲突', message: business.message || '该 Idempotency-Key 已关联不同请求。', retryable: false }
  if (status === 422 && Array.isArray(detail)) return { ...ids, status, title: '请求字段不合法', message: detail.map(item => `${(item.loc || []).filter(part => part !== 'body').join('.') || '请求参数'}：${item.msg}`).join('；'), retryable: false }
  if (status === 422) return { ...ids, status, title: '扫描不能执行', message: business.message || '请求未通过业务校验。', retryable: false }
  if (status === 503) return { ...ids, status, title: '服务暂不可用', message: business.message || '服务暂不可用；已保留已获得扫描点。', retryable: true }
  if (isNetworkFailure(error)) return { ...ids, status, title: '网络请求失败', message: '已保留已获得扫描点，可重试查询。', retryable: true }
  return { ...ids, status, title: '请求失败', message: business.message || detail || error?.message || '键长扫描请求未完成。', retryable: true }
}

export async function getMolecularBondScanCapabilities(options = {}) { const response = await (options.request || fetchMolecularBondScanCapabilitiesRequest)(); return response.data }
export async function submitMolecularBondScan(payload, options = {}) {
  const idempotencyKey = options.idempotencyKey || createIdempotencyKey()
  const request = options.request || createMolecularBondScanRequest
  const networkRetryCount = options.networkRetryCount ?? 1
  let retries = 0
  while (true) {
    try {
      const response = await request(payload, idempotencyKey)
      return { data: response.data, idempotencyKey }
    } catch (error) {
      if (!isNetworkFailure(error) || retries >= networkRetryCount) {
        error.idempotencyKey = idempotencyKey
        throw error
      }
      retries += 1
    }
  }
}
export async function getMolecularBondScan(scanId, options = {}) { const response = await (options.request || fetchMolecularBondScanRequest)(scanId); return response.data }
