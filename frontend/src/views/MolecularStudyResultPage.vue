<template>
  <div class="study-result-page">
    <section v-if="loading && !study" class="loading-state" v-loading="true">正在恢复 Study…</section>
    <el-alert v-if="loadError" type="error" :closable="false" show-icon>
      <template #title>{{ loadError.title }}</template><p>{{ loadError.message }}</p>
      <p class="mono">Study ID：{{ loadError.studyId || route.params.studyId }}<span v-if="loadError.molecularProblemId"> · Molecular Problem ID：{{ loadError.molecularProblemId }}</span></p>
      <p v-if="loadError.code" class="mono">{{ loadError.code }} · {{ loadError.stage || '—' }}<span v-if="loadError.architectureId"> · {{ loadError.architectureId }}</span></p>
      <div class="error-actions"><el-button v-if="loadError.status === 401" @click="goToLogin">重新登录</el-button><el-button v-if="loadError.retryable" size="small" @click="loadStudy">重试查询</el-button></div>
    </el-alert>

    <template v-if="study">
      <header class="result-head"><div><span>MOLECULAR STUDY / DEPLOYMENT REPORT</span><h2>{{ molecularProblem.molecule?.molecule_name || '部署评估 Study' }}</h2><p class="mono">{{ study.study_id }} · {{ molecularProblemId || '—' }}</p><p class="simulation-note">逻辑虚拟 QPU 模拟 · is_real_qpu=false · 非真实 QPU</p></div><div class="contract-tags"><el-tag>logical_virtual_qpu</el-tag><el-tag>is_real_qpu=false</el-tag><el-tag type="warning">非真实 QPU</el-tag><el-button data-testid="copilot-explain-result" text @click="askCopilotAboutResult">让 Copilot 解释这个结果</el-button><el-button @click="goToCreate">新建部署评估</el-button></div></header>

      <BeginnerResultSummary kind="study" :summary="beginnerSummary" compact />

      <section class="study-overview"><div><span>STUDY STATUS</span><h3>{{ studyStatusLabel }}</h3><p>公共分子问题状态：<b>{{ molecularProblem.status || '—' }}</b>。已完成架构独立展示，不会重复计算 PySCF 或 VQE。</p></div><div class="overview-metrics"><article><span>已完成 / 总架构</span><strong>{{ value(study.completed_evaluation_count) }} / {{ value(study.total_evaluation_count) }}</strong></article><article><span>已验证可部署候选</span><strong data-testid="verified-deployment-candidate-count">{{ deploymentEvidence.verifiedCandidateCount }}</strong></article><article><span>部署验证待复核</span><strong>{{ deploymentEvidence.reviewCount }}</strong></article><article><span>评估运行失败</span><strong>{{ deploymentEvidence.failedCount }}</strong></article></div></section>
      <section class="study-decision" aria-label="方案比较结论">
        <article><span>整体比较</span><strong>{{ studyDecision.overall }}</strong><p>{{ studyDecision.candidate }}</p></article>
        <article><span>候选依据</span><strong>{{ studyDecision.reason }}</strong><p>{{ studyDecision.confidence }}</p></article>
        <article><span>推荐下一步</span><strong>{{ studyDecision.next }}</strong><p>不把通信量、SWAP 或任何单项指标单独当作全面最优依据。</p></article>
      </section>

      <details class="study-evidence">
        <summary>查看专业比较证据（科学、优化器、部署、通信与路由）</summary>
        <div class="study-evidence-body">
      <ScientificValidationPanels :optimizer-validation="molecularProblem.optimizer_validation" :scientific-validation="molecularProblem.scientific_validation" :versions="versions" />

      <section class="panel phase-panel"><header class="section-head"><div><span>01 / SHARED MOLECULAR PROBLEM</span><h3>公共分子问题进度</h3></div><small>只执行一次</small></header><div class="shared-phases"><article v-for="(phase,index) in sharedPhases" :key="phase"><b>{{ String(index + 1).padStart(2, '0') }}</b><strong>{{ phase }}</strong></article></div><div v-if="molecularProblem.stages?.length" class="actual-phase-list"><span v-for="stage in molecularProblem.stages" :key="stage.stage">{{ stage.stage }} · {{ stage.status || '—' }}</span></div></section>

      <section class="panel science-panel"><header class="section-head"><div><span>02 / SCIENTIFIC RESULT</span><h3>分子、VQE 与科学参考</h3></div></header><div class="science-grid"><article><span>HF 能量</span><strong>{{ energy(molecularProblem.hf_energy_hartree) }}</strong><small>Ha</small></article><article><span>未分区 VQE 能量</span><strong>{{ energy(molecularProblem.vqe?.unpartitioned_energy_hartree) }}</strong><small>Ha</small></article><article><span>FCI 参考</span><strong>{{ fciLabel }}</strong><small>{{ molecularProblem.fci_reference?.status === 'not_configured' ? '未配置 FCI 参考' : energy(molecularProblem.fci_reference?.energy_hartree) }}</small></article><article><span>VQE - FCI 科学误差</span><strong>{{ energy(molecularProblem.vqe_fci_scientific_error_hartree) }}</strong><small>{{ molecularProblem.fci_reference?.status === 'not_configured' ? '未配置 FCI 参考' : 'Ha' }}</small></article></div><div class="science-details"><span>活性空间：{{ value(molecularProblem.active_space?.active_electrons) }} electrons / {{ value(molecularProblem.active_space?.active_orbitals) }} orbitals</span><span>量子比特：{{ value(molecularProblem.hamiltonian?.qubit_count) }}</span><span>Pauli 项：{{ value(molecularProblem.hamiltonian?.pauli_term_count) }}</span><span>优化器：{{ value(molecularProblem.vqe?.optimizer) }}</span></div></section>

      <section class="panel report-panel"><header class="section-head"><div><span>03 / DEPLOYMENT REPORT</span><h3>架构比较</h3></div><small>原始指标；不生成前端综合评分</small></header><div class="report-table-wrap"><table><thead><tr><th>架构</th><th>评估状态</th><th>可部署状态 / 原因</th><th>分区规模</th><th>SWAP</th><th>跨 QPU 通信</th><th>原始 / 路由后操作</th><th>原生双比特门等价</th><th>分布式执行误差</th><th>路由后计划</th></tr></thead><tbody><tr v-for="evaluation in evaluations" :key="evaluation.evaluation_id || evaluation.architecture_id"><td><strong>{{ evaluation.architecture_name || evaluation.architecture_id }}</strong><small class="mono">{{ evaluation.architecture_id }}</small></td><td>{{ evaluation.status || '—' }}</td><td><el-tag :type="deploymentTag(evaluation).type">{{ deploymentTag(evaluation).label }}</el-tag><small v-if="evaluation.failure_reason" class="reason">{{ evaluation.failure_reason.code }}：{{ evaluation.failure_reason.message }}</small></td><td>{{ value(evaluation.partition_summary?.partition_count) }}<small>{{ list(evaluation.partition_summary?.partition_sizes) }}</small></td><td>{{ value(evaluation.metrics?.abstract_swap_count) }}</td><td>{{ value(evaluation.metrics?.cross_partition_communication_count) }}</td><td>{{ value(evaluation.metrics?.original_operation_count) }} / {{ value(evaluation.metrics?.routed_operation_count) }}</td><td>{{ value(evaluation.metrics?.native_two_qubit_gate_equivalent_count) }}</td><td>{{ energy(evaluation.energy_validation?.distributed_execution_error_hartree) }}</td><td>{{ booleanLabel(evaluation.distribution?.actual_routed_plan_consumption, '路由后计划已实际消费', '—') }}</td></tr><tr v-if="!evaluations.length"><td colspan="10" class="empty">等待后端返回架构评估 partial result。</td></tr></tbody></table></div></section>

      <section class="panel evaluation-progress"><header class="section-head"><div><span>04 / PER-ARCHITECTURE PROGRESS</span><h3>架构独立评估进度</h3></div><small>每个架构单独评估</small></header><div class="evaluation-cards"><article v-for="evaluation in evaluations" :key="`progress-${evaluation.evaluation_id || evaluation.architecture_id}`"><header><strong>{{ evaluation.architecture_name || evaluation.architecture_id }}</strong><el-tag :type="evaluation.status === 'failed' ? 'danger' : evaluation.status === 'completed' ? 'success' : 'warning'">{{ evaluation.status || 'queued' }}</el-tag></header><ol><li v-for="phase in evaluationPhases" :key="phase">{{ phase }}</li></ol><p>{{ evaluation.is_deployable === false ? '不可部署结果已完成，保留失败原因。' : evaluation.status === 'failed' ? '评估运行失败，其他架构不受影响。' : '状态以后端 evaluation.status 为准。' }}</p></article></div></section>

      <section v-for="evaluation in evaluations" :key="`detail-${evaluation.evaluation_id || evaluation.architecture_id}`" class="panel evaluation-detail"><header class="section-head"><div><span>ARCHITECTURE DETAIL</span><h3>{{ evaluation.architecture_name || evaluation.architecture_id }}</h3></div><el-tag :type="deploymentTag(evaluation).type">{{ deploymentTag(evaluation).label }}</el-tag></header><ScientificValidationPanels :deployment-validation="evaluation.deployment_validation" :versions="{}" /><ParticleConservingCircuitLegend :ansatz="molecularProblem.vqe?.ansatz" :qasm="molecularProblem.vqe?.qasm" :routed-plan="evaluation.distribution?.routed_execution_plan" /><div class="detail-grid"><article><h4>分区方案</h4><p>{{ json(evaluation.partition_summary?.partitions) }}</p></article><article><h4>虚拟节点映射</h4><p>{{ json(evaluation.distribution?.virtual_node_mapping) }}</p></article><article><h4>分区间拓扑</h4><p>{{ edgeList(evaluation.architecture?.inter_qpu_topology || evaluation.distribution?.inter_qpu_topology) }}</p></article><article><h4>芯片内部物理耦合图</h4><p>{{ chipCouplings(evaluation.architecture?.virtual_qpus) }}</p></article><article><h4>初始 logical-to-physical 布局</h4><p>{{ json(evaluation.distribution?.partition_chip_routing?.map(item => item.logical_to_physical_initial)) }}</p></article><article><h4>最终 logical-to-physical 布局</h4><p>{{ json(evaluation.distribution?.final_logical_to_physical_layout) }}</p></article><article><h4>SWAP 路径</h4><p>{{ json(evaluation.distribution?.two_qubit_routing_evidence?.map(item => item.swap_path)) }}</p></article><article><h4>双比特门路由证据</h4><p>{{ json(evaluation.distribution?.two_qubit_routing_evidence) }}</p></article><article><h4>routed_execution_plan</h4><p>{{ json(evaluation.distribution?.routed_execution_plan) }}</p></article><article><h4>communication_events</h4><p>{{ json(evaluation.distribution?.communication_events) }}</p></article><article><h4>state_norm</h4><p>{{ value(evaluation.distribution?.state_norm) }}</p></article><article><h4>实际消费</h4><p>actual_partition_consumption={{ value(evaluation.distribution?.actual_partition_consumption) }}<br>actual_routed_plan_consumption={{ value(evaluation.distribution?.actual_routed_plan_consumption) }}</p></article></div><div class="energy-row"><article><span>未分区 VQE 能量</span><strong>{{ energy(evaluation.energy_validation?.unpartitioned_vqe_energy_hartree) }}</strong></article><article><span>分布式 VQE 能量</span><strong>{{ energy(evaluation.energy_validation?.distributed_simulation_energy_hartree) }}</strong></article><article><span>Distributed VQE - VQE 执行误差</span><strong>{{ energy(evaluation.energy_validation?.distributed_execution_error_hartree) }}</strong></article></div></section>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMolecularStudy, isMolecularStudyTerminalStatus, mergeMolecularStudy, normalizeMolecularStudyError, resolveMolecularProblemId } from '../services/molecularStudyService.js'
import { saveRecentMolecularStudy } from '../services/molecularStudyStorage.js'
import { clearAuthSession } from '../services/authStorage.js'
import ScientificValidationPanels from '../components/ScientificValidationPanels.vue'
import ParticleConservingCircuitLegend from '../components/ParticleConservingCircuitLegend.vue'
import BeginnerResultSummary from '../components/BeginnerResultSummary.vue'
import { implementationVersions } from '../services/scientificValidationService.js'
import { summarizeStudyForBeginners } from '../services/beginnerExperienceService.js'
import { summarizeStudyDecision, summarizeStudyDeploymentEvidence, studyDeploymentEvidence } from '../services/productExperienceService.js'
import { readUser } from '../services/authStorage.js'
import { createCopilotResultDraft, savePendingCopilotDraft } from '../services/assistantCopilotContext.js'

const route = useRoute()
const router = useRouter()
const study = ref(null)
const loading = ref(false)
const loadError = ref(null)
let pollTimer = null
const POLL_INTERVAL_MS = 2500
const sharedPhases = ['PySCF', '活性空间', 'Hamiltonian', 'Qubit 映射', 'VQE / QASM']
const evaluationPhases = ['线路分区', '虚拟节点映射', '芯片路由', 'routed plan 模拟', '能量验证']
const molecularProblem = computed(() => study.value?.result?.molecular_problem || {})
const versions = computed(() => implementationVersions(molecularProblem.value || {}))
const evaluations = computed(() => study.value?.result?.deployment_evaluations || [])
const deploymentEvidence = computed(() => summarizeStudyDeploymentEvidence(study.value || {}))
const beginnerSummary = computed(() => summarizeStudyForBeginners(study.value || {}))
const studyDecision = computed(() => summarizeStudyDecision(study.value || {}))
const molecularProblemId = computed(() => resolveMolecularProblemId(study.value) || molecularProblem.value.molecular_problem_id || null)
const loginUrl = computed(() => `/auth?tab=login&redirect=${encodeURIComponent(route.fullPath)}`)
const studyStatusLabel = computed(() => ({ queued: '排队中', running: '评估中', partial: '部分完成', completed: '评估完成', failed: 'Study 未完成', needs_review: '需要复核' })[study.value?.status] || '状态待确认')
const fciLabel = computed(() => molecularProblem.value.fci_reference?.status === 'not_configured' ? '未配置 FCI 参考' : energy(molecularProblem.value.fci_reference?.energy_hartree))

function clearPolling() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null } }
function schedulePolling() { clearPolling(); if (study.value && !isMolecularStudyTerminalStatus(study.value.status)) pollTimer = setTimeout(loadStudy, POLL_INTERVAL_MS) }
async function loadStudy() {
  clearPolling(); loading.value = true; loadError.value = null
  try {
    const response = await getMolecularStudy(route.params.studyId)
    study.value = mergeMolecularStudy(study.value, response)
    saveRecentMolecularStudy(study.value)
    schedulePolling()
  } catch (error) {
    loadError.value = normalizeMolecularStudyError(error)
    if (loadError.value.status === 401) clearAuthSession()
  } finally { loading.value = false }
}

function value(input) { return input === null || input === undefined || input === '' ? '—' : String(input) }
function energy(input) { return input === null || input === undefined || input === '' ? '—' : `${Number(input).toFixed(10)} Ha` }
function list(items) { return Array.isArray(items) && items.length ? items.join(' / ') : '—' }
function json(input) { return input === null || input === undefined ? '—' : JSON.stringify(input, null, 2) }
function edgeList(edges) { return Array.isArray(edges) && edges.length ? edges.map(edge => `${edge.source} — ${edge.target}`).join(' · ') : '—' }
function chipCouplings(chips) { return Array.isArray(chips) && chips.length ? chips.map(chip => `${chip.virtual_qpu_id}：${edgeList(chip.physical_coupling_map)}`).join('\n') : '—' }
function booleanLabel(input, truthy, falsy) { return input === true ? truthy : input === false ? '未消费' : falsy }
function deploymentTag(evaluation) { return studyDeploymentEvidence(evaluation) }
function goToCreate() { router.push('/app/molecular-studies/new') }
function askCopilotAboutResult() { const draft = createCopilotResultDraft('molecular_study', study.value?.study_id); if (draft && savePendingCopilotDraft(readUser(), draft)) router.push('/app/copilot') }
function goToLogin() { router.push(loginUrl.value) }

watch(() => route.params.studyId, loadStudy)
onMounted(loadStudy)
onBeforeUnmount(clearPolling)
</script>

<style scoped>
.study-result-page{display:grid;gap:22px}.loading-state{min-height:360px;padding:35px;border:1px solid #c9cec7;background:#fff}.result-head{min-height:190px;padding:34px;border:1px solid #c7cdc5;display:flex;align-items:flex-end;justify-content:space-between;gap:24px;background:#e7eae3}.result-head>div:first-child{min-width:0}.result-head span,.section-head span{color:#6e7b72;font:700 .66rem ui-monospace,monospace;letter-spacing:.12em}.result-head h2{margin:13px 0 8px;font-size:clamp(2.2rem,5vw,4.6rem);line-height:.9;letter-spacing:-.065em}.result-head p{margin:0;color:#69756d;font-size:.7rem;overflow-wrap:anywhere}.contract-tags{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px}.study-overview{padding:28px 32px;border:1px solid #9db885;background:#eaf0e4;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:26px}.study-overview span{color:#678047;font:700 .65rem ui-monospace,monospace;letter-spacing:.12em}.study-overview h3{margin:8px 0;font-size:1.7rem}.study-overview p{margin:0;color:#56635b;font-size:.8rem;line-height:1.6}.overview-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:#c8d4c1}.overview-metrics article{min-height:74px;padding:13px;background:#f5f8f2;display:grid;align-content:space-between}.overview-metrics span{color:#748078;font-size:.66rem;letter-spacing:0}.overview-metrics strong{font:700 .93rem ui-monospace,monospace}.panel{padding:30px;border:1px solid #c9cec7;background:#fff}.section-head{margin-bottom:23px;display:flex;align-items:end;justify-content:space-between;gap:20px}.section-head h3{margin:8px 0 0;font-size:1.5rem;letter-spacing:-.03em}.section-head small{color:#718078;font-size:.72rem}.shared-phases{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid #d8ddd6}.shared-phases article{min-height:80px;padding:15px;border-right:1px solid #e0e4df;display:grid;gap:10px;align-content:center}.shared-phases article:last-child{border-right:0}.shared-phases b{color:#75a248;font:700 .66rem ui-monospace,monospace}.shared-phases strong{font-size:.78rem}.actual-phase-list{margin-top:16px;display:flex;flex-wrap:wrap;gap:8px}.actual-phase-list span{padding:7px 9px;border:1px solid #d8ddd6;background:#f5f6f3;font:600 .67rem ui-monospace,monospace}.science-grid,.energy-row{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#d5dad3}.science-grid article,.energy-row article{min-height:130px;padding:20px;background:#f4f6f2;display:grid;align-content:space-between}.science-grid span,.energy-row span{color:#748078;font-size:.68rem}.science-grid strong,.energy-row strong{font:700 .85rem ui-monospace,monospace;overflow-wrap:anywhere}.science-grid small{color:#718078;font-size:.7rem}.science-details{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px}.science-details span{padding:8px 10px;background:#f2f4f0;color:#607066;font:600 .68rem ui-monospace,monospace}.report-table-wrap{overflow:auto;border:1px solid #d5dad3}.report-table-wrap table{width:100%;min-width:1250px;border-collapse:collapse}.report-table-wrap th{padding:11px;background:#eff2ed;color:#6b776f;text-align:left;font-size:.67rem;font-weight:700;white-space:nowrap}.report-table-wrap td{padding:14px;border-top:1px solid #e1e5df;vertical-align:top;font-size:.73rem}.report-table-wrap td>strong,.report-table-wrap td>small{display:block}.report-table-wrap .reason{max-width:220px;margin-top:7px;color:#825b4b;line-height:1.4}.empty{text-align:center;color:#78837d}.evaluation-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:13px}.evaluation-cards article{min-height:220px;padding:20px;border:1px solid #d3d9d2;background:#f7f8f5}.evaluation-cards header{display:flex;justify-content:space-between;gap:10px}.evaluation-cards header strong{font:700 .8rem ui-monospace,monospace;overflow-wrap:anywhere}.evaluation-cards ol{margin:18px 0;padding-left:20px;color:#58665d;font-size:.73rem;line-height:1.8}.evaluation-cards p{margin:0;color:#748078;font-size:.72rem;line-height:1.55}.evaluation-detail{border-left:3px solid #6d9848}.detail-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#d7dcd5}.detail-grid article{min-height:142px;padding:17px;background:#f5f6f3}.detail-grid h4{margin:0 0 12px;color:#5e7c43;font-size:.73rem}.detail-grid p{max-height:126px;margin:0;overflow:auto;white-space:pre-wrap;color:#536259;font:600 .67rem/1.55 ui-monospace,monospace}.energy-row{margin-top:20px;grid-template-columns:repeat(3,1fr)}.mono{font-family:ui-monospace,monospace}.error-actions{display:flex;gap:8px}@media(max-width:1120px){.study-overview{grid-template-columns:1fr}.science-grid{grid-template-columns:repeat(2,1fr)}.detail-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:780px){.result-head,.section-head{align-items:flex-start;flex-direction:column}.contract-tags{justify-content:flex-start}.panel{padding:20px}.shared-phases,.evaluation-cards,.science-grid,.detail-grid,.energy-row{grid-template-columns:1fr}.shared-phases article{border-right:0;border-bottom:1px solid #e0e4df}.overview-metrics{grid-template-columns:1fr 1fr}.study-overview{padding:22px}.evaluation-cards{gap:10px}}
.study-result-page,.panel,.report-table-wrap{min-width:0}.report-table-wrap{max-width:100%;overflow-x:auto}
.study-decision{display:grid;grid-template-columns:1.1fr 1.15fr .9fr;gap:1px;border:1px solid var(--lz-line);background:var(--lz-line)}.study-decision article{min-height:145px;padding:20px;background:var(--lz-panel);display:grid;align-content:start;gap:9px}.study-decision span{color:var(--lz-muted);font-size:.68rem}.study-decision strong{font-size:.94rem;line-height:1.45;overflow-wrap:anywhere}.study-decision p{margin:0;color:var(--lz-muted);font-size:.75rem;line-height:1.55}.study-evidence{border:1px solid var(--lz-line);background:var(--lz-bg-soft)}.study-evidence>summary{padding:18px 20px;color:var(--lz-accent-deep);cursor:pointer;font-weight:700;font-size:.86rem}.study-evidence[open]>summary{border-bottom:1px solid var(--lz-line)}.study-evidence-body{padding:20px;display:grid;gap:18px}.study-evidence-body>.panel{margin:0}.simulation-note{margin-top:10px!important;color:#42662f!important;font:700 .68rem ui-monospace,monospace!important}.contract-tags :deep(.el-tag){border-color:#b7cbaa;background:#edf4e8;color:#385a2c;font-weight:700}.contract-tags :deep(.el-tag--warning){border-color:#e4c476;background:#fff5dc;color:#895d10}@media(max-width:1120px){.study-decision{grid-template-columns:1fr 1fr}.study-decision article:last-child{grid-column:1/-1}}@media(max-width:780px){.study-evidence-body{padding:20px}.study-decision{grid-template-columns:1fr}.study-decision article:last-child{grid-column:auto}}
</style>
