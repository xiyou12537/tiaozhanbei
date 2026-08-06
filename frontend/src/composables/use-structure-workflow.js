import { computed, reactive } from 'vue'
import {
  generateAdsorptionConformations,
  loadActiveSiteSuggestions,
  loadStructureWorkflow,
  runActiveSpaceCandidates,
  runElectronicStructureCandidates,
  runGeometryPreparation,
  runQuantumCalculation,
  saveActiveSiteConfirmation,
  saveActiveSpaceConfirmation,
  saveDftImport,
  saveElectronicCandidate,
  saveQuantumRegion,
  uploadAndParseStructure,
} from '../services/structure-modeling-service'

const STORAGE_KEY = 'liangzhi-structure-modeling-workflow'

const structureState = reactive({
  workflowId: '',
  workflowStatus: 'idle',
  sourceFileRecord: null,
  parseResult: null,
  structure: null,
  optimizedFileRecord: null,
  optimizedParseResult: null,
  optimizedStructure: null,
  activeSiteSuggestions: [],
  confirmedActiveSite: null,
  adsorptionModels: [],
  selectedAdsorptionModelId: '',
  geometryOptimization: null,
  dftImport: null,
  quantumRegion: null,
  electronicCandidates: [],
  confirmedElectronicCandidate: null,
  activeSpaceCandidates: [],
  confirmedActiveSpace: null,
  quantumResult: null,
  busyAction: '',
  lastError: '',
})

restorePersistedState()

/** Coordinate the independent user-uploaded structure modeling workflow. */
export function useStructureWorkflow() {
  const isStructureValid = computed(() => {
    return Boolean(structureState.structure?.validation?.is_valid)
  })

  const selectedAdsorptionModel = computed(() => {
    return (
      structureState.adsorptionModels.find(
        item => item.adsorption_model_id === structureState.selectedAdsorptionModelId
      ) || null
    )
  })

  const effectiveGeometry = computed(() => {
    if (structureState.dftImport?.status === 'dft_optimized') {
      return {
        geometry_optimization_id: structureState.dftImport.geometry_optimization_id,
        source_type: 'imported_dft_result',
      }
    }
    return structureState.geometryOptimization
  })

  const canBuildQuantumRegion = computed(() => {
    return Boolean(selectedAdsorptionModel.value && effectiveGeometry.value?.geometry_optimization_id)
  })

  const canRunVqe = computed(() => {
    return structureState.confirmedActiveSpace?.status === 'confirmed'
  })

  const currentStep = computed(() => {
    if (structureState.quantumResult) return 6
    if (structureState.confirmedActiveSpace || structureState.activeSpaceCandidates.length) return 5
    if (structureState.quantumRegion) return 4
    if (structureState.geometryOptimization || structureState.dftImport) return 3
    if (structureState.adsorptionModels.length) return 2
    if (structureState.confirmedActiveSite) return 2
    if (structureState.structure) return 1
    return 0
  })

  async function uploadSourceStructure(payload) {
    return runAction('uploading_source', async () => {
      resetAfterSourceUpload()
      const result = await uploadAndParseStructure(payload)
      structureState.sourceFileRecord = result.file
      structureState.parseResult = result.parseResult
      structureState.structure = result.structure
      structureState.workflowId = result.parseResult.workflow_id || ''
      structureState.workflowStatus = result.structure?.validation?.is_valid
        ? 'active_site_pending'
        : 'validation_failed'
      persistState()
      return result
    })
  }

  async function uploadOptimizedStructure(payload) {
    return runAction('uploading_optimized', async () => {
      const result = await uploadAndParseStructure(payload)
      structureState.optimizedFileRecord = result.file
      structureState.optimizedParseResult = result.parseResult
      structureState.optimizedStructure = result.structure
      persistState()
      return result
    })
  }

  async function requestActiveSiteSuggestions() {
    return runAction('suggesting_sites', async () => {
      ensureValue(structureState.structure?.structure_id, '请先上传并解析有效结构')
      structureState.activeSiteSuggestions = await loadActiveSiteSuggestions(
        structureState.structure.structure_id
      )
      persistState()
      return structureState.activeSiteSuggestions
    })
  }

  async function confirmActiveSite(payload) {
    return runAction('confirming_site', async () => {
      const confirmedSite = await saveActiveSiteConfirmation(
        structureState.structure.structure_id,
        payload
      )
      structureState.confirmedActiveSite = {
        ...confirmedSite,
        confirmation_at: new Date().toISOString(),
      }
      structureState.workflowStatus = 'active_site_confirmed'
      persistState()
      return structureState.confirmedActiveSite
    })
  }

  async function createAdsorptionConformations(payload) {
    return runAction('generating_adsorption', async () => {
      ensureValue(structureState.confirmedActiveSite?.active_site_id, '请先确认活性位点')
      const result = await generateAdsorptionConformations(
        structureState.confirmedActiveSite.active_site_id,
        payload
      )
      structureState.adsorptionModels = result.models || []
      structureState.selectedAdsorptionModelId = result.models?.[0]?.adsorption_model_id || ''
      structureState.workflowStatus = result.status === 'generated' ? 'adsorption_models_generated' : 'partial_result'
      persistState()
      return result
    })
  }

  function selectAdsorptionModel(modelId) {
    structureState.selectedAdsorptionModelId = modelId
    persistState()
  }

  async function prepareGeometry() {
    return runAction('preparing_geometry', async () => {
      ensureValue(structureState.selectedAdsorptionModelId, '请选择一个吸附初始构型')
      structureState.geometryOptimization = await runGeometryPreparation(
        structureState.selectedAdsorptionModelId
      )
      structureState.workflowStatus = 'geometry_optimized'
      persistState()
      return structureState.geometryOptimization
    })
  }

  async function importDftEvidence(payload) {
    return runAction('importing_dft', async () => {
      ensureValue(structureState.selectedAdsorptionModelId, '请选择一个吸附初始构型')
      structureState.dftImport = await saveDftImport(
        structureState.selectedAdsorptionModelId,
        payload
      )
      if (structureState.dftImport.geometry_optimization) {
        structureState.geometryOptimization = structureState.dftImport.geometry_optimization
      }
      structureState.workflowStatus =
        structureState.dftImport.status === 'dft_optimized' ? 'geometry_optimized' : 'needs_model_review'
      persistState()
      return structureState.dftImport
    })
  }

  async function buildQuantumRegion(payload) {
    return runAction('building_region', async () => {
      if (!canBuildQuantumRegion.value) throw new Error('当前构型还没有可用的几何结果')
      structureState.quantumRegion = await saveQuantumRegion(
        structureState.selectedAdsorptionModelId,
        {
          geometry_optimization_id: effectiveGeometry.value.geometry_optimization_id,
          radius_angstrom: payload.radiusAngstrom,
          total_charge: payload.totalCharge,
          spin_multiplicity: payload.spinMultiplicity,
        }
      )
      structureState.workflowStatus = structureState.quantumRegion.status
      persistState()
      return structureState.quantumRegion
    })
  }

  async function calculateElectronicCandidates(payload) {
    return runAction('calculating_electronic', async () => {
      ensureValue(structureState.quantumRegion?.quantum_region_id, '请先建立量子区')
      const result = await runElectronicStructureCandidates(
        structureState.quantumRegion.quantum_region_id,
        payload
      )
      structureState.electronicCandidates = result?.candidates || []
      structureState.workflowStatus = result?.status || 'needs_model_review'
      persistState()
      return result
    })
  }

  async function confirmElectronicCandidate(candidateId, note) {
    return runAction('confirming_electronic', async () => {
      structureState.confirmedElectronicCandidate = await saveElectronicCandidate(candidateId, note)
      structureState.workflowStatus = 'electronic_structure_confirmed'
      persistState()
      return structureState.confirmedElectronicCandidate
    })
  }

  async function calculateActiveSpaces() {
    return runAction('calculating_active_spaces', async () => {
      ensureValue(structureState.confirmedElectronicCandidate?.candidate_id, '请先确认电荷和自旋候选')
      const result = await runActiveSpaceCandidates(structureState.quantumRegion.quantum_region_id)
      structureState.activeSpaceCandidates = result?.candidates || []
      structureState.workflowStatus = result?.status || 'active_space_pending'
      persistState()
      return result
    })
  }

  async function confirmActiveSpaceCandidate(activeSpaceId) {
    return runAction('confirming_active_space', async () => {
      structureState.confirmedActiveSpace = await saveActiveSpaceConfirmation(
        structureState.quantumRegion.quantum_region_id,
        activeSpaceId
      )
      structureState.workflowStatus = 'active_space_confirmed'
      persistState()
      return structureState.confirmedActiveSpace
    })
  }

  async function executeQuantumCalculation(options) {
    return runAction('running_vqe', async () => {
      if (!canRunVqe.value) throw new Error('请先确认可用的活性空间')
      structureState.quantumResult = await runQuantumCalculation(
        structureState.confirmedActiveSpace.active_space_id,
        options
      )
      structureState.workflowStatus = structureState.quantumResult.execution?.status || 'completed'
      persistState()
      return structureState.quantumResult
    })
  }

  async function refreshWorkflow() {
    if (!structureState.workflowId) return null
    return runAction('refreshing_workflow', async () => {
      const workflow = await loadStructureWorkflow(structureState.workflowId)
      structureState.workflowStatus = workflow.status
      persistState()
      return workflow
    })
  }

  /** Synchronize a server-backed workflow opened from a detail route with the shared header state. */
  function syncWorkflowFromDetail(workflow) {
    if (!workflow?.workflow_id) return
    structureState.workflowId = workflow.workflow_id
    structureState.workflowStatus = workflow.status || 'idle'
    persistState()
  }

  function resetWorkflow() {
    Object.assign(structureState, createEmptyState())
    window.localStorage.removeItem(STORAGE_KEY)
  }

  return {
    structureState,
    isStructureValid,
    selectedAdsorptionModel,
    effectiveGeometry,
    canBuildQuantumRegion,
    canRunVqe,
    currentStep,
    uploadSourceStructure,
    uploadOptimizedStructure,
    requestActiveSiteSuggestions,
    confirmActiveSite,
    createAdsorptionConformations,
    selectAdsorptionModel,
    prepareGeometry,
    importDftEvidence,
    buildQuantumRegion,
    calculateElectronicCandidates,
    confirmElectronicCandidate,
    calculateActiveSpaces,
    confirmActiveSpaceCandidate,
    executeQuantumCalculation,
    refreshWorkflow,
    syncWorkflowFromDetail,
    resetWorkflow,
  }
}

async function runAction(actionName, action) {
  structureState.busyAction = actionName
  structureState.lastError = ''
  try {
    return await action()
  } catch (error) {
    structureState.lastError = getErrorMessage(error)
    throw error
  } finally {
    structureState.busyAction = ''
  }
}

function getErrorMessage(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return error.message || '科研建模请求失败'
}

function persistState() {
  const persisted = {
    ...structureState,
    structure: structureState.structure
      ? { ...structureState.structure, atomic_sites: undefined }
      : null,
    optimizedStructure: structureState.optimizedStructure
      ? { ...structureState.optimizedStructure, atomic_sites: undefined }
      : null,
    busyAction: '',
    lastError: '',
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted))
}

function restorePersistedState() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
    if (saved && typeof saved === 'object') Object.assign(structureState, saved)
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
  }
}

function resetAfterSourceUpload() {
  const empty = createEmptyState()
  Object.assign(structureState, empty)
}

function createEmptyState() {
  return {
    workflowId: '',
    workflowStatus: 'idle',
    sourceFileRecord: null,
    parseResult: null,
    structure: null,
    optimizedFileRecord: null,
    optimizedParseResult: null,
    optimizedStructure: null,
    activeSiteSuggestions: [],
    confirmedActiveSite: null,
    adsorptionModels: [],
    selectedAdsorptionModelId: '',
    geometryOptimization: null,
    dftImport: null,
    quantumRegion: null,
    electronicCandidates: [],
    confirmedElectronicCandidate: null,
    activeSpaceCandidates: [],
    confirmedActiveSpace: null,
    quantumResult: null,
    busyAction: '',
    lastError: '',
  }
}

function ensureValue(value, message) {
  if (!value) throw new Error(message)
}
