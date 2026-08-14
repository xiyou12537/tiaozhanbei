export const taskChoiceGuidance = [
  {
    id: 'workflow',
    title: '单次分子计算',
    description: '了解一个固定分子的计算结果。适合先从一个分子的能量、质量状态和模拟过程开始。',
    path: '/app/molecules',
    technicalNote: '会保留 Hamiltonian、VQE、分区和路由证据。',
  },
  {
    id: 'study',
    title: '方案比较',
    description: '比较不同分区和连接方案，找出在同一分子问题下更合适的逻辑部署方案。',
    path: '/app/molecular-studies/new',
    technicalNote: '同一分子问题只计算一次，再比较多种架构。',
  },
  {
    id: 'bond-scan',
    title: '键长扫描',
    description: '观察 LiH 距离变化与能量趋势，寻找值得进一步复核的离散区间。',
    path: '/app/molecular-bond-scans/new',
    technicalNote: '这是离散扫描，最低点是候选值，不等于精确平衡键长。',
  },
]

export const plainLanguageTerms = [
  ['Hamiltonian', '把分子的能量问题写成量子电路可处理的数学模型。'],
  ['VQE', '用一组可调参数反复寻找较低能量的计算方法；收敛不等于已经得到精确答案。'],
  ['HF', '一个较快的基准能量计算，用来提供参考起点。'],
  ['FCI', '在当前小问题和可用参考条件下更完整的对照计算；不可用时不会用 0 代替。'],
  ['活性空间', '本次重点纳入计算的一小组电子和轨道；范围越小，计算越聚焦但近似也更多。'],
  ['Pauli 项', 'Hamiltonian 拆成的可计算片段；阈值会过滤很小的项。'],
  ['Qubit', '量子计算中的信息单元；这里显示的是模拟所需的逻辑或物理映射数量。'],
  ['QPU', '量子处理器。本平台使用 logical_virtual_qpu 逻辑虚拟 QPU 模拟，不是实际硬件。'],
  ['分区', '把较大的电路按规则分到多个逻辑节点，便于评估分布式执行。'],
  ['拓扑', '节点之间允许连接的方式；它会影响可用路径和额外操作。'],
  ['SWAP', '为让两个不直接相连的 Qubit 交互而加入的换位操作，数量越多通常意味着路由开销越大。'],
  ['科学验证', '检查能量、粒子数、自旋和参考误差是否支持当前结果的科学解释。'],
  ['部署验证', '检查分区、映射、路由和逻辑分布式模拟是否按计划被实际使用。'],
]

const statusMeta = {
  queued: ['已排队', '任务已创建，尚未开始完整计算。', '等待任务进入执行后再查看结果。'],
  running: ['计算中', '任务正在执行，当前内容可能是部分结果。', '保留本页，等待状态更新。'],
  partial: ['部分完成', '已有部分结果，但不能把它当作完整结论。', '查看已完成部分，并等待或复核剩余步骤。'],
  completed: ['已完成', '任务已到达后端完成状态；仍需结合质量验证判断可否采用。', '查看质量与专业证据，再决定是否继续。'],
  failed: ['未完成', '任务没有形成完整结果。', '查看失败阶段和错误信息，修正后重试。'],
  needs_review: ['需要复核', '系统保留结果，但它不应被直接当作可靠结论。', '先查看质量问题和专业证据。'],
}

function present(value, suffix = '') {
  return value === null || value === undefined || value === '' ? '暂无可用结果' : `${value}${suffix}`
}

function statusSummary(status) {
  return statusMeta[status] || ['状态待确认', '后端没有提供可识别的状态，不能据此判断任务失败或通过。', '查看原始状态与技术证据后再判断。']
}

function qualitySummary(validationStatus, issues = []) {
  if (validationStatus === 'passed') return ['质量验证通过', '优化器、科学与部署验证的细节仍保留在下方。']
  if (validationStatus === 'needs_review' || issues.length) return ['需要复核', '存在质量问题或待复核信号，不能把结果直接当作结论。']
  if (validationStatus === 'failed') return ['质量验证未通过', '当前结果不应作为通过验证的结论使用。']
  return ['质量状态待确认', '没有足够的质量状态可用于判断结论可靠性。']
}

export function summarizeWorkflowForBeginners(result = {}) {
  const [status, statusReason, next] = statusSummary(result.status)
  const [confidence, confidenceReason] = qualitySummary(result.validation_status, result.validation_issues || [])
  return {
    status,
    statusReason,
    keyResult: `分布式模拟能量：${present(result.energies?.distributed_simulation_energy_hartree, ' Ha')}`,
    confidence,
    confidenceReason,
    next,
  }
}

export function summarizeStudyForBeginners(study = {}) {
  const [status, statusReason, next] = statusSummary(study.status)
  const evaluations = study.result?.deployment_evaluations || []
  const deployable = evaluations.filter(item => item?.is_deployable === true).length
  const failed = evaluations.filter(item => item?.status === 'failed').length
  const confidence = failed ? '方案比较包含失败项' : study.status === 'completed' ? '比较结果待结合每项验证阅读' : '比较仍在进行或状态待确认'
  const confidenceReason = failed ? '失败项没有被当作可部署方案。' : '每个方案的科学与部署验证都保留在下方。'
  return {
    status,
    statusReason,
    keyResult: evaluations.length ? `${deployable} / ${evaluations.length} 个方案标记为可部署` : '尚无可比较的部署方案结果',
    confidence,
    confidenceReason,
    next,
  }
}

export function summarizeBondScanForBeginners(scan = {}) {
  const [status, statusReason, next] = statusSummary(scan.status)
  const result = scan.result || {}
  const minimum = result.scientific_vqe_discrete_minimum
  const confidence = minimum ? '存在通过科学验证的离散候选点' : scan.status === 'completed' ? '没有通过科学验证的离散候选点' : '趋势仍在生成，暂不能下结论'
  const confidenceReason = minimum
    ? '候选点只代表当前扫描网格中的离散最小值，不等于精确平衡键长。'
    : '不会把未验证、缺失或失败的点表示成可靠最低点。'
  return {
    status,
    statusReason,
    keyResult: minimum ? `值得复核的离散候选距离：${present(minimum.distance_angstrom, ' Å')}` : '尚无通过科学验证的离散候选距离',
    confidence,
    confidenceReason,
    next,
  }
}
