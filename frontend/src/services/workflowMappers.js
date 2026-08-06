const STAGE_ORDER = [
  'created',
  'screening',
  'chem_modeling',
  'quantum_encoding',
  'distributed_compiling',
  'simulation_evaluating',
  'scoring',
  'aggregating',
  'completed',
]

export const stageTitleMap = {
  created: '任务创建',
  screening: '候选筛选',
  chem_modeling: '化学建模',
  quantum_encoding: '量子编码',
  distributed_compiling: '分布式编译',
  simulation_evaluating: '模拟评估',
  scoring: '综合评分',
  aggregating: '结果聚合',
  completed: '任务完成',
  cancelled: '已取消',
}

export function createInitialStageStatusMap() {
  return {
    created: 'pending',
    screening: 'pending',
    chem_modeling: 'pending',
    quantum_encoding: 'pending',
    distributed_compiling: 'pending',
    simulation_evaluating: 'pending',
    scoring: 'pending',
    aggregating: 'pending',
    completed: 'pending',
  }
}

export function mapCandidates(rawList = []) {
  return rawList.map(item => ({
    name: item.candidate_name,
    family: item.family,
    adsorptionStrength: item.adsorption_strength,
    materialId: item.material_id || '',
    materialName: item.material_name || item.candidate_name,
    materialFamily: item.material_family || item.family,
    focus: item.family || 'candidate',
    note: `吸附强度 ${item.adsorption_strength ?? '--'}，可作为候选筛选输入。`,
    raw: item,
  }))
}

export function mapCases(rawList = []) {
  return rawList.map(item => ({
    id: item.case_id,
    title: item.title,
    candidateMaterial: item.candidate_material,
  }))
}

export function mapStageRuns(rawList = []) {
  return rawList.map((item, index) => ({
    id: `${item.stage_name}-${index + 1}`,
    stageName: item.stage_name,
    stageTitle: stageTitleMap[item.stage_name] || item.stage_name,
    stageStatus: item.stage_status,
    attemptNo: item.attempt_no,
    serviceName: item.service_name,
    output: item.output || {},
  }))
}

export function buildStageStatusMap(rawStageRuns = [], detail = null) {
  const stageStatusMap = createInitialStageStatusMap()
  stageStatusMap.created = detail?.workflow_id ? 'success' : 'pending'

  rawStageRuns.forEach(item => {
    stageStatusMap[item.stage_name] = item.stage_status
  })

  if (detail?.overall_status === 'completed') {
    stageStatusMap.completed = 'success'
  } else if (detail?.overall_status === 'cancelled') {
    stageStatusMap.completed = 'skipped'
  } else if (detail?.current_stage && stageStatusMap[detail.current_stage] === 'pending') {
    stageStatusMap[detail.current_stage] = 'running'
  }

  return stageStatusMap
}

export function mapWorkflowProgress(detail = null) {
  if (!detail?.total_stage_count) {
    return { percent: 0, text: '等待创建实验' }
  }

  const percent = Math.round((detail.completed_stage_count / detail.total_stage_count) * 100)
  const currentStageText = stageTitleMap[detail.current_stage] || detail.current_stage

  if (detail.overall_status === 'completed') {
    return { percent: 100, text: '已完成' }
  }

  if (detail.overall_status === 'cancelled') {
    return { percent, text: '已取消' }
  }

  return { percent, text: `执行中：${currentStageText}` }
}

export function mapResultView(response = null) {
  if (!response?.result_view) return null

  const resultView = response.result_view
  return {
    workflowId: response.workflow_id,
    overallStatus: response.overall_status,
    candidateMaterial: response.candidate_material,
    candidateName: resultView.candidate_name,
    summary: resultView.summary || {},
    scientificSnapshot: resultView.scientific_snapshot || {},
    artifacts: resultView.artifacts || {},
  }
}

export function mapEventLogs(rawList = []) {
  return rawList.map(item => ({
    index: item.event_index,
    eventType: item.event_type,
    stageName: item.stage_name,
    stageTitle: item.stage_name ? stageTitleMap[item.stage_name] || item.stage_name : '工作流',
    payload: item.payload || {},
  }))
}

export function mapSummary(response = null) {
  if (!response?.summary) return null
  return {
    workflowId: response.workflow_id,
    currentStage: response.current_stage,
    overallStatus: response.overall_status,
    summary: response.summary,
  }
}

export function mapArtifacts(response = null) {
  return response?.artifacts || null
}

export function sortStagesForDisplay(stageRuns = []) {
  return [...stageRuns].sort((left, right) => {
    const leftIndex = STAGE_ORDER.indexOf(left.stageName)
    const rightIndex = STAGE_ORDER.indexOf(right.stageName)
    return leftIndex - rightIndex
  })
}
