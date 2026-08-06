<template>
  <div class="molecule-result-page">
    <header class="result-head">
      <div>
        <span class="lz-kicker">Molecule workflow result</span>
        <h2>{{ result?.molecule?.molecule_name || '分子计算结果' }}</h2>
        <p class="mono">Workflow ID：{{ workflowId }}</p>
      </div>
      <div class="result-actions">
        <el-tag effect="dark">模拟器</el-tag>
        <el-tag type="info" effect="plain">虚拟节点逻辑分布式模拟</el-tag>
        <el-tag v-if="result?.is_real_qpu === false" type="warning" effect="plain">非真实 QPU</el-tag>
        <el-tag v-else-if="result" type="danger" effect="plain">QPU 标识异常</el-tag>
        <el-button @click="loadWorkflow">刷新结果</el-button>
        <router-link to="/app/molecules"><el-button type="primary">新建计算</el-button></router-link>
      </div>
    </header>

    <el-alert v-if="loadError" type="error" :closable="false" show-icon>
      <template #title>{{ loadError.title }}</template>
      <p>{{ loadError.message }}</p>
      <p v-if="loadError.stage">失败阶段：{{ stageLabel(loadError.stage) }}</p>
      <p v-if="loadError.workflowId" class="mono">Workflow ID：{{ loadError.workflowId }}</p>
      <router-link v-if="loadError.status === 401" to="/auth?tab=login"><el-button size="small">重新登录</el-button></router-link>
    </el-alert>

    <section v-if="isLoading" class="loading-panel" aria-live="polite">
      <el-icon class="is-loading" :size="28"><Loading /></el-icon>
      <strong>正在恢复 Workflow 结果</strong>
    </section>

    <template v-else-if="result">
      <section class="validation-summary result-panel" :class="`validation-${validationStatus || 'unknown'}`">
        <div class="validation-copy">
          <span class="section-index">Validation</span>
          <h3>{{ validationLabel }}</h3>
          <p>状态 completed 仅表示九阶段执行结束并已保存结果；科研有效性以 validation_status 为准。</p>
        </div>
        <el-tag :type="validationTagType" effect="dark" size="large">{{ validationLabel }}</el-tag>
        <div v-if="result.validation_issues?.length" class="validation-issues">
          <article v-for="issue in result.validation_issues" :key="`${issue.code}-${issue.stage}`">
            <div><code>{{ issue.code }}</code><el-tag type="warning" effect="plain">{{ stageLabel(issue.stage) }}</el-tag></div>
            <p>{{ issue.message }}</p>
            <small>迭代次数：{{ issue.iteration_count }}</small>
          </article>
        </div>
      </section>

      <section class="stage-panel result-panel">
        <div class="section-head"><div><span class="section-index">01</span><h3>九阶段执行记录</h3></div><el-tag type="info">后端真实状态</el-tag></div>
        <ol class="actual-stages">
          <li v-for="(definition, index) in stageDefinitions" :key="definition.id" :class="stageRecord(definition.id)?.status || 'missing'">
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <strong>{{ definition.label }}</strong>
            <small>{{ statusText(stageRecord(definition.id)?.status) }}</small>
            <em>{{ formatDuration(stageRecord(definition.id)?.duration_ms) }}</em>
            <details v-if="stageRecord(definition.id)?.details && Object.keys(stageRecord(definition.id).details).length">
              <summary>阶段详情</summary>
              <pre>{{ formatDetails(stageRecord(definition.id).details) }}</pre>
            </details>
          </li>
        </ol>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">02</span><h3>分子与固定几何</h3></div><el-tag effect="plain">未执行几何优化</el-tag></div>
        <dl class="metrics-grid">
          <div><dt>分子</dt><dd>{{ result.molecule.molecule_name }}</dd></div>
          <div><dt>原子数</dt><dd>{{ result.molecule.atom_count }}</dd></div>
          <div><dt>电荷</dt><dd>{{ result.molecule.charge }}</dd></div>
          <div><dt>自旋多重度</dt><dd>{{ result.molecule.spin_multiplicity }}</dd></div>
          <div><dt>基组</dt><dd>{{ result.molecule.basis_set }}</dd></div>
          <div><dt>几何来源</dt><dd>输入固定几何</dd></div>
        </dl>
        <div class="data-table geometry-table">
          <div class="table-row table-head"><span>元素</span><span>X (Å)</span><span>Y (Å)</span><span>Z (Å)</span></div>
          <div v-for="(atom, index) in result.molecule.geometry" :key="index" class="table-row">
            <strong>{{ atom.element }}</strong><span v-for="value in atom.coordinates_angstrom" :key="value">{{ formatNumber(value, 6) }}</span>
          </div>
        </div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">03</span><h3>电子结构与活性空间</h3></div></div>
        <dl class="metrics-grid">
          <div class="accent-metric"><dt>HF 能量</dt><dd>{{ formatEnergy(result.hf_energy_hartree) }}</dd></div>
          <div><dt>活性电子数</dt><dd>{{ result.active_space.active_electrons }}</dd></div>
          <div><dt>活性轨道数</dt><dd>{{ result.active_space.active_orbitals }}</dd></div>
          <div><dt>选择方法</dt><dd>{{ result.active_space.selection_method }}</dd></div>
        </dl>
        <div class="data-table orbital-table">
          <div class="table-row table-head"><span>轨道索引</span><span>轨道能量 (Hartree)</span></div>
          <div v-for="(orbitalIndex, index) in result.active_space.orbital_indices" :key="orbitalIndex" class="table-row">
            <strong>{{ orbitalIndex }}</strong><span>{{ formatNumber(result.active_space.orbital_energies_hartree[index], 8) }}</span>
          </div>
        </div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">04</span><h3>Qubit Hamiltonian</h3></div><el-tag effect="plain">{{ result.hamiltonian.mapping_method }}</el-tag></div>
        <dl class="metrics-grid">
          <div><dt>量子比特数</dt><dd>{{ result.hamiltonian.qubit_count }}</dd></div>
          <div><dt>映射前量子比特数</dt><dd>{{ result.hamiltonian.qubit_count_before_tapering }}</dd></div>
          <div><dt>Pauli 项数</dt><dd>{{ result.hamiltonian.pauli_term_count }}</dd></div>
          <div><dt>截断阈值</dt><dd>{{ result.hamiltonian.coefficient_cutoff }}</dd></div>
        </dl>
        <el-collapse>
          <el-collapse-item :title="`展开 Pauli 项表（${result.hamiltonian.pauli_terms.length} 项）`" name="pauli-terms">
            <div class="data-table pauli-table">
              <div class="table-row table-head"><span>Pauli string</span><span>Coefficient</span></div>
              <div v-for="(term, index) in result.hamiltonian.pauli_terms" :key="`${term.pauli_string}-${index}`" class="table-row">
                <code>{{ term.pauli_string }}</code><span>{{ formatNumber(term.coefficient, 12) }}</span>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">05</span><h3>VQE 优化与线路</h3></div><el-tag :type="result.vqe.converged ? 'success' : 'warning'">{{ result.vqe.converged ? '已收敛' : '未收敛' }}</el-tag></div>
        <dl class="metrics-grid">
          <div><dt>Ansatz</dt><dd>{{ result.vqe.ansatz }}</dd></div>
          <div><dt>优化器</dt><dd>{{ result.vqe.optimizer }}</dd></div>
          <div><dt>迭代次数</dt><dd>{{ result.vqe.iteration_count }}</dd></div>
          <div><dt>初态</dt><dd>{{ result.vqe.initial_state }}</dd></div>
        </dl>
        <div v-if="optimizerDiagnostics" class="optimizer-diagnostics">
          <div class="diagnostics-head">
            <div><span class="section-index">Optimizer diagnostics</span><h4>{{ result.vqe.optimizer }} 终止诊断</h4></div>
            <el-tag :type="optimizerDiagnostics.scipy_success ? 'success' : 'warning'">
              {{ optimizerDiagnostics.scipy_success ? '优化器正常终止' : '优化器未成功终止' }}
            </el-tag>
          </div>
          <dl class="diagnostics-grid">
            <div><dt>优化器终止状态</dt><dd>Scipy status {{ optimizerDiagnostics.scipy_status }}</dd></div>
            <div><dt>终止原因</dt><dd>{{ terminationReasonLabel(optimizerDiagnostics.termination_reason) }}</dd></div>
            <div><dt>最佳迭代</dt><dd>{{ optimizerDiagnostics.best_iteration }}</dd></div>
            <div><dt>目标函数评估次数</dt><dd>{{ optimizerDiagnostics.nfev }}</dd></div>
            <div><dt>初始能量</dt><dd>{{ formatEnergy(optimizerDiagnostics.initial_energy_hartree) }}</dd></div>
            <div><dt>最终能量</dt><dd>{{ formatEnergy(optimizerDiagnostics.final_energy_hartree) }}</dd></div>
          </dl>
          <div class="termination-message"><span>后端终止说明</span><code>{{ optimizerDiagnostics.scipy_message }}</code></div>
          <div class="energy-changes">
            <span>能量变化</span>
            <code v-for="(change, index) in optimizerDiagnostics.recent_energy_changes_hartree" :key="index">{{ formatSignedEnergyChange(change) }}</code>
            <small v-if="!optimizerDiagnostics.recent_energy_changes_hartree?.length">无近期变化记录</small>
          </div>
          <p class="diagnostic-note">目标函数评估次数由优化器报告，Powell 的该数值可以大于配置的最大迭代数，不表示参数超限。</p>
        </div>
        <div class="chart-card">
          <div class="chart-title"><strong>迭代能量曲线</strong><span>Energy (Hartree)</span></div>
          <svg viewBox="0 0 720 240" role="img" aria-label="VQE 迭代能量曲线">
            <line x1="48" y1="20" x2="48" y2="205" class="axis" /><line x1="48" y1="205" x2="700" y2="205" class="axis" />
            <polyline :points="energyPolyline" class="energy-line" />
            <circle v-for="point in energyPoints" :key="point.iteration" :cx="point.x" :cy="point.y" r="4"><title>迭代 {{ point.iteration }}：{{ point.energy }}</title></circle>
            <text x="48" y="225">1</text><text x="665" y="225">{{ result.vqe.iteration_count }}</text>
            <text x="54" y="35">{{ formatNumber(energyRange.max, 6) }}</text><text x="54" y="197">{{ formatNumber(energyRange.min, 6) }}</text>
          </svg>
        </div>
        <el-collapse>
          <el-collapse-item title="展开最终 OpenQASM 2.0" name="qasm"><pre class="qasm-block">{{ result.vqe.qasm }}</pre></el-collapse-item>
        </el-collapse>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">06</span><h3>线路分区</h3></div></div>
        <dl class="metrics-grid">
          <div><dt>分区数量</dt><dd>{{ partition.partition_count }}</dd></div>
          <div><dt>Teleportation</dt><dd>{{ partition.teleportations }}</dd></div>
          <div><dt>全局门数量</dt><dd>{{ partition.global_gate_count }}</dd></div>
          <div><dt>分区方法</dt><dd>{{ partition.method }}</dd></div>
        </dl>
        <div class="partition-cards">
          <article v-for="item in partition.partitions" :key="item.partition_id"><span>{{ item.partition_id }}</span><strong>量子比特 {{ item.qubits.join(', ') }}</strong></article>
        </div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">07</span><h3>虚拟节点映射与拓扑</h3></div><el-tag effect="plain">映射代价 {{ formatNumber(result.distribution.mapping_cost, 6) }}</el-tag></div>
        <div class="mapping-layout">
          <div>
            <h4>虚拟节点映射</h4>
            <div class="mapping-list"><article v-for="node in result.distribution.virtual_node_mapping" :key="node.virtual_node_id"><strong>{{ node.virtual_node_id }}</strong><span>{{ node.partition_id }}</span><small>q[{{ node.qubits.join(', ') }}]</small></article></div>
          </div>
          <div>
            <h4>拓扑边</h4>
            <div class="topology-list"><span v-for="(edge, index) in result.distribution.topology_edges" :key="index">节点 {{ edge.source }} ↔ 节点 {{ edge.target }}</span></div>
          </div>
        </div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">08</span><h3>跨分区通信</h3></div><el-tag effect="dark">{{ result.distribution.cross_partition_communication_count }} 次</el-tag></div>
        <div v-if="result.distribution.communication_events.length" class="data-table communication-table">
          <div class="table-row table-head"><span>门序号</span><span>门</span><span>控制 / 目标</span><span>源分区 / 节点</span><span>目标分区 / 节点</span></div>
          <div v-for="event in result.distribution.communication_events" :key="event.gate_index" class="table-row">
            <span>{{ event.gate_index }}</span><code>{{ event.gate }}</code><span>q{{ event.control_qubit }} → q{{ event.target_qubit }}</span><span>{{ event.source_partition_id }} / {{ event.source_virtual_node_id }}</span><span>{{ event.target_partition_id }} / {{ event.target_virtual_node_id }}</span>
          </div>
        </div>
        <p v-else class="empty-copy">没有跨分区通信事件。</p>
      </section>

      <section class="result-panel energy-panel">
        <div class="section-head"><div><span class="section-index">09</span><h3>能量结果对比</h3></div></div>
        <div class="energy-comparison">
          <article><span>未分区基准能量</span><strong>{{ formatEnergy(result.energies.unpartitioned_benchmark_energy_hartree) }}</strong></article>
          <article><span>分布式模拟能量</span><strong>{{ formatEnergy(result.energies.distributed_simulation_energy_hartree) }}</strong></article>
          <article class="error-card"><span>绝对误差</span><strong>{{ formatEnergy(result.energies.absolute_error_hartree) }}</strong></article>
        </div>
        <p>执行后端：模拟器 · 能力级别：虚拟节点逻辑分布式模拟 · {{ result.distribution.is_real_qpu === false ? '非真实 QPU' : 'QPU 标识异常' }}</p>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { clearAuthSession } from '../services/authStorage'
import {
  MOLECULE_STAGE_DEFINITIONS,
  getMoleculeWorkflow,
  normalizeMoleculeWorkflowError,
  stageLabel,
} from '../services/moleculeWorkflowService'
import { saveRecentMoleculeWorkflow } from '../services/moleculeWorkflowStorage'

const route = useRoute()
const result = ref(null)
const loadError = ref(null)
const isLoading = ref(false)
const stageDefinitions = MOLECULE_STAGE_DEFINITIONS
const workflowId = computed(() => String(route.params.workflowId || ''))
const partition = computed(() => result.value?.distribution?.partition_scheme || { partitions: [] })
const validationStatus = computed(() => result.value?.validation_status || '')
const validationLabel = computed(() => ({
  passed: '计算通过',
  needs_review: '计算完成，需要复核',
})[validationStatus.value] || '计算完成，验证状态待确认')
const validationTagType = computed(() => ({ passed: 'success', needs_review: 'warning' })[validationStatus.value] || 'info')
const optimizerDiagnostics = computed(() => result.value?.vqe?.optimizer_diagnostics || null)

const energyRange = computed(() => {
  const values = (result.value?.vqe?.iteration_history || []).map(item => Number(item.energy_hartree)).filter(Number.isFinite)
  if (!values.length) return { min: 0, max: 1 }
  const min = Math.min(...values)
  const max = Math.max(...values)
  return min === max ? { min: min - 0.000001, max: max + 0.000001 } : { min, max }
})

const energyPoints = computed(() => {
  const history = result.value?.vqe?.iteration_history || []
  const width = 640
  const height = 165
  return history.map((item, index) => ({
    iteration: item.iteration,
    energy: item.energy_hartree,
    x: 48 + (history.length === 1 ? width / 2 : index * width / (history.length - 1)),
    y: 30 + (energyRange.value.max - item.energy_hartree) / (energyRange.value.max - energyRange.value.min) * height,
  }))
})
const energyPolyline = computed(() => energyPoints.value.map(point => `${point.x},${point.y}`).join(' '))

async function loadWorkflow() {
  if (!workflowId.value) return
  isLoading.value = true
  loadError.value = null
  try {
    result.value = await getMoleculeWorkflow(workflowId.value)
    saveRecentMoleculeWorkflow(result.value)
  } catch (error) {
    result.value = null
    loadError.value = normalizeMoleculeWorkflowError(error)
    if (loadError.value.status === 401) clearAuthSession()
  } finally {
    isLoading.value = false
  }
}

function stageRecord(stageId) { return result.value?.stages?.find(stage => stage.stage === stageId) }
function statusText(status) { return ({ completed: '已完成', failed: '失败', running: '执行中' })[status] || '无状态记录' }
function formatDuration(value) { return Number.isFinite(Number(value)) ? `${formatNumber(value, 2)} ms` : '--' }
function formatNumber(value, digits = 6) { return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '--' }
function formatEnergy(value) { return `${formatNumber(value, 10)} Hartree` }
function formatDetails(details) { return JSON.stringify(details, null, 2) }
function formatSignedEnergyChange(value) {
  if (!Number.isFinite(Number(value))) return '--'
  return `${Number(value) >= 0 ? '+' : ''}${Number(value).toExponential(4)} Ha`
}
function terminationReasonLabel(reason) {
  return ({
    optimizer_reported_success: '优化器报告成功',
    maximum_function_evaluations: '达到目标函数评估次数上限',
    trust_region_radius_lower_bound: '信赖域半径达到下限',
  })[reason] || reason || '--'
}

onMounted(loadWorkflow)
watch(workflowId, loadWorkflow)
</script>

<style scoped>
.molecule-result-page { display: grid; gap: 18px; }
.result-head, .section-head, .result-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.result-head h2 { margin: 5px 0; font-size: clamp(1.6rem, 3vw, 2.25rem); }
.result-head p { margin: 0; color: var(--lz-muted); overflow-wrap: anywhere; }
.result-actions { flex-wrap: wrap; justify-content: flex-end; }
.result-panel, .loading-panel { padding: 22px; border: 1px solid var(--lz-line); border-radius: 12px; background: rgba(8, 20, 36, .74); box-shadow: var(--lz-shadow); }
.validation-summary { display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; }
.validation-summary.validation-passed { border-color: rgba(56, 243, 194, .38); }
.validation-summary.validation-needs_review { border-color: rgba(242, 195, 91, .52); background: rgba(54, 39, 10, .5); }
.validation-copy h3 { margin: 5px 0; }
.validation-copy p { margin: 0; color: var(--lz-muted); line-height: 1.6; }
.validation-issues { grid-column: 1 / -1; display: grid; gap: 10px; }
.validation-issues article { padding: 14px; border: 1px solid rgba(242, 195, 91, .3); border-radius: 8px; background: rgba(242, 195, 91, .05); }
.validation-issues article > div { display: flex; align-items: center; gap: 10px; }
.validation-issues p { margin: 10px 0; line-height: 1.55; }
.validation-issues small { color: var(--lz-muted); }
.loading-panel { min-height: 220px; display: flex; align-items: center; justify-content: center; gap: 12px; color: var(--lz-cyan); }
.section-head { margin-bottom: 16px; }
.section-head > div { display: flex; align-items: center; gap: 10px; }
.section-head h3 { margin: 0; }
.section-index { color: var(--lz-cyan); font-size: .72rem; font-weight: 800; }
.actual-stages { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.actual-stages li { min-width: 0; padding: 13px; border: 1px solid var(--lz-line); border-radius: 8px; display: grid; grid-template-columns: auto 1fr auto; gap: 5px 9px; }
.actual-stages li > span { color: var(--lz-cyan); font-size: .72rem; font-weight: 800; }
.actual-stages small { color: var(--lz-muted); }
.actual-stages em { color: var(--lz-gold); font-size: .72rem; font-style: normal; }
.actual-stages details { grid-column: 1 / -1; }
.actual-stages summary { color: var(--lz-muted); cursor: pointer; font-size: .72rem; }
.actual-stages pre { max-height: 180px; overflow: auto; white-space: pre-wrap; color: var(--lz-muted); font-size: .68rem; }
.actual-stages .completed { border-color: rgba(56, 243, 194, .3); }
.actual-stages .failed { border-color: rgba(255, 138, 122, .55); }
.metrics-grid { margin: 0 0 18px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.metrics-grid > div { min-width: 0; padding: 14px; border: 1px solid var(--lz-line); border-radius: 8px; background: rgba(255,255,255,.025); }
.metrics-grid dt { color: var(--lz-muted); font-size: .76rem; }
.metrics-grid dd { margin: 7px 0 0; color: var(--lz-text); font-weight: 800; overflow-wrap: anywhere; }
.metrics-grid .accent-metric dd { color: var(--lz-gold); }
.data-table { border: 1px solid var(--lz-line); border-radius: 8px; overflow-x: auto; }
.table-row { min-width: 520px; padding: 10px 12px; display: grid; gap: 12px; border-top: 1px solid var(--lz-line); }
.table-row:first-child { border-top: 0; }
.table-head { color: var(--lz-muted); background: rgba(52,214,255,.05); font-size: .75rem; font-weight: 800; }
.geometry-table .table-row { grid-template-columns: repeat(4, 1fr); }
.orbital-table .table-row, .pauli-table .table-row { grid-template-columns: 1fr 2fr; }
.communication-table .table-row { min-width: 760px; grid-template-columns: .6fr .5fr 1fr 1.2fr 1.2fr; }
.chart-card { margin-bottom: 15px; padding: 15px; border: 1px solid var(--lz-line); border-radius: 8px; overflow-x: auto; }
.chart-title { display: flex; justify-content: space-between; color: var(--lz-muted); }
.chart-title strong { color: var(--lz-text); }
.chart-card svg { min-width: 600px; width: 100%; height: 240px; }
.chart-card .axis { stroke: rgba(147,168,189,.5); stroke-width: 1; }
.chart-card .energy-line { fill: none; stroke: var(--lz-cyan); stroke-width: 3; }
.chart-card circle { fill: var(--lz-gold); }
.chart-card text { fill: var(--lz-muted); font-size: 12px; }
.qasm-block { margin: 0; padding: 16px; max-height: 420px; overflow: auto; border-radius: 8px; color: #d6efff; background: #020711; line-height: 1.6; }
.optimizer-diagnostics { margin-bottom: 15px; padding: 16px; border: 1px solid var(--lz-line); border-radius: 8px; background: rgba(52, 214, 255, .035); }
.diagnostics-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.diagnostics-head h4 { margin: 4px 0 0; }
.diagnostics-grid { margin: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.diagnostics-grid div { padding: 11px; border: 1px solid var(--lz-line); border-radius: 7px; }
.diagnostics-grid dt, .termination-message span, .energy-changes > span { color: var(--lz-muted); font-size: .75rem; }
.diagnostics-grid dd { margin: 5px 0 0; font-weight: 750; overflow-wrap: anywhere; }
.termination-message, .energy-changes { margin-top: 10px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.termination-message code, .energy-changes code { padding: 6px 9px; border-radius: 6px; background: rgba(0, 0, 0, .24); overflow-wrap: anywhere; }
.diagnostic-note { margin: 12px 0 0; color: var(--lz-muted); font-size: .8rem; line-height: 1.55; }
.partition-cards, .mapping-list { display: flex; flex-wrap: wrap; gap: 10px; }
.partition-cards article, .mapping-list article { min-width: 160px; padding: 14px; border: 1px solid var(--lz-line); border-radius: 8px; display: grid; gap: 5px; }
.partition-cards span, .mapping-list span, .mapping-list small { color: var(--lz-muted); }
.mapping-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.mapping-layout h4 { margin: 0 0 12px; }
.topology-list { display: flex; flex-wrap: wrap; gap: 8px; }
.topology-list span { padding: 9px 12px; border: 1px solid var(--lz-line); border-radius: 999px; }
.energy-comparison { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.energy-comparison article { padding: 18px; border: 1px solid var(--lz-line); border-radius: 8px; display: grid; gap: 8px; }
.energy-comparison span { color: var(--lz-muted); }
.energy-comparison strong { color: var(--lz-cyan); font-size: 1.05rem; overflow-wrap: anywhere; }
.energy-comparison .error-card strong { color: var(--lz-gold); }
.energy-panel > p, .empty-copy { color: var(--lz-muted); }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
@media (max-width: 1100px) { .actual-stages, .metrics-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px) { .result-head, .section-head, .diagnostics-head { align-items: flex-start; flex-direction: column; } .result-actions { justify-content: flex-start; } .validation-summary, .actual-stages, .metrics-grid, .diagnostics-grid, .mapping-layout, .energy-comparison { grid-template-columns: 1fr; } .validation-summary > .el-tag { justify-self: start; } .result-panel { padding: 16px; } }
</style>
