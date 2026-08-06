import {
  confirmActiveSpace,
  confirmElectronicStructureCandidate,
  confirmStructureActiveSite,
  createAdsorptionModels,
  createElectronicStructureCandidates,
  createFermionicHamiltonian,
  createGeometryOptimization,
  createQubitMapping,
  createQuantumRegion,
  createVqeCircuit,
  executeVqeCircuit,
  fetchStructure,
  fetchStructureTask,
  fetchStructureWorkflow,
  importDftResult,
  parseStructureFile,
  queueActiveSpaceCandidates,
  suggestStructureActiveSites,
  uploadStructureFile,
} from '../api/platformApi'

const TASK_POLL_INTERVAL_MS = 900
const TASK_POLL_LIMIT = 100

/** Upload and parse a user-owned molecular or crystal structure. */
export async function uploadAndParseStructure({ file, materialName, materialFamily, description }) {
  if (!file) throw new Error('请选择结构文件')
  if (!materialName?.trim()) throw new Error('请填写材料名称')

  const formData = new FormData()
  formData.append('file', file)
  formData.append('material_name', materialName.trim())
  if (materialFamily?.trim()) formData.append('material_family', materialFamily.trim())
  if (description?.trim()) formData.append('description', description.trim())

  const uploadResponse = await uploadStructureFile(formData)
  const parseResponse = await parseStructureFile(uploadResponse.data.file_id)
  const structureResponse = parseResponse.data.structure_id
    ? await fetchStructure(parseResponse.data.structure_id)
    : null

  return {
    file: uploadResponse.data,
    parseResult: parseResponse.data,
    structure: structureResponse?.data || null,
  }
}

/** Load active-site suggestions generated from a parsed structure. */
export async function loadActiveSiteSuggestions(structureId) {
  const { data } = await suggestStructureActiveSites(structureId)
  return data.suggestions || []
}

/** Persist the scientist's active-site decision. */
export async function saveActiveSiteConfirmation(structureId, payload) {
  const { data } = await confirmStructureActiveSite(structureId, payload)
  return data
}

/** Generate traceable Li2S4/Li2S6 initial conformations. */
export async function generateAdsorptionConformations(activeSiteId, payload) {
  const { data } = await createAdsorptionModels(activeSiteId, payload)
  return data
}

/** Create a geometry-only relaxation record. */
export async function runGeometryPreparation(adsorptionModelId) {
  const { data } = await createGeometryOptimization(adsorptionModelId, {
    calculation_mode: 'geometry_only',
  })
  return data
}

/** Import auditable DFT metadata and energy evidence for a selected conformation. */
export async function saveDftImport(adsorptionModelId, payload) {
  const { data } = await importDftResult(adsorptionModelId, payload)
  if (data.status !== 'dft_optimized' || !payload.optimized_structure_id) return data

  const geometryResponse = await createGeometryOptimization(adsorptionModelId, {
    calculation_mode: 'dft_optimized',
    imported_structure_id: payload.optimized_structure_id,
    method_name: [payload.calculation_metadata.software, payload.calculation_metadata.functional]
      .filter(Boolean)
      .join(' '),
    calculation_metadata: payload.calculation_metadata,
  })
  return { ...data, geometry_optimization: geometryResponse.data }
}

/** Build the local quantum region from a prepared geometry. */
export async function saveQuantumRegion(adsorptionModelId, payload) {
  const { data } = await createQuantumRegion(adsorptionModelId, payload)
  return data
}

/** Submit charge and spin candidates and wait for the bounded background task. */
export async function runElectronicStructureCandidates(quantumRegionId, payload) {
  const { data } = await createElectronicStructureCandidates(quantumRegionId, payload)
  return pollStructureTask(data.task_id)
}

/** Confirm an eligible charge and spin candidate. */
export async function saveElectronicCandidate(candidateId, confirmationNote = '') {
  const { data } = await confirmElectronicStructureCandidate(candidateId, {
    confirmation_note: confirmationNote || null,
  })
  return data
}

/** Generate active-space candidates and wait for the backend task result. */
export async function runActiveSpaceCandidates(quantumRegionId) {
  const { data } = await queueActiveSpaceCandidates(quantumRegionId)
  return pollStructureTask(data.task_id)
}

/** Confirm an eligible active space. */
export async function saveActiveSpaceConfirmation(quantumRegionId, activeSpaceId) {
  const { data } = await confirmActiveSpace(quantumRegionId, activeSpaceId)
  return data
}

/** Build, map, compile and execute the confirmed quantum problem. */
export async function runQuantumCalculation(activeSpaceId, options) {
  const fermionic = (await createFermionicHamiltonian(activeSpaceId)).data
  const qubit = (
    await createQubitMapping(fermionic.hamiltonian_id, {
      mapping_method: options.mappingMethod,
      enable_z2_tapering: options.enableZ2Tapering,
      pauli_coefficient_cutoff: options.pauliCoefficientCutoff,
    })
  ).data
  const circuit = (
    await createVqeCircuit(qubit.qubit_hamiltonian_id, {
      ansatz: 'hardware_efficient_ry_cx',
      ansatz_layers: options.ansatzLayers,
      optimizer: 'COBYLA',
      max_iterations: options.maxIterations,
      convergence_tolerance: options.convergenceTolerance,
      shots: options.shots,
      measurement_grouping: 'qubit_wise_commuting',
    })
  ).data
  const execution = (await executeVqeCircuit(circuit.vqe_circuit_id)).data
  return { fermionic, qubit, circuit, execution }
}

/** Fetch the current evidence-chain status for a structure workflow. */
export async function loadStructureWorkflow(workflowId) {
  const { data } = await fetchStructureWorkflow(workflowId)
  return data
}

async function pollStructureTask(taskId) {
  for (let attempt = 0; attempt < TASK_POLL_LIMIT; attempt += 1) {
    const { data } = await fetchStructureTask(taskId)
    if (data.status === 'completed') return data.result
    if (data.status === 'failed') throw new Error(data.message || '后台科研计算失败')
    await wait(TASK_POLL_INTERVAL_MS)
  }
  throw new Error('科研计算等待超时，请稍后重新查询任务')
}

function wait(durationMs) {
  return new Promise(resolve => window.setTimeout(resolve, durationMs))
}
