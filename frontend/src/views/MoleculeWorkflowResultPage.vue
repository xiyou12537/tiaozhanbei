<template>
  <div class="molecule-result-page">
    <section v-if="loading" class="result-loading" v-loading="true">正在恢复 Workflow 结果…</section>
    <el-alert v-else-if="loadError" type="error" :closable="false" show-icon><template #title>{{ loadError.title }}</template><p>{{ loadError.message }}</p><p v-if="loadError.workflowId" class="mono">Workflow ID：{{ loadError.workflowId }}</p><el-button size="small" @click="loadWorkflow">重试</el-button></el-alert>

    <template v-else-if="result">
      <header class="result-head">
        <div><span class="page-kicker">MOLECULAR WORKFLOW</span><h2>{{ result.molecule?.molecule_name || 'Workflow 结果' }}</h2><p class="mono">{{ result.workflow_id }}</p></div>
        <div class="result-actions"><el-tag>模拟器</el-tag><el-tag type="info">虚拟节点逻辑分布式模拟</el-tag><el-tag v-if="result?.is_real_qpu === false" type="warning">非真实 QPU</el-tag><el-button data-testid="copilot-explain-result" text @click="askCopilotAboutResult">让 Copilot 解释这个结果</el-button><router-link to="/app/molecules"><el-button>新建计算</el-button></router-link></div>
      </header>

      <BeginnerResultSummary compact kind="workflow" :summary="beginnerSummary" />

      <section class="validation-summary" :class="validationClass">
        <div><span class="page-kicker">ENERGY & QUALITY STATUS</span><h3>{{ validationTitle }}</h3><p>{{ validationText }}</p></div>
        <div class="status-pair"><span>执行状态</span><strong>{{ executionLabel }}</strong><span>质量状态</span><strong>{{ result.validation_status || '—' }}</strong></div>
      </section>
      <section class="result-key-metrics" aria-label="核心结果指标">
        <article><span>VQE 能量</span><strong>{{ energy(result.vqe?.energy_hartree) }}</strong><small>Hartree</small></article>
        <article><span>分布式模拟能量</span><strong>{{ energy(result.energies?.distributed_simulation_energy_hartree) }}</strong><small>Hartree</small></article>
        <article><span>绝对误差</span><strong>{{ energy(result.energies?.absolute_error_hartree) }}</strong><small>Hartree</small></article>
        <article><span>质量状态</span><strong>{{ result.validation_status || '待确认' }}</strong><small>完成不等于质量验证通过</small></article>
      </section>

      <details class="workflow-evidence">
        <summary><span>完整专业证据</span><small>Hamiltonian、VQE、FCI、粒子数、分区和路由</small></summary>
        <div class="evidence-body">
      <ScientificValidationPanels :optimizer-validation="result.optimizer_validation" :scientific-validation="result.scientific_validation" :deployment-validation="result.deployment_validation" :versions="versions" />

      <section v-if="result.validation_issues?.length" class="result-panel validation-issues">
        <div class="section-head"><div><span class="section-index">QUALITY ISSUES</span><h3>复核问题</h3></div></div>
        <div class="issue-list"><article v-for="issue in result.validation_issues" :key="`${issue.code}-${issue.stage}`"><strong>{{ issue.code || '—' }}</strong><span>阶段：{{ stageLabel(issue.stage) }}</span><p>{{ issue.message || issue.description || '—' }}</p><small>迭代次数：{{ value(issue.iteration_count) }}</small></article></div>
      </section>

      <section class="result-panel stage-panel">
        <div class="section-head"><div><span class="section-index">01 / PIPELINE</span><h3>执行阶段记录</h3></div><span>后端真实状态 · {{ result.stages?.length || 0 }} 个阶段</span></div>
        <ol class="actual-stages"><li v-for="(stage,index) in result.stages || []" :key="stage.stage"><span>{{ String(index+1).padStart(2,'0') }}</span><strong>{{ stageLabel(stage.stage) }}</strong><small>{{ stage.status || '—' }} · {{ duration(stage.duration_ms) }}</small></li></ol>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">02 / MOLECULE</span><h3>分子与固定几何</h3></div><span>未执行几何优化</span></div>
        <div class="molecule-summary"><article><span>分子</span><strong>{{ value(result.molecule?.molecule_name) }}</strong></article><article><span>电荷</span><strong>{{ value(result.molecule?.charge) }}</strong></article><article><span>自旋多重度</span><strong>{{ value(result.molecule?.spin_multiplicity) }}</strong></article><article><span>基组</span><strong>{{ value(result.molecule?.basis_set) }}</strong></article></div>
        <div class="geometry-table table-grid"><div class="table-head"><span>#</span><span>元素</span><span>X / Å</span><span>Y / Å</span><span>Z / Å</span></div><div v-for="(atom,index) in result.molecule?.geometry || []" :key="index"><span>{{ index+1 }}</span><strong>{{ atom.element }}</strong><span v-for="coordinate in atom.coordinates_angstrom" :key="coordinate">{{ number(coordinate,6) }}</span></div></div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">03 / ELECTRONIC STRUCTURE</span><h3>HF 能量与活性空间</h3></div></div>
        <div class="metrics-grid"><article><span>HF 能量</span><strong>{{ energy(result.hf_energy_hartree) }}</strong><small>Hartree</small></article><article><span>活性电子</span><strong>{{ value(result.active_space?.active_electrons) }}</strong></article><article><span>活性轨道</span><strong>{{ value(result.active_space?.active_orbitals) }}</strong></article><article><span>选择方法</span><strong>{{ value(result.active_space?.selection_method) }}</strong></article></div>
        <div class="orbital-list"><span v-for="(orbital,index) in result.active_space?.orbital_indices || []" :key="orbital"><b>MO {{ orbital }}</b>{{ energy(result.active_space?.orbital_energies_hartree?.[index]) }} Ha</span></div>
      </section>

      <section class="result-panel">
        <div class="section-head"><div><span class="section-index">04 / HAMILTONIAN</span><h3>Qubit Hamiltonian</h3></div></div>
        <div class="metrics-grid"><article><span>量子比特数</span><strong>{{ value(result.hamiltonian?.qubit_count) }}</strong></article><article><span>Pauli 项数</span><strong>{{ value(result.hamiltonian?.pauli_term_count) }}</strong></article><article><span>映射方法</span><strong>{{ value(result.hamiltonian?.mapping_method) }}</strong></article><article><span>截断阈值</span><strong>{{ value(result.hamiltonian?.coefficient_cutoff) }}</strong></article></div>
        <el-collapse><el-collapse-item title="展开 Pauli 项表" name="pauli"><div class="pauli-table"><div><strong>Pauli string</strong><strong>Coefficient</strong></div><div v-for="(term,index) in result.hamiltonian?.pauli_terms || []" :key="index"><code>{{ term.pauli_string }}</code><span>{{ number(term.coefficient,12) }}</span></div></div></el-collapse-item></el-collapse>
      </section>

      <section class="result-panel vqe-panel">
        <div class="section-head"><div><span class="section-index">05 / VQE</span><h3>VQE 优化与线路</h3></div><span>{{ result.vqe?.converged ? '已收敛' : '未收敛' }}</span></div>
        <div class="optimizer-banner"><div><span>优化器</span><strong>{{ value(result.vqe?.optimizer) }}</strong></div><div><span>优化器终止状态</span><strong>{{ optimizerStatus }}</strong></div><div><span>终止原因</span><strong>{{ value(result.vqe?.optimizer_diagnostics?.termination_reason) }}</strong></div><div><span>目标函数评估次数</span><strong>{{ value(result.vqe?.optimizer_diagnostics?.nfev) }}</strong></div><div><span>最佳迭代</span><strong>{{ value(result.vqe?.optimizer_diagnostics?.best_iteration) }}</strong></div><div><span>能量变化</span><strong>{{ recentEnergyChanges }}</strong></div></div>
        <div class="vqe-layout"><div class="energy-history"><h4>迭代能量曲线</h4><svg v-if="historyPoints" viewBox="0 0 720 260" preserveAspectRatio="none" aria-label="VQE 迭代能量曲线"><line x1="40" y1="220" x2="700" y2="220"/><line x1="40" y1="25" x2="40" y2="220"/><polyline :points="historyPoints"/><circle v-for="point in historyDots" :key="point.iteration" :cx="point.x" :cy="point.y" r="4"><title>迭代 {{ point.iteration }}：{{ point.energy }}</title></circle></svg><p v-else>—</p></div><div class="qasm-block"><h4>最终 QASM</h4><pre>{{ result.vqe?.qasm || '—' }}</pre></div></div>
        <ParticleConservingCircuitLegend :ansatz="result.vqe?.ansatz" :qasm="result.vqe?.qasm" :routed-plan="routing.routedPlan" />
      </section>

      <section class="result-panel partition-panel">
        <div class="section-head"><div><span class="section-index">06 / CIRCUIT PARTITION</span><h3>线路分区</h3></div><span>teleportation {{ value(result.distribution?.partition_scheme?.teleportations) }} · 全局门 {{ value(result.distribution?.partition_scheme?.global_gate_count) }}</span></div>
        <div class="partition-grid"><article v-for="partition in routing.partitions" :key="partition.partition_id"><span>{{ partition.partition_id }}</span><strong>{{ qubits(partition.qubits) }}</strong><small>线路分区包含的逻辑量子比特</small></article></div>
      </section>

      <section class="result-panel topology-panel inter-topology">
        <div class="section-head"><div><span class="section-index">07 / INTER-QPU</span><h3>分区间虚拟 QPU 拓扑</h3></div><span>映射代价 {{ value(result.distribution?.mapping_cost) }}</span></div>
        <p class="scope-note">该拓扑只连接虚拟 QPU 节点，用于分区映射与跨分区通信；不与芯片内物理耦合混画。</p>
        <div class="virtual-mapping"><article v-for="item in routing.virtualNodeMapping" :key="item.virtual_node_id"><span>{{ item.partition_id }}</span><strong>{{ item.virtual_node_id }}</strong><small>{{ qubits(item.qubits) }}</small></article></div>
        <div class="topology-edges"><span v-for="(edge,index) in routing.interQpuTopology" :key="index">T{{ edge.source+1 }} <b>—</b> T{{ edge.target+1 }}</span><span v-if="!routing.interQpuTopology.length">—</span></div>
      </section>

      <section class="result-panel chip-routing-panel">
        <div class="section-head"><div><span class="section-index">08 / INTRA-CHIP ROUTING</span><h3>芯片内部物理耦合拓扑</h3></div><span>每颗虚拟 QPU 独立展示</span></div>
        <p class="scope-note">以下每张图只表示单颗虚拟芯片的物理耦合边，以及该芯片内的 logical-to-physical 布局。</p>
        <div class="chip-result-grid"><article v-for="chip in routing.chips" :key="chip.virtual_qpu_id" class="chip-result"><header><div><span>{{ chip.partition_id }}</span><h4>{{ chip.virtual_qpu_id }}</h4></div><strong>{{ value(chip.physical_qubit_count) }} physical qubits</strong></header><div class="physical-couplings"><span v-for="(edge,index) in chip.physical_coupling_map || []" :key="index">q{{ edge.source }} — q{{ edge.target }}</span><span v-if="!chip.physical_coupling_map?.length">—</span></div><h5>logical-to-physical 布局</h5><div class="layout-comparison"><div><span>初始</span><code>{{ layout(chip.logical_to_physical_initial) }}</code></div><b>→</b><div><span>最终</span><code>{{ layout(chip.logical_to_physical_final) }}</code></div></div></article><p v-if="!routing.chips.length">旧记录未提供芯片路由派生字段：—</p></div>
      </section>

      <section class="result-panel swap-panel">
        <div class="section-head"><div><span class="section-index">09 / SWAP EVIDENCE</span><h3>SWAP 路径</h3></div></div>
        <div class="routing-cost"><article><span>抽象 SWAP 数</span><strong>{{ value(routing.routingCost.abstract_swap_count) }}</strong></article><article><span>路由后双量子比特操作</span><strong>{{ value(routing.routingCost.routed_two_qubit_operation_count) }}</strong></article><article><span>原生双量子门等价开销</span><strong>{{ value(routing.routingCost.native_two_qubit_gate_equivalent_count) }}</strong></article></div>
        <h4>芯片内路由成本</h4>
        <div class="evidence-list"><article v-for="(evidence,index) in routing.evidence" :key="`${evidence.partition_id}-${evidence.gate_index}-${index}`"><header><strong>{{ evidence.partition_id }} / {{ evidence.virtual_qpu_id }}</strong><span :class="evidence.routing_status">{{ evidence.routing_status === 'routed' ? '执行 SWAP 路由' : '直接耦合' }}</span></header><div><span>逻辑门</span><code>{{ qubits(evidence.logical_qubits) }}</code><span>物理路径</span><code>{{ path(evidence.path) }}</code><span>SWAP</span><code>{{ swapPath(evidence.swap_path) }}</code></div></article><p v-if="!routing.evidence.length">—</p></div>
        <div class="plan-consumption" :class="{ consumed:routing.routedPlanConsumed }"><span>{{ routing.routedPlanConsumed ? '✓' : '!' }}</span><div><strong>{{ routing.routedPlanConsumed ? '路由后计划已实际消费' : '路由后计划未确认消费' }}</strong><p>actual_routed_plan_consumption={{ String(result.distribution?.actual_routed_plan_consumption ?? '—') }}</p></div></div>
        <el-collapse><el-collapse-item title="展开路由后执行计划" name="plan"><div class="plan-table"><div v-for="item in routing.routedPlan" :key="item.execution_index"><span>#{{ item.execution_index }}</span><strong>{{ item.operation }}</strong><code>{{ item.scope }}</code><span>{{ qubits(item.logical_qubits) }} → {{ qubits(item.physical_qubits,'q') }}</span><b>{{ item.physical_edge_is_valid === false ? '物理边无效' : '物理边有效' }}</b></div><p v-if="!routing.routedPlan.length">—</p></div></el-collapse-item></el-collapse>
      </section>

      <section class="result-panel communication-panel">
        <div class="section-head"><div><span class="section-index">10 / COMMUNICATION</span><h3>跨分区通信</h3></div><span>{{ value(routing.communicationCount) }} 次</span></div>
        <div class="communication-events"><article v-for="(event,index) in routing.communicationEvents" :key="index"><span>Gate {{ value(event.gate_index) }}</span><strong>{{ event.source_partition_id }} / {{ event.source_virtual_node_id }} → {{ event.target_partition_id }} / {{ event.target_virtual_node_id }}</strong><small>{{ event.gate }} q{{ event.control_qubit }} → q{{ event.target_qubit }}</small></article><p v-if="!routing.communicationEvents.length">—</p></div>
      </section>

      <section class="result-panel energy-panel">
        <div class="section-head"><div><span class="section-index">11 / ENERGY</span><h3>能量与质量状态</h3></div></div>
        <div class="energy-comparison"><article><span>未分区基准能量</span><strong>{{ energy(result.energies?.unpartitioned_benchmark_energy_hartree) }}</strong><small>Hartree</small></article><article><span>分布式模拟能量</span><strong>{{ energy(result.energies?.distributed_simulation_energy_hartree) }}</strong><small>Hartree</small></article><article><span>绝对误差</span><strong>{{ energy(result.energies?.absolute_error_hartree) }}</strong><small>Hartree</small></article></div>
      </section>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getMoleculeWorkflow, moleculeWorkflowExecutionMeta, normalizeMoleculeRoutingResult, normalizeMoleculeWorkflowError, stageLabel } from '../services/moleculeWorkflowService'
import { saveRecentMoleculeWorkflow } from '../services/moleculeWorkflowStorage'
import ScientificValidationPanels from '../components/ScientificValidationPanels.vue'
import ParticleConservingCircuitLegend from '../components/ParticleConservingCircuitLegend.vue'
import BeginnerResultSummary from '../components/BeginnerResultSummary.vue'
import { implementationVersions, workflowExecutionHeadline } from '../services/scientificValidationService.js'
import { summarizeWorkflowForBeginners } from '../services/beginnerExperienceService.js'
import { readUser } from '../services/authStorage.js'
import { createCopilotResultDraft, savePendingCopilotDraft } from '../services/assistantCopilotContext.js'

const route=useRoute();const router=useRouter();const loading=ref(false);const result=ref(null);const loadError=ref(null)
const routing=computed(()=>normalizeMoleculeRoutingResult(result.value))
const versions=computed(()=>implementationVersions(result.value || {}))
const executionLabel=computed(()=>moleculeWorkflowExecutionMeta(result.value?.status).label)
const legacyHeadline=computed(()=>workflowExecutionHeadline(result.value?.status,result.value?.validation_status))
const validationTitle=computed(()=>legacyHeadline.value.title)
const validationText=computed(()=>legacyHeadline.value.message)
const validationClass=computed(()=>result.value?.status==='completed'?'unknown':result.value?.status==='failed'?'review':'unknown')
const beginnerSummary=computed(()=>summarizeWorkflowForBeginners(result.value || {}))
const optimizerStatus=computed(()=>{const d=result.value?.vqe?.optimizer_diagnostics;if(!d)return '—';return `${d.scipy_success?'已正常终止':'未正常终止'}${d.scipy_status===null||d.scipy_status===undefined?'':` · ${d.scipy_status}`}`})
const recentEnergyChanges=computed(()=>{const changes=result.value?.vqe?.optimizer_diagnostics?.recent_energy_changes_hartree;return Array.isArray(changes)&&changes.length?changes.map(x=>number(x,10)).join(' · '):'—'})
const historyDots=computed(()=>{const history=result.value?.vqe?.iteration_history||[];if(!history.length)return[];const energies=history.map(item=>Number(item.energy_hartree));const min=Math.min(...energies),max=Math.max(...energies),range=max-min||1;return history.map((item,index)=>({iteration:item.iteration,energy:item.energy_hartree,x:40+(history.length===1?330:index*660/(history.length-1)),y:25+(max-Number(item.energy_hartree))*195/range}))})
const historyPoints=computed(()=>historyDots.value.map(point=>`${point.x},${point.y}`).join(' '))
const value=input=>input===null||input===undefined||input===''?'—':String(input)
const number=(input,digits=8)=>{const n=Number(input);return Number.isFinite(n)?n.toFixed(digits):'—'}
const energy=input=>number(input,10)
const duration=input=>{const n=Number(input);if(!Number.isFinite(n))return '—';return n<1000?`${Math.round(n)} ms`:`${(n/1000).toFixed(2)} s`}
const qubits=(items,prefix='q')=>Array.isArray(items)&&items.length?items.map(item=>`${prefix}${item}`).join(' · '):'—'
const path=items=>Array.isArray(items)&&items.length?items.map(item=>`q${item}`).join(' → '):'—'
const swapPath=items=>Array.isArray(items)&&items.length?items.map(pair=>`q${pair[0]} ↔ q${pair[1]}`).join(' · '):'无'
const layout=mapping=>mapping&&Object.keys(mapping).length?Object.entries(mapping).map(([logical,physical])=>`q${logical}→p${physical}`).join(' · '):'—'
function askCopilotAboutResult(){const draft=createCopilotResultDraft('molecule_workflow',result.value?.workflow_id);if(draft&&savePendingCopilotDraft(readUser(),draft))router.push('/app/copilot')}
async function loadWorkflow(){loading.value=true;loadError.value=null;try{const data=await getMoleculeWorkflow(route.params.workflowId);result.value=data;saveRecentMoleculeWorkflow(data)}catch(error){loadError.value=normalizeMoleculeWorkflowError(error)}finally{loading.value=false}}
watch(()=>route.params.workflowId,loadWorkflow);onMounted(loadWorkflow)
</script>

<style scoped>
.molecule-result-page{display:grid;gap:18px;min-width:0}.result-loading{min-height:360px;padding:40px;border:1px solid var(--lz-line);background:#fff}.result-head{min-width:0;min-height:0;padding:clamp(24px,3vw,38px);border:1px solid var(--lz-line);display:flex;align-items:flex-end;justify-content:space-between;gap:24px;background:#f9faf7}.result-head>div{min-width:0}.page-kicker,.section-index{color:var(--lz-accent-deep);font:700 .66rem var(--lz-mono);letter-spacing:.12em}.result-head h2{margin:10px 0 8px;font-size:clamp(2.2rem,5vw,4rem);line-height:.95;letter-spacing:-.065em}.result-head p{margin:0;color:var(--lz-muted);font-size:.72rem;overflow-wrap:anywhere}.result-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.validation-summary{padding:22px 24px;border:1px solid;display:flex;align-items:center;justify-content:space-between;gap:30px}.validation-summary.passed{border-color:#91ad77;background:#eaf0e4}.validation-summary.review{border-color:#d5ba6a;background:#f5edd4}.validation-summary.unknown{border-color:var(--lz-line);background:#f2f4ef}.validation-summary h3{margin:8px 0;font-size:1.35rem}.validation-summary p{margin:0;color:var(--lz-muted);font-size:.8rem}.status-pair{display:grid;grid-template-columns:auto auto;gap:8px 18px;align-items:center}.status-pair span{color:var(--lz-muted);font-size:.7rem}.status-pair strong{font:700 .72rem var(--lz-mono)}.result-key-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;border:1px solid var(--lz-line);background:var(--lz-line)}.result-key-metrics article{min-height:116px;padding:18px;background:#fff;display:grid;align-content:space-between}.result-key-metrics span,.result-key-metrics small{color:var(--lz-muted);font-size:.71rem}.result-key-metrics strong{font:700 .98rem var(--lz-mono);overflow-wrap:anywhere}.workflow-evidence{border:1px solid var(--lz-line);background:#fff}.workflow-evidence>summary{min-height:66px;padding:17px 20px;display:flex;align-items:center;justify-content:space-between;gap:14px;cursor:pointer}.workflow-evidence>summary span{font-weight:700}.workflow-evidence>summary small{color:var(--lz-muted);font-size:.74rem}.workflow-evidence[open]>summary{border-bottom:1px solid var(--lz-line)}.evidence-body{padding:18px;display:grid;gap:18px;min-width:0}.result-panel{min-width:0;padding:26px;border:1px solid var(--lz-line);background:#fff}.section-head{margin-bottom:22px;display:flex;align-items:end;justify-content:space-between;gap:20px}.section-head h3{margin:8px 0 0;font-size:1.35rem;letter-spacing:-.03em}.section-head>span{color:var(--lz-muted);font-size:.72rem}.actual-stages{padding:0;display:grid;grid-template-columns:repeat(3,1fr);list-style:none}.actual-stages li{min-height:88px;padding:16px;border:1px solid var(--lz-line-soft);display:grid;grid-template-columns:auto 1fr;gap:8px 13px}.actual-stages li>span{color:var(--lz-accent);font:700 .68rem var(--lz-mono)}.actual-stages small{grid-column:2;color:var(--lz-muted)}.molecule-summary,.metrics-grid,.routing-cost{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--lz-line)}.molecule-summary article,.metrics-grid article,.routing-cost article{min-height:110px;padding:18px;background:#f7f8f5;display:grid;align-content:space-between}.molecule-summary span,.metrics-grid span,.routing-cost span{color:var(--lz-muted);font-size:.7rem}.molecule-summary strong,.metrics-grid strong,.routing-cost strong{font:700 1rem var(--lz-mono);overflow-wrap:anywhere}.metrics-grid small{color:var(--lz-muted)}.table-grid{min-width:0;margin-top:20px;border:1px solid var(--lz-line);overflow-x:auto}.table-grid>div{min-width:580px;min-height:42px;padding:7px 14px;border-bottom:1px solid var(--lz-line-soft);display:grid;grid-template-columns:50px 1fr repeat(3,1fr);align-items:center}.table-grid .table-head{background:#f3f5f1;color:var(--lz-muted);font-size:.68rem}.orbital-list,.topology-edges,.physical-couplings{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px}.orbital-list span,.topology-edges span,.physical-couplings span{padding:9px 12px;border:1px solid var(--lz-line);background:#f5f6f3;font:600 .7rem var(--lz-mono)}.orbital-list b{margin-right:12px;color:var(--lz-accent)}.pauli-table{overflow-x:auto}.pauli-table>div{min-width:360px;min-height:42px;padding:8px 14px;border-bottom:1px solid var(--lz-line-soft);display:grid;grid-template-columns:1fr 1fr}.pauli-table code{color:var(--lz-accent-deep)}.optimizer-banner{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--lz-line)}.optimizer-banner>div{min-height:100px;padding:18px;background:#f5f6f3;display:grid;align-content:space-between}.optimizer-banner span{color:var(--lz-muted);font-size:.68rem}.optimizer-banner strong{font:700 .76rem var(--lz-mono);overflow-wrap:anywhere}.vqe-layout{margin-top:20px;display:grid;grid-template-columns:1.2fr .8fr;gap:18px}.energy-history,.qasm-block{min-width:0;padding:20px;border:1px solid var(--lz-line)}.energy-history h4,.qasm-block h4{margin:0 0 16px}.energy-history svg{width:100%;height:270px;background:#f5f6f3}.energy-history line{stroke:#aeb8af;stroke-width:1}.energy-history polyline{fill:none;stroke:var(--lz-accent);stroke-width:3}.energy-history circle{fill:var(--lz-text)}.qasm-block pre{max-height:270px;margin:0;padding:16px;overflow:auto;background:#18231e;color:#d7e9bf;font:500 .68rem/1.6 var(--lz-mono)}.partition-grid,.virtual-mapping{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.partition-grid article,.virtual-mapping article{min-height:110px;padding:18px;border:1px solid var(--lz-line);display:grid;align-content:space-between}.partition-grid span,.virtual-mapping span{color:var(--lz-accent);font:700 .67rem var(--lz-mono)}.partition-grid strong,.virtual-mapping strong{font:700 .88rem var(--lz-mono)}.partition-grid small,.virtual-mapping small{color:var(--lz-muted)}.scope-note{margin:-8px 0 22px;padding-left:12px;border-left:3px solid var(--lz-accent);color:var(--lz-muted);font-size:.78rem;line-height:1.7}.chip-result-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.chip-result{min-width:0;padding:20px;border:1px solid var(--lz-line);background:#f7f8f5}.chip-result header{display:flex;justify-content:space-between;gap:14px}.chip-result header span{color:var(--lz-accent);font:700 .65rem var(--lz-mono)}.chip-result h4{margin:6px 0 0;font-size:1.15rem}.chip-result header>strong{color:var(--lz-muted);font:700 .68rem var(--lz-mono)}.chip-result h5{margin:22px 0 10px}.layout-comparison{display:grid;grid-template-columns:1fr auto 1fr;gap:10px;align-items:center}.layout-comparison>div{min-width:0;padding:12px;background:#fff}.layout-comparison span{display:block;margin-bottom:7px;color:var(--lz-muted);font-size:.66rem}.layout-comparison code{font-size:.68rem;line-height:1.6;overflow-wrap:anywhere}.routing-cost{grid-template-columns:repeat(3,1fr)}.swap-panel>h4{margin:24px 0 12px}.evidence-list{display:grid;gap:10px}.evidence-list article{min-width:0;padding:17px;border:1px solid var(--lz-line)}.evidence-list header{display:flex;justify-content:space-between}.evidence-list header span{padding:4px 8px;background:#dfe5dc;font-size:.65rem}.evidence-list header span.routed{background:#f0e0ad;color:#775d12}.evidence-list article>div{margin-top:14px;display:grid;grid-template-columns:auto 1fr auto 1fr auto 1fr;gap:8px;align-items:center}.evidence-list article>div span{color:var(--lz-muted);font-size:.68rem}.evidence-list code{font-size:.68rem;overflow-wrap:anywhere}.plan-consumption{margin:22px 0;padding:18px;border:1px solid #c9826c;display:flex;gap:14px;align-items:center;background:#f8e8e2}.plan-consumption.consumed{border-color:#82a866;background:#e8f0e2}.plan-consumption>span{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:#17201d;color:#fff}.plan-consumption strong{font-size:.86rem}.plan-consumption p{margin:5px 0 0;color:var(--lz-muted);font:600 .66rem var(--lz-mono)}.plan-table{overflow-x:auto}.plan-table>div{min-width:520px;min-height:44px;padding:8px;border-bottom:1px solid var(--lz-line-soft);display:grid;grid-template-columns:55px 80px 100px 1fr 100px;gap:8px;align-items:center;font-size:.7rem}.plan-table b{color:var(--lz-accent-deep)}.communication-events{display:grid;gap:9px}.communication-events article{min-width:0;padding:16px;border-left:3px solid var(--lz-accent);display:grid;grid-template-columns:90px 1fr auto;gap:14px;background:#f5f6f3;font-size:.74rem}.communication-events article span,.communication-events article small{color:var(--lz-muted)}.energy-comparison{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--lz-line)}.energy-comparison article{min-height:150px;padding:22px;background:#f5f6f3;display:grid;align-content:space-between}.energy-comparison span{color:var(--lz-muted);font-size:.72rem}.energy-comparison strong{font:700 1.25rem var(--lz-mono)}.energy-comparison small{color:var(--lz-muted)}.issue-list{display:grid;gap:9px}.issue-list article{padding:16px;border-left:3px solid #d1ad43;background:#f5eed9;display:grid;grid-template-columns:160px 1fr auto;gap:10px}.issue-list p{margin:0}.issue-list small{color:#756725}.mono{font-family:var(--lz-mono)}@media(max-width:1100px){.result-key-metrics,.molecule-summary,.metrics-grid{grid-template-columns:repeat(2,1fr)}.optimizer-banner{grid-template-columns:repeat(2,1fr)}.vqe-layout{grid-template-columns:1fr}.chip-result-grid{grid-template-columns:1fr}}@media(max-width:760px){.result-head,.validation-summary,.section-head{align-items:flex-start;flex-direction:column}.result-key-metrics,.actual-stages,.partition-grid,.virtual-mapping,.routing-cost,.energy-comparison{grid-template-columns:1fr}.molecule-summary,.metrics-grid,.optimizer-banner{grid-template-columns:1fr}.result-panel,.evidence-body{padding:16px}.workflow-evidence>summary{align-items:flex-start;flex-direction:column}.evidence-list article>div{grid-template-columns:1fr}.plan-table>div{grid-template-columns:40px 60px 1fr}.plan-table>div span:nth-of-type(2),.plan-table b{grid-column:3}.communication-events article,.issue-list article{grid-template-columns:1fr}.layout-comparison{grid-template-columns:1fr}}
.molecule-result-page{gap:22px}.result-head,.result-key-metrics,.workflow-evidence,.result-panel{border-radius:var(--lz-radius);box-shadow:var(--lz-shadow)}.result-head{background:var(--lz-bg-soft)}.result-head h2{line-height:var(--lz-title-leading);letter-spacing:-.045em}.validation-summary{border-radius:var(--lz-radius);box-shadow:var(--lz-shadow)}.validation-summary.passed{border-color:#b8d2c5;background:var(--lz-accent-soft)}.validation-summary.review{border-color:#ebcf94;background:#fff6e5}.validation-summary.unknown{background:var(--lz-bg-soft)}.result-key-metrics,.workflow-evidence{overflow:hidden}.workflow-evidence>summary{padding:19px 22px}.result-panel{padding:var(--lz-space-panel)}.molecule-summary article,.metrics-grid article,.routing-cost article,.optimizer-banner>div,.chip-result{background:var(--lz-bg-soft)}.qasm-block pre{background:#253630;color:#dfe9e3}.scope-note{border-color:var(--lz-accent);line-height:var(--lz-body-leading)}
</style>
