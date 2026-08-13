<template>
  <section class="validation-panels" aria-label="三类验证状态">
    <article v-for="panel in panels" :key="panel.key" class="validation-panel" :class="panel.view.status">
      <header><span>{{ panel.kicker }}</span><strong>{{ panel.view.title }}</strong></header>
      <p>{{ panel.view.message }}</p>
      <template v-if="panel.key === 'optimizer' && optimizerValidation">
        <dl><div><dt>优化器</dt><dd>{{ value(optimizerValidation.optimizer) }}</dd></div><div><dt>success</dt><dd>{{ boolean(optimizerValidation.success) }}</dd></div><div><dt>termination_reason</dt><dd>{{ value(optimizerValidation.termination_reason) }}</dd></div><div><dt>目标函数评估次数</dt><dd>{{ value(optimizerValidation.nfev) }}</dd></div></dl>
      </template>
      <template v-else-if="panel.key === 'scientific' && scientificValidation">
        <dl><div><dt>VQE–FCI 科学误差</dt><dd>{{ energy(scientificValidation.vqe_fci_error_hartree) }}</dd></div><div><dt>化学精度阈值</dt><dd>{{ energy(scientificValidation.chemical_accuracy_threshold_hartree) }}</dd></div><div><dt>chemical_accuracy_reached</dt><dd>{{ boolean(scientificValidation.chemical_accuracy_reached) }}</dd></div><div><dt>HF reference reproduced</dt><dd>{{ energy(scientificValidation.hf_reference_error_hartree) }}</dd></div><div><dt>variational bound satisfied</dt><dd>{{ boolean(scientificValidation.variational_bound_satisfied) }}</dd></div><div><dt>粒子数期望值</dt><dd>{{ value(scientificValidation.particle_number_expectation) }} / {{ value(scientificValidation.target_electron_count) }}</dd></div><div><dt>粒子数方差</dt><dd>{{ value(scientificValidation.particle_number_variance) }}</dd></div><div><dt>minimum_consistency_status</dt><dd>{{ value(scientificValidation.minimum_consistency_status) }}</dd></div></dl>
        <ul v-if="scientificValidation.issues?.length"><li v-for="issue in scientificValidation.issues" :key="`${issue.code}-${issue.message}`"><b>{{ issue.code }}</b> · {{ issue.message }}</li></ul>
      </template>
      <template v-else-if="panel.key === 'deployment' && deploymentValidation">
        <dl><div><dt>分布式执行误差</dt><dd>{{ energy(deploymentValidation.distributed_execution_error_hartree) }}</dd></div><div><dt>actual_routed_plan_consumption</dt><dd>{{ deploymentValidation.actual_routed_plan_consumption === true ? '路由后计划已实际消费' : boolean(deploymentValidation.actual_routed_plan_consumption) }}</dd></div><div><dt>state_norm</dt><dd>{{ value(deploymentValidation.state_norm) }}</dd></div></dl>
      </template>
    </article>
  </section>
  <details class="version-panel"><summary>计算实现版本</summary><dl><div v-for="(label, key) in versionLabels" :key="key"><dt>{{ label }}</dt><dd>{{ versions?.[key] ?? 'legacy / 未记录' }}</dd></div></dl></details>
</template>

<script setup>
import { computed } from 'vue'
import { scientificValidationView } from '../services/scientificValidationService.js'

const props = defineProps({ optimizerValidation: Object, scientificValidation: Object, deploymentValidation: Object, versions: Object })
const panels = computed(() => [
  { key: 'optimizer', kicker: 'OPTIMIZER VALIDATION', view: scientificValidationView('optimizer', props.optimizerValidation) },
  { key: 'scientific', kicker: 'SCIENTIFIC VALIDATION', view: scientificValidationView('scientific', props.scientificValidation) },
  { key: 'deployment', kicker: 'DEPLOYMENT VALIDATION', view: scientificValidationView('deployment', props.deploymentValidation) },
])
const versionLabels = { ansatz_name: 'ansatz_name', ansatz_version: 'ansatz_version', simulator_version: 'simulator_version', hamiltonian_builder_version: 'hamiltonian_builder_version', scientific_validation_version: 'scientific_validation_version' }
function value(input) { return input === null || input === undefined || input === '' ? '—' : String(input) }
function energy(input) { return input === null || input === undefined || input === '' ? '—' : `${Number(input).toPrecision(8)} Ha` }
function boolean(input) { return input === true ? 'true' : input === false ? 'false' : '—' }
</script>

<style scoped>
.validation-panels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:#d3d9d2;border:1px solid #c9d0c8}.validation-panel{min-height:210px;padding:18px;background:#f7f8f5}.validation-panel.passed{background:#edf4e8}.validation-panel.needs_review{background:#fbf4df}.validation-panel.failed{background:#f9eae4}.validation-panel.legacy{background:#f1f3ef}.validation-panel header{display:grid;gap:8px}.validation-panel header span{color:#647d4e;font:700 .62rem ui-monospace,monospace;letter-spacing:.08em}.validation-panel header strong{font-size:1rem}.validation-panel p{min-height:36px;color:#59665e;font-size:.76rem;line-height:1.55}.validation-panel dl,.version-panel dl{display:grid;gap:7px;margin:12px 0 0}.validation-panel dl div,.version-panel dl div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px}.validation-panel dt,.version-panel dt{color:#748078;font-size:.67rem}.validation-panel dd,.version-panel dd{max-width:185px;margin:0;text-align:right;overflow-wrap:anywhere;font:600 .67rem ui-monospace,monospace}.validation-panel ul{margin:12px 0 0;padding-left:16px;color:#7a553e;font-size:.7rem;line-height:1.5}.version-panel{padding:14px 16px;border:1px solid #d3d9d2;background:#f7f8f5}.version-panel summary{cursor:pointer;color:#557b3b;font-size:.78rem;font-weight:700}.version-panel dl{grid-template-columns:repeat(2,minmax(0,1fr));column-gap:30px}@media(max-width:860px){.validation-panels{grid-template-columns:1fr}.version-panel dl{grid-template-columns:1fr}}</style>
