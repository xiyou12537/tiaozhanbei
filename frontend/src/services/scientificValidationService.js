const VALIDATION_COPY = {
  optimizer: {
    passed: ['优化验证通过', '参数优化正常终止'],
    needs_review: ['优化结果需复核', '优化器未满足正常终止检查'],
  },
  scientific: {
    passed: ['科学验证通过', '结果通过参考能量、粒子数和化学精度检查'],
    needs_review: ['科学结果需复核', '线路仍可进行工程部署验证，但不能作为可信化学结论'],
    failed: ['科学验证失败', '结果未通过后端科学检查，不能作为可信化学结论'],
  },
  deployment: {
    passed: ['部署验证通过', '分区与路由后保持原线路能量'],
    needs_review: ['部署结果需复核', '分区与路由后的执行证据需要复核'],
    failed: ['部署验证失败', '分区或路由后的执行未通过后端验证'],
  },
}

export function scientificValidationView(domain, validation) {
  if (!validation || !validation.status) return { status: 'legacy', title: '旧版结果', message: '旧版结果，未提供该项验证' }
  const [title, message] = VALIDATION_COPY[domain]?.[validation.status] || ['验证状态未识别', '后端返回了未识别的验证状态']
  return { status: validation.status, title, message }
}

export function scanScientificErrorSeries(points = []) {
  return points
    .filter(point => point.status === 'completed' && point.vqe_fci_scientific_error_hartree !== null && point.vqe_fci_scientific_error_hartree !== undefined)
    .map(point => ({ pointIndex: point.point_index, distance: point.distance_angstrom, error: point.vqe_fci_scientific_error_hartree, needsReview: point.scientific_validation?.status !== 'passed' }))
}

export function circuitOperationMeta(operation, scope = 'intra_qpu') {
  const normalized = String(operation || '').toLowerCase()
  if (normalized === 'x') return { label: 'X', group: 'hf_initial_state', tone: 'initial' }
  if (normalized === 'swap') return { label: 'SWAP', group: 'routing_swap', tone: 'routing' }
  if (normalized === 'cx' && scope === 'inter_qpu') return { label: 'CX', group: 'inter_qpu_cx', tone: 'communication' }
  if (normalized === 'cx') return { label: 'CX', group: 'pauli_evolution', tone: 'entanglement' }
  if (['h', 's', 'sdg'].includes(normalized)) return { label: normalized.toUpperCase(), group: 'pauli_evolution', tone: 'basis' }
  if (normalized === 'rz') return { label: 'RZ', group: 'parameterized_excitation', tone: 'parameter' }
  if (normalized === 'ry') return { label: 'RY', group: 'legacy_parameterized_gate', tone: 'legacy' }
  return { label: normalized ? normalized.toUpperCase() : '—', group: 'unknown_gate', tone: 'unknown' }
}

export function implementationVersions(source = {}) {
  const vqe = source.vqe || source
  return {
    ansatz_name: vqe.ansatz ?? source.ansatz_name ?? null,
    ansatz_version: vqe.ansatz_version ?? source.ansatz_version ?? null,
    simulator_version: vqe.simulator_version ?? source.simulator_version ?? null,
    hamiltonian_builder_version: source.hamiltonian_builder_version ?? null,
    scientific_validation_version: source.scientific_validation_version ?? null,
  }
}

export function workflowExecutionHeadline(status, legacyValidationStatus) {
  if (status === 'completed') {
    return {
      title: 'Workflow 执行已完成',
      message: legacyValidationStatus
        ? '执行状态与旧版质量状态不代表优化、科学或部署验证结论；请查看下方三类独立验证。'
        : '执行状态不代表优化、科学或部署验证结论；请查看下方三类独立验证。',
    }
  }
  return {
    title: 'Workflow 执行状态待确认',
    message: '请查看后端执行状态与下方三类独立验证。',
  }
}
