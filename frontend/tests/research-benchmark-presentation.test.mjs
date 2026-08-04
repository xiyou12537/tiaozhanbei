import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildResearchBenchmarkDftMetadataLines,
  formatResearchBenchmarkComposition,
  formatResearchBenchmarkSourceEnergy,
  isResearchBenchmarkCandidateSelectable,
  mapResearchBenchmarkImportError,
} from '../src/services/research-benchmark-presentation.js'

test('only server-validated FeN4C66 + Li2S4 candidates can be selected', () => {
  const candidate = { source_metadata: { composition_validation: 'passed', element_counts: { C: 66, Fe: 1, N: 4, Li: 2, S: 4 } } }
  assert.equal(isResearchBenchmarkCandidateSelectable(candidate), true)
  assert.equal(formatResearchBenchmarkComposition(candidate), 'C66 Fe1 N4 Li2 S4 · 通过')
  assert.equal(isResearchBenchmarkCandidateSelectable({ source_metadata: { composition_validation: 'failed' } }), false)
})

test('source energy remains dataset-native and unresolved', () => {
  assert.equal(
    formatResearchBenchmarkSourceEnergy({ source_energy: -123.456, source_energy_unit: 'dataset_native_unit_not_confirmed' }),
    '-123.456 dataset_native_unit_not_confirmed'
  )
})

test('DFT metadata displays only backend facts', () => {
  const lines = buildResearchBenchmarkDftMetadataLines({ software: 'CASTEP', k_points: [3, 3, 1], dispersion: { sedc_scheme: 'g06' } })
  assert.deepEqual(lines, [
    { label: '软件', value: 'CASTEP' },
    { label: 'k 点', value: '3 × 3 × 1' },
    { label: '色散', value: 'g06' },
  ])
})

test('admin import failures use the required fixed copy', () => {
  assert.equal(mapResearchBenchmarkImportError(409, 'ignored'), '该基准已导入，请返回基准列表查看。')
  assert.equal(mapResearchBenchmarkImportError(403, 'ignored'), '仅研究基准管理员可导入。')
})
