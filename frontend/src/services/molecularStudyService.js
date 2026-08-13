import { createMolecularStudyRequest, fetchMolecularStudyRequest } from '../api/molecularStudyApi.js'
import { clonePreset } from './moleculeWorkflowService.js'

export const MOLECULAR_STUDY_RUNNING_STATUSES = ['queued', 'running']
export const MOLECULAR_STUDY_TERMINAL_STATUSES = ['completed', 'failed']

const ARCHITECTURE_ID_PATTERN = /^[A-Za-z0-9._:-]{1,64}$/

function lineCouplingMap(qubitCount) {
  return Array.from({ length: Math.max(Number(qubitCount) - 1, 0) }, (_, index) => ({ source: index, target: index + 1 }))
}

function createPartition(seed, partitionCount = 2) {
  return {
    partitionCount,
    partitionStrategy: 'sequential_greedy',
    interQpuTopology: Array.from({ length: Math.max(partitionCount - 1, 0) }, (_, index) => ({ source: index, target: index + 1 })),
    virtualQpus: Array.from({ length: partitionCount }, (_, index) => ({
      virtualQpuId: `${seed}-QPU-${index + 1}`,
      physicalQubitCount: 4,
      physicalCouplingMap: lineCouplingMap(4),
    })),
    initialLayout: 'identity',
    routingMethod: 'shortest_path_swap',
  }
}

export function createArchitecture(index = 1) {
  const architectureId = `architecture-${index}`
  return { architectureId, partition: createPartition(`A${index}`) }
}

export function cloneStudyArchitecture(architecture, index) {
  const cloned = structuredClone(architecture)
  cloned.architectureId = `${architecture.architectureId}-copy-${index}`.slice(0, 64)
  cloned.partition.virtualQpus = cloned.partition.virtualQpus.map((chip, chipIndex) => ({
    ...chip,
    virtualQpuId: `${cloned.architectureId}-QPU-${chipIndex + 1}`.slice(0, 64),
  }))
  return cloned
}

export function createMolecularStudyForm(presetName = 'H2') {
  const molecule = clonePreset(presetName)
  return {
    moleculeName: molecule.moleculeName,
    geometry: molecule.geometry,
    charge: molecule.charge,
    spinMultiplicity: molecule.spinMultiplicity,
    basisSet: molecule.basisSet,
    activeSpaceOrbitals: molecule.activeSpaceOrbitals,
    pauliCoefficientCutoff: molecule.pauliCoefficientCutoff,
    ansatzLayers: molecule.ansatzLayers,
    maxIterations: molecule.maxIterations,
    architectures: [createArchitecture(1), createArchitecture(2), createArchitecture(3)],
  }
}

function finiteInteger(value) {
  return Number.isInteger(Number(value))
}

function validateTopology(edges, nodeCount, label, errors, required = true) {
  if (!Array.isArray(edges) || edges.length < 1) {
    if (required) errors.push(`${label}至少需要一条边`)
    return
  }
  for (const [edgeIndex, edge] of edges.entries()) {
    const source = Number(edge.source)
    const target = Number(edge.target)
    if (!Number.isInteger(source) || !Number.isInteger(target) || source < 0 || target < 0 || source >= nodeCount || target >= nodeCount || source === target) {
      errors.push(`${label}第 ${edgeIndex + 1} 条边不合法`)
    }
  }
}

export function validateMolecularStudyForm(form) {
  const errors = []
  if (!form.moleculeName?.trim()) errors.push('请填写分子名称')
  if (!Array.isArray(form.geometry) || form.geometry.length < 1) errors.push('至少需要一个原子')
  for (const [atomIndex, atom] of (form.geometry || []).entries()) {
    if (!/^[A-Z][a-z]?$/.test(atom.element?.trim() || '')) errors.push(`第 ${atomIndex + 1} 个原子的元素符号不合法`)
    if (!Array.isArray(atom.coordinates) || atom.coordinates.length !== 3 || atom.coordinates.some(value => !Number.isFinite(Number(value)))) errors.push(`第 ${atomIndex + 1} 个原子的三维坐标不合法`)
  }
  if (!finiteInteger(form.charge)) errors.push('电荷必须是整数')
  if (!finiteInteger(form.spinMultiplicity) || Number(form.spinMultiplicity) < 1) errors.push('自旋多重度必须是正整数')
  if (!form.basisSet?.trim()) errors.push('请选择基组')
  if (!finiteInteger(form.activeSpaceOrbitals) || Number(form.activeSpaceOrbitals) < 1 || Number(form.activeSpaceOrbitals) > 6) errors.push('活性空间轨道数必须在 1 到 6 之间')
  if (!(Number(form.pauliCoefficientCutoff) > 0 && Number(form.pauliCoefficientCutoff) <= 0.01)) errors.push('Pauli 截断阈值必须大于 0 且不大于 0.01')
  if (!finiteInteger(form.ansatzLayers) || Number(form.ansatzLayers) < 1 || Number(form.ansatzLayers) > 4) errors.push('VQE 层数必须在 1 到 4 之间')
  if (!finiteInteger(form.maxIterations) || Number(form.maxIterations) < 1 || Number(form.maxIterations) > 500) errors.push('VQE 迭代预算必须在 1 到 500 之间')

  const architectures = form.architectures || []
  if (architectures.length < 3) errors.push('至少需要 3 个架构方案')
  if (architectures.length > 12) errors.push('架构方案不能超过 12 个')
  const seenIds = new Set()
  for (const [architectureIndex, architecture] of architectures.entries()) {
    const prefix = `架构 ${architectureIndex + 1}`
    const architectureId = architecture.architectureId?.trim() || ''
    if (!ARCHITECTURE_ID_PATTERN.test(architectureId)) errors.push(`${prefix}的架构 ID 不符合契约`)
    if (seenIds.has(architectureId)) errors.push('架构 ID 必须唯一')
    seenIds.add(architectureId)
    const partition = architecture.partition || {}
    const partitionCount = Number(partition.partitionCount)
    if (!Number.isInteger(partitionCount) || partitionCount < 2 || partitionCount > 3) errors.push(`${prefix}的分区数量必须在 2 到 3 之间`)
    validateTopology(partition.interQpuTopology, partitionCount, `${prefix}的芯片间拓扑边`, errors)
    if (!Array.isArray(partition.virtualQpus) || partition.virtualQpus.length !== partitionCount) errors.push(`${prefix}的虚拟 QPU 数量必须与分区数量一致`)
    const chipIds = new Set()
    for (const [chipIndex, chip] of (partition.virtualQpus || []).entries()) {
      const chipId = chip.virtualQpuId?.trim() || ''
      if (!ARCHITECTURE_ID_PATTERN.test(chipId) || chipIds.has(chipId)) errors.push(`${prefix}的虚拟 QPU ID 不合法或重复`)
      chipIds.add(chipId)
      const physicalQubitCount = Number(chip.physicalQubitCount)
      if (!Number.isInteger(physicalQubitCount) || physicalQubitCount < 1 || physicalQubitCount > 12) errors.push(`${prefix}的物理量子比特数必须在 1 到 12 之间`)
      validateTopology(chip.physicalCouplingMap, physicalQubitCount, `${prefix}的物理耦合边`, errors, false)
    }
  }
  return errors
}

export function buildMolecularStudyPayload(form) {
  return {
    molecule_name: form.moleculeName.trim(),
    geometry: form.geometry.map(atom => ({ element: atom.element.trim(), coordinates_angstrom: atom.coordinates.map(Number) })),
    charge: Number(form.charge),
    spin_multiplicity: Number(form.spinMultiplicity),
    basis_set: form.basisSet.trim(),
    mapping_method: 'jordan_wigner',
    active_space_orbitals: Number(form.activeSpaceOrbitals),
    pauli_coefficient_cutoff: Number(form.pauliCoefficientCutoff),
    vqe: { ansatz_layers: Number(form.ansatzLayers), max_iterations: Number(form.maxIterations), convergence_tolerance: 0.0001, shots: 1024 },
    execution_mode: 'logical_virtual_qpu',
    architectures: form.architectures.map(architecture => ({
      architecture_id: architecture.architectureId.trim(),
      partition: {
        partition_count: Number(architecture.partition.partitionCount),
        partition_strategy: architecture.partition.partitionStrategy,
        inter_qpu_topology: architecture.partition.interQpuTopology.map(edge => ({ source: Number(edge.source), target: Number(edge.target) })),
        virtual_qpus: architecture.partition.virtualQpus.map(chip => ({
          virtual_qpu_id: chip.virtualQpuId.trim(),
          physical_qubit_count: Number(chip.physicalQubitCount),
          physical_coupling_map: chip.physicalCouplingMap.map(edge => ({ source: Number(edge.source), target: Number(edge.target) })),
        })),
        initial_layout: architecture.partition.initialLayout,
        routing_method: architecture.partition.routingMethod,
      },
    })),
  }
}

export function isMolecularStudyTerminalStatus(status) {
  return MOLECULAR_STUDY_TERMINAL_STATUSES.includes(status)
}

export function resolveMolecularProblemId(study) {
  return study?.molecular_problem_id ?? study?.problem_id ?? null
}

function evaluationIdentity(evaluation) {
  return evaluation?.evaluation_id || evaluation?.architecture_id
}

export function mergeMolecularStudy(previous, next) {
  if (!previous) return next
  if (!next) return previous
  const previousResult = previous.result
  const nextResult = next.result
  if (!previousResult || !nextResult) return { ...previous, ...next, molecular_problem_id: resolveMolecularProblemId(next) || resolveMolecularProblemId(previous), result: nextResult || previousResult || null }
  const evaluations = new Map((previousResult.deployment_evaluations || []).map(item => [evaluationIdentity(item), item]))
  for (const item of nextResult.deployment_evaluations || []) evaluations.set(evaluationIdentity(item), item)
  return {
    ...previous,
    ...next,
    molecular_problem_id: resolveMolecularProblemId(next) || resolveMolecularProblemId(previous),
    result: {
      ...previousResult,
      ...nextResult,
      molecular_problem: nextResult.molecular_problem || previousResult.molecular_problem || null,
      deployment_evaluations: [...evaluations.values()],
      summary: nextResult.summary || previousResult.summary || null,
    },
  }
}

function validationLocation(item) {
  return (item?.loc || []).filter(segment => segment !== 'body').join('.')
}

export function normalizeMolecularStudyError(error) {
  const status = error?.response?.status ?? null
  const detail = error?.response?.data?.detail
  const business = detail && !Array.isArray(detail) && typeof detail === 'object' ? detail : {}
  const shared = {
    status,
    code: business.code || null,
    stage: business.stage || null,
    studyId: business.study_id || null,
    molecularProblemId: business.molecular_problem_id || null,
    architectureId: business.architecture_id || null,
  }
  if (status === 401) return { ...shared, title: '登录状态失效', message: '请重新登录后恢复此 Study。', retryable: false }
  if (status === 404) return { ...shared, title: 'Study 不存在', message: business.message || 'Study 不存在或不属于当前用户。', retryable: false }
  if (status === 422 && Array.isArray(detail)) return { ...shared, title: '请求字段不合法', message: detail.map(item => `${validationLocation(item) || '请求参数'}：${item.msg}`).join('；'), fieldErrors: detail, retryable: false }
  if (status === 422) return { ...shared, title: 'Study 不能执行', message: business.message || '请求未通过业务校验。', retryable: false }
  if (status === 503) return { ...shared, title: '服务暂不可用', message: business.message || '调度或运行时暂不可用；已保留当前结果，可仅重试查询。', retryable: true }
  if (!error?.response) return { ...shared, title: '网络请求失败', message: '未能连接 Study 服务；已保留当前结果，可仅重试查询。', retryable: true }
  return { ...shared, title: '请求失败', message: business.message || detail || error?.message || 'Study 请求未完成。', retryable: true }
}

export function formatStudyValue(value, digits) {
  if (value === null || value === undefined || value === '') return '—'
  if (digits === undefined) return String(value)
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '—'
}

export async function submitMolecularStudy(payload, options = {}) {
  const request = options.request || createMolecularStudyRequest
  const response = await request(payload)
  return response.data
}

export async function getMolecularStudy(studyId, options = {}) {
  const request = options.request || fetchMolecularStudyRequest
  const response = await request(studyId)
  return response.data
}
