<template>
  <div class="scan-result">
    <section v-if="loading && !scan" class="loading" v-loading="true">正在恢复键长扫描…</section>
    <el-alert v-if="error" type="error" :title="error.title" :closable="false">
      <p>{{ error.message }}</p><p class="mono">Scan ID：{{ error.scanId || route.params.scanId }}</p>
      <el-button v-if="error.retryable" size="small" @click="load">重试查询</el-button>
    </el-alert>

    <template v-if="scan">
      <header class="head">
        <div><span>LIH / POTENTIAL ENERGY SCAN</span><h2>LiH 离散势能曲线</h2><p class="mono">{{ scan.scan_id }}</p><p class="simulation-note">逻辑虚拟 QPU 模拟 · is_real_qpu=false · 非真实 QPU</p></div>
        <div class="fixed-tags"><el-tag>logical_virtual_qpu</el-tag><el-tag>is_real_qpu=false</el-tag><el-tag type="warning">非真实 QPU</el-tag><el-button data-testid="copilot-explain-result" text @click="askCopilotAboutResult">让 Copilot 解释这个结果</el-button></div>
      </header>

      <BeginnerResultSummary kind="bond-scan" :summary="beginnerSummary" compact />

      <section class="overview">
        <article><span>Scan 状态</span><strong>{{ scan.status }}</strong><small>{{ scan.current_stage }}</small></article>
        <article><span>已完成 / 总点数</span><strong>{{ value(scan.completed_point_count) }} / {{ value(scan.total_point_count) }}</strong></article>
        <article><span>failed 点数</span><strong>{{ value(scan.failed_point_count) }}</strong></article>
        <article><span>needs_review 点数</span><strong>{{ value(scan.needs_review_point_count) }}</strong></article>
        <article><span>当前计算距离</span><strong>{{ currentDistance }}</strong></article>
      </section>

      <section class="scan-decision" aria-label="键长扫描结论">
        <article><span>扫描进度</span><strong>{{ scanDecision.progress }}</strong><p>{{ scanDecision.minimum }}；这是离散候选点，不是精确平衡键长。</p></article>
        <article><span>范围与科学参考</span><strong>{{ scanDecision.boundary }}</strong><p>{{ scanDecision.science }}</p></article>
        <article><span>部署结论与下一步</span><strong>{{ scanDecision.deployment }}</strong><p>{{ scanDecision.next }}</p></article>
      </section>

      <section class="panel curve-panel">
        <header><span>RUNNING PARTIAL RESULT</span><h3>势能曲线</h3><p>离散扫描连线，仅用于观察趋势。failed 点不连入曲线；未配置或不可用的 FCI 不会代替为 0。</p></header>
        <div class="legend"><el-checkbox v-model="visible.hf">HF</el-checkbox><el-checkbox v-model="visible.vqe">VQE</el-checkbox><el-checkbox v-model="visible.fci">FCI</el-checkbox></div>
        <svg class="curve" viewBox="0 0 900 360" role="img" aria-label="LiH 势能曲线">
          <line x1="72" y1="300" x2="860" y2="300"/><line x1="72" y1="35" x2="72" y2="300"/>
          <polyline v-for="item in chartLines" :key="item.name" :points="item.points" :class="item.name"/>
          <g v-for="item in chartDots" :key="item.name"><circle v-for="point in item.data" :key="`${item.name}-${point.pointIndex}`" :cx="point.x" :cy="point.y" :class="[item.name, { warning: point.needsReview }]" @click="selected = point.pointIndex"><title>{{ item.name }} · {{ point.distance }} Å · {{ energy(point.energy) }} · {{ point.converged === true ? 'VQE 已收敛' : point.converged === false ? 'VQE 未收敛' : 'VQE 状态 —' }}</title></circle></g>
          <text x="460" y="345">Li–H 距离 / Å</text><text transform="translate(18,185) rotate(-90)">能量 / Hartree</text>
        </svg>
        <section class="error-strip"><header><span>VQE–FCI SCIENTIFIC ERROR</span><strong>科学误差视图</strong></header><div v-if="scientificErrorSeries.length" class="error-points"><button v-for="item in scientificErrorSeries" :key="item.pointIndex" :class="{ review:item.needsReview }" @click="selected=item.pointIndex">{{ item.distance }} Å · {{ energy(item.error) }}</button></div><p v-else>—</p></section>
      </section>

      <section class="minima">
        <article v-for="minimum in minima" :key="minimum.label"><span>{{ minimum.label }}</span><strong>{{ value(minimum.distance) }} Å</strong><p>{{ energy(minimum.energy) }} · point {{ value(minimum.pointIndex) }}</p><small v-if="minimum.minimumAtBoundary">最低点位于扫描区间边界，当前范围可能未包围实际最低区域。</small></article>
      </section>
      <section class="deployment-reference-status" :class="deploymentReference.kind">
        <span>DEPLOYMENT BASIS</span><strong>{{ deploymentReference.title }}</strong><p>{{ deploymentReference.message }}</p>
      </section>
      <el-alert v-if="isTerminal && scan.result && !scan.result.scientific_vqe_discrete_minimum" type="warning" :closable="false" title="没有通过科学验证的 VQE 最低点"><p>不显示可信近似键长。</p><p v-if="scan.result.engineering_only_deployment === true">仅进行工程部署验证。</p></el-alert>

      <details class="scan-evidence">
        <summary>查看扫描点、科学验证、部署与路由证据</summary>
        <div class="scan-evidence-body">
      <section class="panel">
        <header><span>POINTS</span><h3>已获得扫描点</h3></header>
        <div class="table" role="table">
          <button v-for="point in points" :key="point.point_index" :class="{ selected: selected === point.point_index }" @click="selected = point.point_index">
            <b>#{{ point.point_index }}</b><span>{{ value(point.distance_angstrom) }} Å</span><span>{{ point.status }}</span><span>{{ point.validation_status || '—' }}</span><span>{{ energy(point.hf_energy_hartree) }}</span><span>{{ energy(point.vqe_energy_hartree) }}</span><span>{{ point.fci_reference?.status === 'available' ? energy(point.fci_reference.energy_hartree) : '—' }}</span>
          </button>
        </div>
      </section>

      <section v-if="selectedPoint" class="panel detail">
        <header><span>POINT DETAIL</span><h3>{{ selectedPoint.distance_angstrom }} Å</h3></header>
        <div class="metric-grid">
          <article><span>HF 能量</span><strong>{{ energy(selectedPoint.hf_energy_hartree) }}</strong></article>
          <article><span>未分区 VQE 能量</span><strong>{{ energy(selectedPoint.vqe_energy_hartree) }}</strong></article>
          <article><span>FCI 能量</span><strong>{{ fciLabel(selectedPoint) }}</strong></article>
          <article><span>VQE–FCI scientific error</span><strong>{{ energy(selectedPoint.vqe_fci_scientific_error_hartree) }}</strong></article>
          <article><span>VQE 收敛</span><strong>{{ selectedPoint.vqe_converged === true ? '已收敛' : selectedPoint.vqe_converged === false ? '未收敛' : '—' }}</strong></article>
          <article><span>质量状态</span><strong>{{ selectedPoint.validation_status || '—' }}</strong></article>
          <article><span>Qubits / Pauli</span><strong>{{ value(selectedPoint.qubit_count) }} / {{ value(selectedPoint.pauli_term_count) }}</strong></article>
          <article><span>点状态</span><strong>{{ selectedPoint.status }}</strong></article>
        </div>
        <ScientificValidationPanels :optimizer-validation="selectedPoint.optimizer_validation" :scientific-validation="selectedPoint.scientific_validation" :deployment-validation="selectedPoint.deployment_validation" :versions="pointVersions" />
        <section v-if="selectedPoint.scientific_validation" class="science-diagnostics"><header><span>SCIENTIFIC DIAGNOSTICS</span><h4>科学诊断</h4></header><div><article v-for="item in pointScientificDiagnostics" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></article></div></section>
        <p class="science-note">优化器收敛只表示参数搜索满足终止条件，不等于 VQE 已接近 FCI。</p>
        <div v-if="selectedPoint.validation_issues?.length" class="issue-list"><strong>validation issues</strong><p v-for="issue in selectedPoint.validation_issues" :key="`${issue.code}-${issue.stage}`">{{ issue.code }} · {{ issue.stage || '—' }} · {{ issue.message }}<template v-if="issue.iteration !== null && issue.iteration !== undefined"> · iteration {{ issue.iteration }}</template></p></div>
        <div v-if="selectedPoint.optimizer_diagnostics" class="diagnostics"><strong>optimizer diagnostics</strong><span>终止状态：{{ value(selectedPoint.optimizer_diagnostics.scipy_status) }}</span><span>终止原因：{{ value(selectedPoint.optimizer_diagnostics.termination_reason) }}</span><span>最佳迭代：{{ value(selectedPoint.optimizer_diagnostics.best_iteration) }}</span><span>目标函数评估次数：{{ value(selectedPoint.optimizer_diagnostics.nfev) }}</span><span>能量变化：{{ selectedPoint.optimizer_diagnostics.recent_energy_changes_hartree?.map(energy).join('，') || '—' }}</span></div>
        <div v-if="selectedPoint.stages?.length" class="stage-list"><strong>执行阶段</strong><span v-for="stage in selectedPoint.stages" :key="stage.stage || stage.id">{{ stage.stage || stage.id }} · {{ stage.status }} · {{ value(stage.duration_ms) }}</span></div>
        <el-alert v-if="selectedPoint.error" type="error" :closable="false" :title="selectedPoint.error.code || '扫描点失败'">{{ selectedPoint.error.message }} · {{ selectedPoint.error.stage || '—' }}</el-alert>
        <pre>{{ selectedPoint.qasm || '—' }}</pre>
      </section>

      <section v-if="deployment.length" class="panel deployment-panel">
        <header><span>DEPLOYMENT REFERENCE</span><h3>最低 VQE 点部署报告</h3><p>以下部署结果对应 VQE 离散最低能量点，不代表所有扫描点均执行了部署评估。</p></header>
        <p class="mono">deployment_reference_point_index = {{ value(scan.result?.deployment_reference_point_index) }}</p>
        <article v-for="evaluation in deployment" :key="evaluation.evaluation_id || evaluation.architecture_id" class="deployment">
          <header><div><strong>{{ evaluation.architecture_name || evaluation.architecture_id }}</strong><span>{{ evaluation.status }}</span></div><el-tag :type="evaluation.is_deployable === true ? 'success' : evaluation.is_deployable === false ? 'danger' : 'info'">{{ evaluation.is_deployable === true ? '可部署' : evaluation.is_deployable === false ? '不可部署' : '—' }}</el-tag></header>
          <div class="deployment-metrics"><span>分区规模 <b>{{ evaluation.partition_summary?.partition_count ?? '—' }}</b></span><span>SWAP <b>{{ value(evaluation.metrics?.abstract_swap_count) }}</b></span><span>跨 QPU 通信 <b>{{ value(evaluation.metrics?.cross_partition_communication_count) }}</b></span><span>原始 / 路由后操作 <b>{{ value(evaluation.metrics?.original_operation_count) }} / {{ value(evaluation.metrics?.routed_operation_count) }}</b></span><span>原生双比特等价开销 <b>{{ value(evaluation.metrics?.native_two_qubit_gate_equivalent_count) }}</b></span><span>分布式 VQE 能量 <b>{{ energy(evaluation.energy_validation?.distributed_simulation_energy_hartree) }}</b></span><span>Distributed VQE–VQE execution error <b>{{ energy(evaluation.energy_validation?.distributed_execution_error_hartree) }}</b></span></div>
          <ScientificValidationPanels :deployment-validation="evaluation.deployment_validation" :versions="{}" />
          <ParticleConservingCircuitLegend :routed-plan="evaluation.distribution?.routed_execution_plan" />
          <p v-if="evaluation.failure_reason" class="failure">{{ evaluation.failure_reason.code || 'deployment_failed' }} · {{ evaluation.failure_reason.message }} · {{ evaluation.failure_reason.stage || '—' }}</p>
          <details><summary>分区、映射与路由证据</summary><div class="evidence"><p><b>分区：</b>{{ json(evaluation.partition_summary?.partitions) }}</p><p><b>虚拟节点映射：</b>{{ json(evaluation.distribution?.virtual_node_mapping) }}</p><p><b>芯片间拓扑：</b>{{ json(evaluation.architecture?.inter_qpu_topology) }}</p><p><b>芯片内 physical coupling map：</b>{{ json(evaluation.architecture?.virtual_qpus) }}</p><p><b>初始 / 最终布局：</b>{{ json(evaluation.distribution?.initial_logical_to_physical_layout) }} / {{ json(evaluation.distribution?.final_logical_to_physical_layout) }}</p><p><b>SWAP 路径：</b>{{ json(evaluation.distribution?.swap_paths) }}</p><p><b>双比特门路由证据：</b>{{ json(evaluation.distribution?.two_qubit_routing_evidence) }}</p><p><b>routed_execution_plan：</b>{{ json(evaluation.distribution?.routed_execution_plan) }}</p><p><b>communication_events：</b>{{ json(evaluation.distribution?.communication_events) }}</p><p><b>state_norm：</b>{{ value(evaluation.distribution?.state_norm) }}</p><p><b>actual_partition_consumption：</b>{{ value(evaluation.distribution?.actual_partition_consumption) }}</p><p><b>actual_routed_plan_consumption：</b>{{ evaluation.distribution?.actual_routed_plan_consumption === true ? '路由后计划已实际消费' : value(evaluation.distribution?.actual_routed_plan_consumption) }}</p></div></details>
        </article>
      </section>
      <el-alert v-else-if="isTerminal && scan.result?.deployment_reference_point_index === null" type="info" :closable="false" title="没有通过验证的 VQE 点，因此未执行部署评估。" />
        </div>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { bondScanDeploymentReferenceView, getMolecularBondScan, isBondScanTerminalStatus, mergeMolecularBondScan, normalizeMolecularBondScanError, scanCurveSeries, scanMinimumCards } from '../services/molecularBondScanService.js'
import { saveRecentMolecularBondScan } from '../services/molecularBondScanStorage.js'
import { clearAuthSession, readUser } from '../services/authStorage.js'
import { createCopilotResultDraft, savePendingCopilotDraft } from '../services/assistantCopilotContext.js'
import ScientificValidationPanels from '../components/ScientificValidationPanels.vue'
import ParticleConservingCircuitLegend from '../components/ParticleConservingCircuitLegend.vue'
import BeginnerResultSummary from '../components/BeginnerResultSummary.vue'
import { implementationVersions, scanScientificErrorSeries } from '../services/scientificValidationService.js'
import { summarizeBondScanForBeginners } from '../services/beginnerExperienceService.js'
import { summarizeScanDecision } from '../services/productExperienceService.js'

const route = useRoute()
const router = useRouter()
const scan = ref(null)
const loading = ref(false)
const error = ref(null)
const selected = ref(null)
const visible = ref({ hf: true, vqe: true, fci: true })
function askCopilotAboutResult() { const draft = createCopilotResultDraft('molecular_bond_scan', scan.value?.scan_id); if (draft && savePendingCopilotDraft(readUser(), draft)) router.push('/app/copilot') }
let timer = null
const points = computed(() => scan.value?.result?.points || [])
const series = computed(() => scanCurveSeries(points.value))
const minima = computed(() => scanMinimumCards(scan.value?.result))
const deployment = computed(() => scan.value?.result?.deployment_result || [])
const isTerminal = computed(() => isBondScanTerminalStatus(scan.value?.status))
const deploymentReference = computed(() => bondScanDeploymentReferenceView(scan.value || {}))
const beginnerSummary = computed(() => summarizeBondScanForBeginners(scan.value || {}))
const scanDecision = computed(() => summarizeScanDecision(scan.value || {}))
const selectedPoint = computed(() => points.value.find(point => point.point_index === selected.value) || points.value[0] || null)
const pointVersions = computed(() => implementationVersions(selectedPoint.value || {}))
const pointScientificDiagnostics = computed(() => {
  const science = selectedPoint.value?.scientific_validation
  if (!science) return []
  return [
    ['HF 总能量', energy(selectedPoint.value?.hf_energy_hartree)], ['HF determinant reference energy', energy(science.hf_determinant_energy_hartree)], ['zero-parameter energy', energy(science.zero_parameter_energy_hartree)], ['first objective energy', energy(science.first_objective_energy_hartree)], ['best VQE energy', energy(selectedPoint.value?.vqe_energy_hartree)], ['exact qubit ground energy', energy(science.exact_qubit_ground_energy_hartree)], ['FCI energy', energy(science.fci_reference_energy_hartree)], ['VQE–FCI error', energy(science.vqe_fci_error_hartree)], ['chemical accuracy threshold', energy(science.chemical_accuracy_threshold_hartree)], ['target electron count', value(science.target_electron_count)], ['particle number expectation', value(science.particle_number_expectation)], ['particle number variance', value(science.particle_number_variance)], ['spin square / expected', `${value(science.spin_square)} / ${value(science.expected_spin_square)}`], ['spin contamination', value(science.spin_contamination)],
  ].map(([label, displayValue]) => ({ label, value: displayValue }))
})
const currentDistance = computed(() => {
  if (scan.value?.current_point_index === null || scan.value?.current_point_index === undefined) return '—'
  const point = points.value.find(item => item.point_index === scan.value.current_point_index)
  return point ? `${point.distance_angstrom} Å` : '—'
})
const value = input => input === null || input === undefined || input === '' ? '—' : String(input)
const energy = input => input === null || input === undefined || input === '' ? '—' : `${Number(input).toPrecision(10)} Ha`
const fciLabel = point => {
  const status = point?.fci_reference?.status
  if (status === 'available') return energy(point.fci_reference.energy_hartree)
  if (status === 'not_configured') return '未配置 FCI 参考'
  if (status === 'unavailable' || status === 'not_supported') return 'FCI 不可用'
  return '—'
}
function json(input) { return input === null || input === undefined ? '—' : JSON.stringify(input) }
function chart(data) {
  const all = [...series.value.hf, ...series.value.vqe, ...series.value.fci]
  if (!data.length || !all.length) return []
  const xs = all.map(point => point.distance)
  const ys = all.map(point => point.energy)
  const xMin = Math.min(...xs), xMax = Math.max(...xs), yMin = Math.min(...ys), yMax = Math.max(...ys)
  const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1
  return data.map(point => ({ ...point, x: 72 + (point.distance - xMin) * 788 / xRange, y: 300 - (point.energy - yMin) * 265 / yRange }))
}
const chartDots = computed(() => Object.entries(series.value).filter(([name]) => visible.value[name]).map(([name, data]) => ({ name, data: chart(data) })))
const chartLines = computed(() => chartDots.value.map(item => ({ ...item, points: item.data.map(point => `${point.x},${point.y}`).join(' ') })))
const scientificErrorSeries = computed(() => scanScientificErrorSeries(points.value))
function stop() { if (timer) clearTimeout(timer); timer = null }
async function load() {
  stop(); loading.value = true; error.value = null
  try {
    scan.value = mergeMolecularBondScan(scan.value, await getMolecularBondScan(route.params.scanId))
    saveRecentMolecularBondScan(scan.value)
    if (!isBondScanTerminalStatus(scan.value.status)) timer = setTimeout(load, 2500)
  } catch (caught) {
    error.value = normalizeMolecularBondScanError(caught)
    if (error.value.status === 401) {
      clearAuthSession()
      router.replace({ path: '/auth', query: { tab: 'login', redirect: route.fullPath } })
    }
  } finally { loading.value = false }
}
watch(() => route.params.scanId, load)
onMounted(load)
onBeforeUnmount(stop)
</script>

<style scoped>
.scan-result,.head,.head>div,.fixed-tags,.curve-panel{min-width:0;max-width:100%}.head .mono,.head .simulation-note{overflow-wrap:anywhere;word-break:break-word}.fixed-tags :deep(.el-button){height:auto;max-width:100%;white-space:normal;text-align:left}@media(max-width:760px){.head{padding:20px}.panel,.curve-panel{min-width:0;max-width:100%}.table{max-width:100%;overflow-x:auto}.curve-panel{overflow-x:auto}}
</style>

<style scoped>
.fixed-tags :deep(.el-tag){border-color:#b7cbaa;background:#edf4e8;color:#385a2c;font-weight:700}.fixed-tags :deep(.el-tag--warning){border-color:#e4c476;background:#fff5dc;color:#895d10}.simulation-note{margin-top:10px!important;color:#42662f!important;font:700 .68rem ui-monospace,monospace!important}
.scan-decision{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;border:1px solid var(--lz-line);background:var(--lz-line)}.scan-decision article{min-height:138px;padding:19px;background:var(--lz-panel);display:grid;align-content:start;gap:9px}.scan-decision span{color:var(--lz-muted);font-size:.68rem}.scan-decision strong{font-size:.92rem;line-height:1.45;overflow-wrap:anywhere}.scan-decision p{margin:0;color:var(--lz-muted);font-size:.75rem;line-height:1.55}.scan-evidence{border:1px solid var(--lz-line);background:var(--lz-bg-soft)}.scan-evidence>summary{padding:18px 20px;color:var(--lz-accent-deep);cursor:pointer;font-weight:700;font-size:.86rem}.scan-evidence[open]>summary{border-bottom:1px solid var(--lz-line)}.scan-evidence-body{padding:20px;display:grid;gap:18px}.scan-evidence-body>.panel{margin:0}@media(max-width:760px){.scan-decision{grid-template-columns:1fr}.scan-evidence-body{padding:20px}}
.scan-result{display:grid;gap:22px}.loading,.panel{padding:30px;border:1px solid #c9cec7;background:#fff}.head{min-height:175px;padding:32px;border:1px solid #c7cdc5;background:#e7eae3;display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.head span,.panel header>span,.science-diagnostics header>span,.error-strip header span,.deployment-reference-status>span{color:#6c7b70;font:700 .66rem ui-monospace,monospace;letter-spacing:.12em}.head h2{margin:10px 0;font-size:clamp(2rem,4.5vw,4.5rem);letter-spacing:-.065em}.fixed-tags{display:flex;gap:8px;flex-wrap:wrap}.mono{font-family:ui-monospace,monospace}.overview,.minima,.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:#d5dbd3}.overview article,.minima article,.metric-grid article{padding:18px;background:#f5f6f3;min-height:105px;display:grid;align-content:space-between}.overview span,.minima span,.metric-grid span{color:#748079;font-size:.68rem}.overview strong,.minima strong,.metric-grid strong{font:700 .85rem ui-monospace,monospace}.overview small{color:#7c8880;font-size:.66rem}.deployment-reference-status{padding:17px 20px;border:1px solid #cbd2c9;background:#f5f7f3;display:grid;gap:6px}.deployment-reference-status strong{font-size:1rem}.deployment-reference-status p{margin:0;color:#5f6c64;font-size:.78rem}.deployment-reference-status.engineering{border-color:#d5b65d;background:#fbf2d8}.deployment-reference-status.engineering>span{color:#8b6c18}.panel h3{margin:8px 0;font-size:1.5rem}.panel header p{color:#67736b;font-size:.78rem}.legend{display:flex;gap:14px}.curve{width:100%;min-height:360px;margin-top:16px;background:#f6f7f4}.curve line{stroke:#9da9a0}.curve polyline{fill:none;stroke-width:3}.curve polyline.HF,.curve circle.HF{stroke:#17201d;fill:#17201d}.curve polyline.VQE,.curve circle.VQE{stroke:#5e9437;fill:#5e9437}.curve polyline.FCI,.curve circle.FCI{stroke:#a56b3c;fill:#a56b3c}.curve circle{r:5;cursor:pointer}.curve circle.warning{stroke:#bc8a1f;stroke-width:5}.curve text{fill:#6d786f;font-size:13px}.error-strip{margin-top:15px;padding:14px;border:1px solid #d7dcd5;background:#f7f8f5}.error-strip header{display:flex;justify-content:space-between}.error-strip header strong{font-size:.78rem}.error-points{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.error-points button{padding:7px 9px;border:1px solid #84a068;background:#edf4e8;color:#315528;cursor:pointer;font:.68rem ui-monospace,monospace}.error-points button.review{border-color:#c19730;background:#faf0d9;color:#785e1f}.minima{grid-template-columns:repeat(4,1fr)}.minima small{color:#87601c;line-height:1.45}.table{border:1px solid #d9ded7}.table button{width:100%;padding:13px;border:0;border-bottom:1px solid #e1e5df;display:grid;grid-template-columns:70px repeat(6,1fr);gap:8px;text-align:left;background:#fff;cursor:pointer;font:.7rem ui-monospace,monospace}.table button.selected{background:#eaf0e4}.metric-grid{grid-template-columns:repeat(4,1fr)}.science-note{padding:13px;border-left:3px solid #bd8f27;background:#f6eedb;color:#655a37}.science-diagnostics{margin-top:14px;padding:15px;border:1px solid #d5dbd3;background:#f7f8f5}.science-diagnostics h4{margin:7px 0 12px}.science-diagnostics>div{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#d8ded7}.science-diagnostics article{min-height:74px;padding:11px;background:#fff;display:grid;align-content:space-between}.science-diagnostics span{color:#748079;font-size:.67rem}.science-diagnostics strong{font:.71rem ui-monospace,monospace;overflow-wrap:anywhere}.issue-list,.diagnostics,.stage-list{display:grid;gap:7px;margin-top:14px;padding:15px;border:1px solid #ddd6ba;background:#fffdf4;font-size:.76rem}.diagnostics{grid-template-columns:repeat(2,minmax(0,1fr));border-color:#d5dbd3;background:#f5f7f2}.stage-list{grid-template-columns:repeat(2,minmax(0,1fr));border-color:#d5dbd3;background:#f7f8f5}.issue-list strong,.diagnostics strong,.stage-list strong{grid-column:1/-1}.detail pre{max-height:240px;margin-top:14px;padding:15px;overflow:auto;background:#17201d;color:#cfe6b5;font:.67rem/1.6 ui-monospace,monospace}.deployment-panel{display:grid;gap:14px}.deployment{padding:18px;border:1px solid #d5dbd3}.deployment>header{display:flex;justify-content:space-between;align-items:center}.deployment>header div{display:grid;gap:5px}.deployment>header strong{font-family:ui-monospace,monospace}.deployment>header span{color:#758078;font-size:.72rem}.deployment-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin-top:14px;background:#d9ded7}.deployment-metrics span{padding:11px;background:#f6f7f4;color:#6c7770;font-size:.7rem}.deployment-metrics b{display:block;margin-top:5px;color:#1b2620;font:700 .76rem ui-monospace,monospace}.failure{padding:10px;border-left:3px solid #bb7554;background:#fff2ed;color:#7b4633;font-size:.75rem}.deployment details{margin-top:14px}.deployment summary{color:#547c38;cursor:pointer;font-weight:700;font-size:.8rem}.evidence{display:grid;gap:7px;margin-top:10px;padding:12px;background:#f7f8f5;font:.7rem/1.5 ui-monospace,monospace;overflow:auto}.evidence p{margin:0;white-space:pre-wrap;word-break:break-word}@media(max-width:760px){.head{align-items:flex-start;flex-direction:column}.overview,.minima,.metric-grid,.deployment-metrics,.diagnostics,.stage-list,.science-diagnostics>div{grid-template-columns:1fr}.panel{padding:20px}.table{overflow:auto}.table button{min-width:800px}.curve{min-width:700px}.curve-panel{overflow:auto}}</style>
