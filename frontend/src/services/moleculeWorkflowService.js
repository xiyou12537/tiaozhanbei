import {
  createMoleculeWorkflowRequest,
  fetchMoleculeWorkflowHistoryRequest,
  fetchMoleculeWorkflowRequest,
} from '../api/moleculeWorkflowApi.js'

export const MOLECULE_STAGE_DEFINITIONS = [
  { id: 'input_validation', label: '输入校验' },
  { id: 'electronic_structure', label: '电子结构计算' },
  { id: 'active_space_selection', label: '活性空间选择' },
  { id: 'fermionic_hamiltonian', label: 'Fermionic Hamiltonian' },
  { id: 'qubit_mapping', label: 'Qubit Hamiltonian 映射' },
  { id: 'vqe_optimization', label: 'VQE 优化' },
  { id: 'circuit_partitioning', label: '线路分区' },
  { id: 'virtual_node_mapping', label: '虚拟节点映射' },
  { id: 'logical_distributed_simulation', label: '逻辑分布式模拟' },
]

export const MOLECULE_PRESETS = {
  H2: {
    moleculeName: 'H2',
    geometry: [
      { element: 'H', coordinates: [0, 0, 0] },
      { element: 'H', coordinates: [0, 0, 0.735] },
    ],
  },
  LiH: {
    moleculeName: 'LiH',
    geometry: [
      { element: 'Li', coordinates: [0, 0, 0] },
      { element: 'H', coordinates: [0, 0, 1.595] },
    ],
  },
  H2O: {
    moleculeName: 'H2O',
    geometry: [
      { element: 'O', coordinates: [0, 0, 0] },
      { element: 'H', coordinates: [0.7586, 0, 0.5043] },
      { element: 'H', coordinates: [-0.7586, 0, 0.5043] },
    ],
  },
}

export function clonePreset(name = 'H2') {
  const preset = MOLECULE_PRESETS[name] || MOLECULE_PRESETS.H2
  return {
    moleculeName: preset.moleculeName,
    charge: 0,
    spinMultiplicity: 1,
    basisSet: 'sto-3g',
    activeSpaceOrbitals: 2,
    pauliCoefficientCutoff: 0.000001,
    ansatzLayers: 1,
    maxIterations: 80,
    partitionCount: 2,
    topologyEdges: [{ source: 0, target: 1 }],
    geometry: preset.geometry.map(atom => ({
      element: atom.element,
      coordinates: [...atom.coordinates],
    })),
  }
}

export function buildMoleculeWorkflowPayload(form) {
  return {
    molecule_name: form.moleculeName.trim(),
    geometry: form.geometry.map(atom => ({
      element: atom.element.trim(),
      coordinates_angstrom: atom.coordinates.map(Number),
    })),
    charge: Number(form.charge),
    spin_multiplicity: Number(form.spinMultiplicity),
    basis_set: form.basisSet.trim(),
    mapping_method: 'jordan_wigner',
    active_space_orbitals: Number(form.activeSpaceOrbitals),
    pauli_coefficient_cutoff: Number(form.pauliCoefficientCutoff),
    vqe: {
      ansatz_layers: Number(form.ansatzLayers),
      max_iterations: Number(form.maxIterations),
      convergence_tolerance: 0.0001,
      shots: 1024,
    },
    partition: {
      partition_count: Number(form.partitionCount),
      topology_edges: form.topologyEdges.map(edge => ({
        source: Number(edge.source),
        target: Number(edge.target),
      })),
    },
    execution_mode: 'logical_virtual_qpu',
  }
}

export function validateMoleculeWorkflowForm(form) {
  const errors = []
  if (!form.moleculeName?.trim() || form.moleculeName.trim().length > 120) errors.push('分子名称长度必须为 1–120 个字符。')
  if (!Array.isArray(form.geometry) || form.geometry.length < 1 || form.geometry.length > 10) errors.push('原子数量必须为 1–10。')
  for (const [index, atom] of (form.geometry || []).entries()) {
    if (!/^[A-Z][a-z]?$/.test(atom.element?.trim() || '')) errors.push(`第 ${index + 1} 个原子的元素符号不合法。`)
    if (!Array.isArray(atom.coordinates) || atom.coordinates.length !== 3 || atom.coordinates.some(value => !Number.isFinite(Number(value)))) {
      errors.push(`第 ${index + 1} 个原子的三维坐标必须是有限数值。`)
    }
  }
  if (!Number.isInteger(Number(form.charge)) || Number(form.charge) < -10 || Number(form.charge) > 10) errors.push('电荷必须是 -10–10 的整数。')
  if (!Number.isInteger(Number(form.spinMultiplicity)) || Number(form.spinMultiplicity) < 1 || Number(form.spinMultiplicity) > 11) errors.push('自旋多重度必须是 1–11 的整数。')
  if (!/^[A-Za-z0-9+*(),._-]{2,64}$/.test(form.basisSet?.trim() || '')) errors.push('基组格式不合法。')
  if (!Number.isInteger(Number(form.activeSpaceOrbitals)) || Number(form.activeSpaceOrbitals) < 1 || Number(form.activeSpaceOrbitals) > 6) errors.push('活性空间轨道数必须是 1–6 的整数。')
  if (!(Number(form.pauliCoefficientCutoff) > 0 && Number(form.pauliCoefficientCutoff) <= 0.01)) errors.push('Pauli 截断阈值必须大于 0 且不超过 0.01。')
  if (!Number.isInteger(Number(form.ansatzLayers)) || Number(form.ansatzLayers) < 1 || Number(form.ansatzLayers) > 4) errors.push('VQE 层数必须是 1–4 的整数。')
  if (!Number.isInteger(Number(form.maxIterations)) || Number(form.maxIterations) < 1 || Number(form.maxIterations) > 500) errors.push('VQE 迭代数必须是 1–500 的整数。')
  const partitionCount = Number(form.partitionCount)
  if (!Number.isInteger(partitionCount) || partitionCount < 2 || partitionCount > 3) errors.push('分区数量必须是 2 或 3。')
  if (!Array.isArray(form.topologyEdges) || form.topologyEdges.length < 1 || form.topologyEdges.length > 3) errors.push('拓扑边数量必须为 1–3。')
  for (const [index, edge] of (form.topologyEdges || []).entries()) {
    const source = Number(edge.source)
    const target = Number(edge.target)
    if (!Number.isInteger(source) || !Number.isInteger(target) || source < 0 || target < 0 || source >= partitionCount || target >= partitionCount) {
      errors.push(`第 ${index + 1} 条拓扑边的节点必须在 0–${Math.max(partitionCount - 1, 0)} 范围内。`)
    } else if (source === target) {
      errors.push(`第 ${index + 1} 条拓扑边不允许自环。`)
    }
  }
  return errors
}

export function createIdempotencyKey() {
  const randomPart = globalThis.crypto?.randomUUID?.()
    || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `molwf-${randomPart}`
}

export function isNetworkFailure(error) {
  return !error?.response && error?.code !== 'ERR_CANCELED'
}

export async function submitMoleculeWorkflow(payload, options = {}) {
  const idempotencyKey = options.idempotencyKey || createIdempotencyKey()
  const request = options.request || createMoleculeWorkflowRequest
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

export async function getMoleculeWorkflow(workflowId) {
  const response = await fetchMoleculeWorkflowRequest(workflowId)
  return response.data
}

export async function listMoleculeWorkflows(filters, options = {}) {
  const request = options.request || fetchMoleculeWorkflowHistoryRequest
  const response = await request(filters)
  return response.data
}

function firstQueryValue(value) {
  return Array.isArray(value) ? value[0] : value
}

export function normalizeMoleculeWorkflowHistoryQuery(query = {}) {
  const filters = { page: 1, page_size: 20 }
  const issues = []
  const page = Number(firstQueryValue(query.page) ?? 1)
  const pageSize = Number(firstQueryValue(query.page_size) ?? 20)
  const moleculeNameValue = firstQueryValue(query.molecule_name)
  const moleculeName = typeof moleculeNameValue === 'string' ? moleculeNameValue.trim() : ''
  const status = firstQueryValue(query.status)
  const validationStatus = firstQueryValue(query.validation_status)

  if (Number.isInteger(page) && page >= 1) filters.page = page
  else issues.push('页码必须是大于等于 1 的整数。')

  if (Number.isInteger(pageSize) && pageSize >= 1 && pageSize <= 100) filters.page_size = pageSize
  else issues.push('每页数量必须是 1 到 100 的整数。')

  if (moleculeNameValue !== undefined) {
    if (moleculeName && moleculeName.length <= 120) filters.molecule_name = moleculeName
    else issues.push('分子名称必须是 1 到 120 个字符。')
  }

  if (status !== undefined) {
    if (['running', 'completed', 'failed'].includes(status)) filters.status = status
    else issues.push('执行状态筛选值不合法。')
  }

  if (validationStatus !== undefined) {
    if (['passed', 'needs_review'].includes(validationStatus)) filters.validation_status = validationStatus
    else issues.push('质量状态筛选值不合法。')
  }

  return { filters, issues }
}

export function formatMoleculeWorkflowHistoryValue(value, options = {}) {
  if (value === null || value === undefined || value === '') return '—'
  if (options.digits !== undefined) {
    const number = Number(value)
    return Number.isFinite(number) ? number.toFixed(options.digits) : '—'
  }
  return String(value)
}

export function moleculeWorkflowExecutionMeta(status) {
  return ({
    running: { label: '运行中', type: 'warning' },
    completed: { label: '已完成', type: 'info' },
    failed: { label: '失败', type: 'danger' },
  })[status] || { label: '—', type: 'info' }
}

export function moleculeWorkflowValidationMeta(status) {
  return ({
    passed: { label: '计算通过', type: 'success' },
    needs_review: { label: '需要复核', type: 'warning' },
  })[status] || { label: '—', type: 'info' }
}

export function canUseMoleculeWorkflowLocalFallback(error) {
  return isNetworkFailure(error) || Number(error?.response?.status) >= 500
}

export function normalizeMoleculeWorkflowHistoryError(error) {
  const status = error?.response?.status ?? null
  const detail = error?.response?.data?.detail
  if (status === 401) {
    return { ...normalizeMoleculeWorkflowError(error), retryable: false }
  }
  if (status === 422) {
    const message = Array.isArray(detail)
      ? detail.map(item => `${validationLocation(item) || '查询参数'}：${item.msg}`).join('；')
      : (detail?.message || detail || '查询参数不符合服务端约束。')
    return { status, title: '筛选条件不合法', message, retryable: false }
  }
  if (Number(status) >= 500) {
    return {
      status,
      title: '历史服务暂不可用',
      message: '未能从服务端读取任务历史，已保留当前已展示的数据。',
      retryable: true,
    }
  }
  if (isNetworkFailure(error)) {
    return {
      status: null,
      title: '网络请求失败',
      message: '未能连接任务历史服务，已保留当前已展示的数据。',
      retryable: true,
    }
  }
  return {
    status,
    title: '请求失败',
    message: detail?.message || detail || error?.message || '任务历史请求未完成。',
    retryable: true,
  }
}

function validationLocation(item) {
  return (item?.loc || []).filter(segment => segment !== 'body').join('.')
}

export function normalizeMoleculeWorkflowError(error) {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail
  const businessDetail = detail && !Array.isArray(detail) && typeof detail === 'object' ? detail : null
  const workflowId = businessDetail?.workflow_id || null

  if (status === 401) return { status, title: '登录状态失效', message: '登录状态已失效，请重新登录后再试。', workflowId }
  if (status === 404) return { status, title: 'Workflow 不存在', message: businessDetail?.message || 'Workflow 不存在或不属于当前用户。', workflowId }
  if (status === 409) return { status, title: '幂等请求冲突', message: businessDetail?.message || '该幂等任务仍在运行、请求内容冲突或已有失败记录。', stage: businessDetail?.stage, workflowId }
  if (status === 503) return { status, title: '计算运行时不可用', message: businessDetail?.message || 'PySCF/OpenFermion 运行时不可用，请稍后重试。', stage: businessDetail?.stage, workflowId }
  if (status === 422 && Array.isArray(detail)) {
    return {
      status,
      title: '表单字段不合法',
      message: detail.map(item => `${validationLocation(item) || '请求参数'}：${item.msg}`).join('；'),
      workflowId: null,
    }
  }
  if (status === 422) return { status, title: '计算输入不可执行', message: businessDetail?.message || '输入无法执行。', stage: businessDetail?.stage, workflowId }
  if (isNetworkFailure(error)) return { status: null, title: '网络请求失败', message: '未能连接计算服务，可使用原幂等 Key 重试。', workflowId: null, retryable: true }
  return { status, title: '请求失败', message: businessDetail?.message || detail || error?.message || '请求未完成。', stage: businessDetail?.stage, workflowId }
}

export function stageLabel(stageId) {
  return MOLECULE_STAGE_DEFINITIONS.find(stage => stage.id === stageId)?.label || stageId || '--'
}
