import { computed, reactive } from 'vue'
import {
  fetchCandidateExplanation,
  fetchScreeningCandidates,
  fetchScreeningStageBundle,
  fetchScreeningWorkflowBundle,
  submitScreeningWorkflow,
} from '../services/screeningWorkflowService'
import {
  readCurrentScreeningWorkflow,
  saveScreeningWorkflowArchive,
} from '../services/screeningArchiveStorage'

const MIN_SELECTED_CANDIDATES = 3

const screeningState = reactive({
  candidates: [],
  selectedCandidates: [],
  screeningWorkflowId: '',
  screeningWorkflowPayload: null,
  workflowStatus: 'idle',
  candidateCount: 0,
  recommendedMaterial: '',
  candidateResults: [],
  classicalScreeningResults: [],
  quantumRefinementResults: [],
  leaderboard: [],
  selectedMaterialId: '',
  selectedMaterialName: '',
  selectedMaterialExplanation: null,
  loadingCandidates: false,
  submitting: false,
  loadingBundle: false,
  loadingExplanation: false,
  lastError: '',
})

function persistScreeningWorkflow() {
  if (!screeningState.screeningWorkflowId) return
  saveScreeningWorkflowArchive(buildScreeningArchiveRecord())
}

export function useScreeningWorkflow() {
  const selectedCandidateCount = computed(() => screeningState.selectedCandidates.length)
  const canSubmitScreening = computed(() => selectedCandidateCount.value >= MIN_SELECTED_CANDIDATES)

  const selectedMaterial = computed(() => {
    return (
      screeningState.candidateResults.find(
        item =>
          item.materialProfile.materialId === screeningState.selectedMaterialId ||
          item.candidateMaterial === screeningState.selectedMaterialName
      ) || null
    )
  })

  const selectedLeaderboardRow = computed(() => {
    return (
      screeningState.leaderboard.find(
        item =>
          item.candidateMaterial === screeningState.selectedMaterialName ||
          item.candidateMaterial === selectedMaterial.value?.candidateMaterial
      ) || screeningState.leaderboard[0] || null
    )
  })

  async function loadCandidates(force = false) {
    if (screeningState.candidates.length && !force) return screeningState.candidates

    screeningState.loadingCandidates = true
    screeningState.lastError = ''
    try {
      screeningState.candidates = await fetchScreeningCandidates()
      if (!screeningState.selectedCandidates.length) {
        screeningState.selectedCandidates = screeningState.candidates.slice(0, 3).map(item => item.name)
      }
      return screeningState.candidates
    } catch (error) {
      screeningState.lastError = error.response?.data?.detail || error.message || '候选材料加载失败'
      throw error
    } finally {
      screeningState.loadingCandidates = false
    }
  }

  function toggleCandidate(candidateName) {
    const exists = screeningState.selectedCandidates.includes(candidateName)
    if (exists) {
      screeningState.selectedCandidates = screeningState.selectedCandidates.filter(item => item !== candidateName)
      return
    }
    screeningState.selectedCandidates = [...screeningState.selectedCandidates, candidateName]
  }

  async function createScreeningWorkflow() {
    if (!canSubmitScreening.value) {
      throw new Error(`至少选择 ${MIN_SELECTED_CANDIDATES} 个候选材料`)
    }

    screeningState.submitting = true
    screeningState.lastError = ''
    try {
      const payload = {
        caseId: 'li-s-demo',
        candidateMaterials: screeningState.selectedCandidates,
      }
      const created = await submitScreeningWorkflow(payload)
      screeningState.screeningWorkflowId = created.workflowId
      screeningState.workflowStatus = created.status
      screeningState.candidateCount = created.candidateCount
      screeningState.recommendedMaterial = created.recommendedMaterial
      screeningState.screeningWorkflowPayload = {
        ...payload,
        caseId: created.caseId || payload.caseId,
        createdAt: created.createdAt,
        updatedAt: created.updatedAt,
      }
      persistScreeningWorkflow()
      await refreshScreeningWorkflow(created.workflowId)
      return created
    } catch (error) {
      screeningState.lastError = error.response?.data?.detail || error.message || '多材料筛选任务创建失败'
      throw error
    } finally {
      screeningState.submitting = false
    }
  }

  async function refreshScreeningWorkflow(workflowId = screeningState.screeningWorkflowId) {
    if (!workflowId) return null

    screeningState.loadingBundle = true
    screeningState.lastError = ''
    try {
      const bundle = await fetchScreeningWorkflowBundle(workflowId)
      applyScreeningWorkflowBundle(bundle)

      const stageBundle = await fetchScreeningStageBundle(workflowId)
      if (stageBundle.classicalScreening.length) {
        screeningState.classicalScreeningResults = stageBundle.classicalScreening
      }
      if (stageBundle.quantumRefinement.length) {
        screeningState.quantumRefinementResults = stageBundle.quantumRefinement
      }
      if (stageBundle.leaderboard.length) {
        screeningState.leaderboard = stageBundle.leaderboard
      }

      const firstRow = screeningState.leaderboard[0]
      if (firstRow && !screeningState.selectedMaterialName) {
        await selectMaterial(firstRow.candidateMaterial)
      }

      persistScreeningWorkflow()
      return bundle
    } catch (error) {
      screeningState.lastError = error.response?.data?.detail || error.message || '筛选结果加载失败'
      throw error
    } finally {
      screeningState.loadingBundle = false
    }
  }

  async function restoreLatestScreeningWorkflow() {
    const latest = readCurrentScreeningWorkflow()
    if (!latest.workflowId) return null

    return loadScreeningWorkflowById(latest.workflowId, latest.selectedCandidates)
  }

  async function loadScreeningWorkflowById(workflowId, selectedCandidates = []) {
    if (!workflowId) return null

    screeningState.screeningWorkflowId = workflowId
    if (Array.isArray(selectedCandidates) && selectedCandidates.length) {
      screeningState.selectedCandidates = selectedCandidates
    }
    return refreshScreeningWorkflow(workflowId)
  }

  async function selectMaterial(candidateMaterial) {
    const candidateResult = screeningState.candidateResults.find(item => item.candidateMaterial === candidateMaterial)
    const materialId = candidateResult?.materialProfile?.materialId

    screeningState.selectedMaterialName = candidateMaterial
    screeningState.selectedMaterialId = materialId || ''

    if (!screeningState.screeningWorkflowId || !materialId) {
      const row = screeningState.leaderboard.find(item => item.candidateMaterial === candidateMaterial)
      screeningState.selectedMaterialExplanation = row?.explanation || candidateResult?.explanation || null
      return screeningState.selectedMaterialExplanation
    }

    screeningState.loadingExplanation = true
    try {
      const payload = await fetchCandidateExplanation(screeningState.screeningWorkflowId, materialId)
      screeningState.selectedMaterialExplanation = payload.explanation
      return payload.explanation
    } catch (error) {
      const row = screeningState.leaderboard.find(item => item.candidateMaterial === candidateMaterial)
      screeningState.selectedMaterialExplanation = row?.explanation || candidateResult?.explanation || null
      screeningState.lastError = error.response?.data?.detail || error.message || '材料解释加载失败'
      return screeningState.selectedMaterialExplanation
    } finally {
      screeningState.loadingExplanation = false
    }
  }

  function applyScreeningWorkflowBundle(bundle) {
    screeningState.screeningWorkflowId = bundle.workflowId
    screeningState.workflowStatus = bundle.status
    screeningState.candidateCount = bundle.candidateCount
    screeningState.recommendedMaterial = bundle.recommendedMaterial
    screeningState.candidateResults = bundle.candidateResults
    screeningState.classicalScreeningResults = bundle.classicalScreening
    screeningState.quantumRefinementResults = bundle.quantumRefinement
    screeningState.leaderboard = bundle.leaderboard

    const firstRow = bundle.leaderboard[0]
    if (firstRow) {
      screeningState.selectedMaterialName = firstRow.candidateMaterial
      const firstCandidate = bundle.candidateResults.find(item => item.candidateMaterial === firstRow.candidateMaterial)
      screeningState.selectedMaterialId = firstCandidate?.materialProfile?.materialId || ''
      screeningState.selectedMaterialExplanation =
        bundle.explanations[screeningState.selectedMaterialId] || firstRow.explanation || firstCandidate?.explanation || null
    }
  }

  return {
    screeningState,
    selectedCandidateCount,
    canSubmitScreening,
    selectedMaterial,
    selectedLeaderboardRow,
    minSelectedCandidates: MIN_SELECTED_CANDIDATES,
    loadCandidates,
    toggleCandidate,
    createScreeningWorkflow,
    refreshScreeningWorkflow,
    restoreLatestScreeningWorkflow,
    loadScreeningWorkflowById,
    selectMaterial,
  }
}

function buildScreeningArchiveRecord() {
  return {
    workflowId: screeningState.screeningWorkflowId,
    caseId: screeningState.screeningWorkflowPayload?.caseId || 'li-s-demo',
    selectedCandidates: screeningState.selectedCandidates,
    candidateCount: screeningState.candidateCount || screeningState.selectedCandidates.length,
    recommendedMaterial: screeningState.recommendedMaterial,
    status: screeningState.workflowStatus,
    createdAt: screeningState.screeningWorkflowPayload?.createdAt || undefined,
    updatedAt: new Date().toISOString(),
  }
}
