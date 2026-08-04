const EXPECTED_ELEMENT_COUNTS = { C: 66, Fe: 1, N: 4, Li: 2, S: 4 }

/** Return whether the server-validated literature candidate can create a workflow. */
export function isResearchBenchmarkCandidateSelectable(candidate) {
  return candidate?.source_metadata?.composition_validation === 'passed'
}

/** Render server-provided composition metadata without deriving chemistry in the client. */
export function formatResearchBenchmarkComposition(candidate) {
  const metadata = candidate?.source_metadata || {}
  const counts = metadata.element_counts
  if (!counts) return '组成校验数据未返回'
  const formula = Object.entries(EXPECTED_ELEMENT_COUNTS)
    .map(([element]) => `${element}${counts[element] ?? 0}`)
    .join(' ')
  return metadata.composition_validation === 'passed' ? `${formula} · 通过` : `${formula} · 异常`
}

/** Preserve the dataset-native energy value and its unresolved unit semantics. */
export function formatResearchBenchmarkSourceEnergy(candidate) {
  const energy = candidate?.source_energy
  if (energy === null || energy === undefined) return '未返回'
  return `${energy} ${candidate.source_energy_unit || ''}`.trim()
}

/** Limit displayed DFT facts to fields actually returned by the backend. */
export function buildResearchBenchmarkDftMetadataLines(metadata) {
  if (!metadata || typeof metadata !== 'object') return []
  const fields = [
    ['软件', metadata.software],
    ['泛函', metadata.xc_functional],
    ['截断能', metadata.plane_wave_cutoff],
    ['k 点', Array.isArray(metadata.k_points) ? metadata.k_points.join(' × ') : null],
    ['色散', metadata.dispersion?.sedc_scheme],
    ['真空层', metadata.vacuum_layer_z_angstrom ? `约 ${metadata.vacuum_layer_z_angstrom} Å` : null],
    ['自旋极化', metadata.spin_polarized],
  ]
  return fields
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([label, value]) => ({ label, value: String(value) }))
}

/** Map fixed server failure statuses to the research-operation copy required by the UI. */
export function mapResearchBenchmarkImportError(status, fallbackMessage) {
  if (status === 409) return '该基准已导入，请返回基准列表查看。'
  if (status === 403) return '仅研究基准管理员可导入。'
  return fallbackMessage
}
