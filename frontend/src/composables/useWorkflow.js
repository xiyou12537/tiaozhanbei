import { computed, reactive } from 'vue'
import { presetCases } from '../platform'
import {
  buildStageStatusMap,
  createInitialStageStatusMap,
  mapWorkflowProgress,
  sortStagesForDisplay,
  stageTitleMap,
} from '../services/workflowMappers'
import {
  cancelWorkflow,
  fetchWorkflowBootstrap,
  fetchWorkflowBundle,
  submitWorkflow,
} from '../services/workflowService'
import { upsertArchivedWorkflow } from '../services/workflowArchiveStorage'

const fallbackCandidates = [
  {
    name: 'Li2S6',
    family: 'lithium-polysulfide',
    adsorptionStrength: 0.82,
    focus: '联调文档默认候选材料',
    note: '当前端仓库尚未与平台接口完全同步时，工作台先使用联调文档中的示例候选值。',
  },
  {
    name: 'Fe-N4',
    family: 'single-atom-catalyst',
    adsorptionStrength: 0.89,
    focus: '平台展示案例',
    note: '适合作为工作台默认案例，便于演示完整流程。',
  },
]

function createFallbackCases() {
  return presetCases.map((item, index) => ({
    id: `fallback-case-${index + 1}`,
    title: item.name,
    candidateMaterial: item.name,
  }))
}

const workflowState = reactive({
  apiReady: true,
  apiVersion: '',
  healthStatus: 'unknown',
  bootstrapLoaded: false,
  bootstrapLoading: false,
  bootstrapError: '',
  cases: [],
  candidates: [],
  selectedCaseId: '',
  selectedCandidate: '',
  executionMode: 'queued',
  qasmContent: '',
  workflowId: '',
  workflowDetail: null,
  stageRunList: [],
  eventLogs: [],
  resultView: null,
  resultSummary: null,
  artifacts: null,
  pollingActive: false,
  pollingTimer: null,
  progressPercent: 0,
  progressText: '等待创建实验',
  circuit: null,
  taskId: null,
  partitionResult: null,
  edgeCosts: null,
  targetEdges: [],
  mapping: null,
  topoComparisons: null,
  workflowStatus: 'idle',
  currentStage: 'created',
  stageRuns: createInitialStageStatusMap(),
  lastError: '',
})

function clearPolling() {
  if (workflowState.pollingTimer) {
    clearTimeout(workflowState.pollingTimer)
    workflowState.pollingTimer = null
  }
  workflowState.pollingActive = false
}

function persistWorkflowArchive() {
  if (!workflowState.workflowId) return

  upsertArchivedWorkflow({
    workflowId: workflowState.workflowId,
    overallStatus: workflowState.workflowStatus,
    currentStage: workflowState.currentStage,
    completedStageCount: workflowState.workflowDetail?.completed_stage_count ?? 0,
    totalStageCount: workflowState.workflowDetail?.total_stage_count ?? 7,
    candidateMaterial:
      workflowState.workflowDetail?.candidate_material ||
      workflowState.resultView?.candidateMaterial ||
      workflowState.selectedCandidate ||
      '',
    executionMode: workflowState.executionMode,
    progressPercent: workflowState.progressPercent,
    progressText: workflowState.progressText,
    resultSummary: workflowState.resultSummary?.summary || workflowState.resultView?.summary || null,
    scientificSnapshot: workflowState.resultView?.scientificSnapshot || null,
    artifacts: workflowState.artifacts || workflowState.resultView?.artifacts || null,
    stageRunList: workflowState.stageRunList,
    eventLogs: workflowState.eventLogs,
    updatedAt: new Date().toISOString(),
  })
}

function applyWorkflowBundle(bundle) {
  workflowState.workflowDetail = bundle.detail
  workflowState.stageRunList = sortStagesForDisplay(bundle.stages || [])
  workflowState.eventLogs = bundle.events || []
  workflowState.resultSummary = bundle.summary
  workflowState.resultView = bundle.resultView
  workflowState.artifacts = bundle.artifacts
  workflowState.workflowStatus = bundle.detail?.overall_status || 'idle'
  workflowState.currentStage = bundle.detail?.current_stage || 'created'
  workflowState.stageRuns = buildStageStatusMap(workflowState.stageRunList, bundle.detail)

  const progress = mapWorkflowProgress(bundle.detail)
  workflowState.progressPercent = progress.percent
  workflowState.progressText = progress.text
  persistWorkflowArchive()
}

export function useWorkflow() {
  const currentCase = computed(
    () => workflowState.cases.find(item => item.id === workflowState.selectedCaseId) || null
  )

  const currentCandidate = computed(
    () => workflowState.candidates.find(item => item.name === workflowState.selectedCandidate) || null
  )

  const workflowStageTitle = computed(
    () => stageTitleMap[workflowState.currentStage] || '等待创建'
  )

  async function loadBootstrap(force = false) {
    if (workflowState.bootstrapLoaded && !force) return

    workflowState.bootstrapLoading = true
    workflowState.bootstrapError = ''

    try {
      const payload = await fetchWorkflowBootstrap()
      workflowState.apiReady = payload.apiReady
      workflowState.apiVersion = payload.version || ''
      workflowState.healthStatus = payload.health?.status || (payload.apiReady ? 'ok' : 'unknown')
      workflowState.cases = payload.cases.length ? payload.cases : createFallbackCases()
      workflowState.candidates = payload.candidates.length ? payload.candidates : fallbackCandidates

      if (!payload.apiReady) {
        workflowState.bootstrapError =
          '平台工作流接口尚未完全接通，工作台已切换为联调占位数据。'
      }

      if (!workflowState.selectedCaseId && workflowState.cases.length) {
        workflowState.selectedCaseId = workflowState.cases[0].id
      }
      if (!workflowState.selectedCandidate && workflowState.candidates.length) {
        workflowState.selectedCandidate = workflowState.candidates[0].name
      }

      workflowState.bootstrapLoaded = true
    } catch (error) {
      workflowState.apiReady = false
      workflowState.apiVersion = ''
      workflowState.healthStatus = 'unreachable'
      workflowState.bootstrapError =
        error.response?.data?.detail || error.message || '加载工作台初始化数据失败'
      workflowState.cases = createFallbackCases()
      workflowState.candidates = fallbackCandidates
      workflowState.selectedCaseId ||= workflowState.cases[0]?.id || ''
      workflowState.selectedCandidate ||= workflowState.candidates[0]?.name || ''
    } finally {
      workflowState.bootstrapLoading = false
    }
  }

  async function refreshWorkflowBundle() {
    if (!workflowState.workflowId) return null
    const bundle = await fetchWorkflowBundle(workflowState.workflowId)
    applyWorkflowBundle(bundle)
    return bundle
  }

  async function createWorkflow() {
    workflowState.lastError = ''

    const payload = {
      case_id: workflowState.selectedCaseId || null,
      candidate_material: workflowState.selectedCandidate,
      qasm_content: workflowState.qasmContent || null,
      execution_mode: workflowState.executionMode,
    }

    const data = await submitWorkflow(payload)
    workflowState.workflowId = data.workflow_id
    workflowState.workflowStatus = data.overall_status || 'created'
    workflowState.currentStage = data.current_stage || 'screening'
    workflowState.progressText = '任务已创建，等待执行'
    workflowState.progressPercent = 0
    workflowState.stageRuns = {
      ...createInitialStageStatusMap(),
      created: 'success',
      screening: data.current_stage === 'screening' ? 'running' : 'pending',
    }
    persistWorkflowArchive()

    if (workflowState.executionMode === 'queued') {
      startPolling()
    } else {
      await refreshWorkflowBundle()
    }

    return data
  }

  async function pollWorkflow() {
    try {
      const bundle = await refreshWorkflowBundle()
      const finished = ['completed', 'cancelled'].includes(bundle.detail?.overall_status)
      if (finished) {
        clearPolling()
        return
      }

      workflowState.pollingTimer = setTimeout(pollWorkflow, 2000)
    } catch (error) {
      workflowState.lastError =
        error.response?.data?.detail || error.message || '轮询工作流失败'
      clearPolling()
    }
  }

  function startPolling() {
    clearPolling()
    workflowState.pollingActive = true
    workflowState.pollingTimer = setTimeout(pollWorkflow, 300)
  }

  async function stopWorkflow() {
    if (!workflowState.workflowId) return
    await cancelWorkflow(workflowState.workflowId)
    await refreshWorkflowBundle()
    clearPolling()
    persistWorkflowArchive()
  }

  function resetWorkflow() {
    clearPolling()
    workflowState.workflowId = ''
    workflowState.workflowDetail = null
    workflowState.stageRunList = []
    workflowState.eventLogs = []
    workflowState.resultView = null
    workflowState.resultSummary = null
    workflowState.artifacts = null
    workflowState.progressPercent = 0
    workflowState.progressText = '等待创建实验'
    workflowState.workflowStatus = 'idle'
    workflowState.currentStage = 'created'
    workflowState.stageRuns = createInitialStageStatusMap()
    workflowState.lastError = ''
  }

  return {
    workflowState,
    currentCase,
    currentCandidate,
    workflowStageTitle,
    loadBootstrap,
    createWorkflow,
    refreshWorkflowBundle,
    startPolling,
    stopWorkflow,
    resetWorkflow,
    clearPolling,
  }
}
