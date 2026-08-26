<template>
  <div class="study-create-page">
    <header class="page-head">
      <div><span>MOLECULAR STUDY / DEPLOYMENT EVALUATION</span><h2>比较哪种连接方案更适合这次分子计算</h2><p>先固定一个分子问题，再并列评估不同分区与连接方案的部署代价。不会重复创建多次分子计算。</p><p class="simulation-note">逻辑虚拟 QPU 模拟 · is_real_qpu=false · 非真实 QPU</p></div>
      <div class="contract-tags"><el-tag>logical_virtual_qpu</el-tag><el-tag>is_real_qpu=false</el-tag><el-tag type="warning">非真实 QPU</el-tag><el-button data-testid="copilot-help-settings" text @click="askCopilotAboutSettings">帮我理解这些设置</el-button></div>
    </header>

    <div class="step-rail" aria-label="部署评估步骤"><span v-for="(step,index) in steps" :key="step" :class="{ active: activeStep === index, done: activeStep > index }"><b>{{ String(index + 1).padStart(2, '0') }}</b>{{ step }}</span></div>

    <main class="builder">
      <section v-show="activeStep === 0" class="step-panel">
        <BeginnerSettingsGuide compact title="推荐路径：先确认分子" description="默认架构集合已经准备好。只需确认分子与几何；计算参数会由所有比较方案共用。" />
        <header><span>STEP 01</span><h3>这次比较要回答什么？</h3><p>同一个分子在不同分区和连接方案下，需要付出多少路由与通信代价。</p></header>
        <div class="preset-row"><span>预置分子</span><el-button v-for="preset in ['H2', 'LiH', 'H2O']" :key="preset" :type="form.moleculeName === preset ? 'primary' : 'default'" @click="applyPreset(preset)">{{ preset }}</el-button></div>
        <div class="atom-editor"><div class="atom-row atom-head"><span>#</span><span>元素</span><span>X / Å</span><span>Y / Å</span><span>Z / Å</span><i></i></div><div v-for="(atom,index) in form.geometry" :key="index" class="atom-row"><b>{{ String(index + 1).padStart(2, '0') }}</b><el-input v-model="atom.element"/><el-input-number v-for="axis in 3" :key="axis" v-model="atom.coordinates[axis - 1]" :precision="6" :step="0.1"/><el-button text type="danger" :disabled="form.geometry.length === 1" @click="form.geometry.splice(index, 1)">删除</el-button></div></div>
        <el-button class="add-atom" @click="form.geometry.push({ element: 'H', coordinates: [0, 0, 0] })">添加原子</el-button>
        <div class="form-grid one"><el-form-item label="分子名称"><el-input v-model="form.moleculeName"/></el-form-item></div>
        <details class="advanced-settings"><summary>高级设置：电荷、基组、活性空间与 VQE 预算</summary><div class="form-grid four"><el-form-item label="电荷"><el-input-number v-model="form.charge"/></el-form-item><el-form-item label="自旋多重度"><el-input-number v-model="form.spinMultiplicity" :min="1"/></el-form-item><el-form-item label="基组"><el-input v-model="form.basisSet"/></el-form-item><el-form-item label="活性空间轨道数"><el-input-number v-model="form.activeSpaceOrbitals" :min="1" :max="6"/></el-form-item><el-form-item label="Pauli 截断阈值"><el-input-number v-model="form.pauliCoefficientCutoff" :precision="8" :step="0.000001"/></el-form-item><el-form-item label="VQE 层数"><el-input-number v-model="form.ansatzLayers" :min="1" :max="4"/></el-form-item><el-form-item label="VQE 迭代预算"><el-input-number v-model="form.maxIterations" :min="1" :max="500"/></el-form-item></div></details>
      </section>

      <section v-show="activeStep === 1" class="step-panel">
        <BeginnerSettingsGuide compact title="推荐架构集合已生效" description="三种默认方案覆盖不同路由条件；首次使用无需编辑，直接继续即可。" />
        <header class="arch-heading"><div><span>STEP 02</span><h3>比较方案</h3><p>默认三种架构已可使用。只有需要进行专业设计时，才展开分区、拓扑与路由配置。</p></div><el-button type="primary" @click="addArchitecture">添加架构</el-button></header>
        <details class="advanced-settings"><summary>高级设置：分区、拓扑、耦合与路由</summary><article v-for="(architecture, architectureIndex) in form.architectures" :key="architectureIndex" class="architecture-editor">
          <header><div><span>ARCHITECTURE {{ String(architectureIndex + 1).padStart(2, '0') }}</span><h4>{{ architecture.architectureId }}</h4></div><div><el-button size="small" @click="copyArchitecture(architecture, architectureIndex)">复制</el-button><el-button size="small" type="danger" :disabled="form.architectures.length <= 3" @click="form.architectures.splice(architectureIndex, 1)">删除</el-button></div></header>
          <div class="form-grid two"><el-form-item label="架构名称 / ID"><el-input v-model="architecture.architectureId"/></el-form-item><el-form-item label="分区数量"><el-select v-model="architecture.partition.partitionCount" @change="syncArchitecture(architecture)"><el-option :value="2" label="2 个虚拟 QPU"/><el-option :value="3" label="3 个虚拟 QPU"/></el-select></el-form-item></div>
          <div class="topology-block"><strong>INTER-QPU TOPOLOGY / 芯片之间的连接</strong><p>只表示虚拟 QPU 间通信，不能代替单颗芯片内部物理耦合。</p><div v-for="(edge,index) in architecture.partition.interQpuTopology" :key="index" class="edge-row"><span>边 {{ index + 1 }}</span><el-input-number v-model="edge.source" :min="0" :max="architecture.partition.partitionCount - 1"/><b>—</b><el-input-number v-model="edge.target" :min="0" :max="architecture.partition.partitionCount - 1"/><el-button text type="danger" :disabled="architecture.partition.interQpuTopology.length <= 1" @click="architecture.partition.interQpuTopology.splice(index, 1)">删除</el-button></div><el-button size="small" @click="architecture.partition.interQpuTopology.push({ source: 0, target: 1 })">添加芯片间边</el-button></div>
          <div class="chip-grid"><article v-for="(chip, chipIndex) in architecture.partition.virtualQpus" :key="chipIndex" class="chip-editor"><header><div><span>VIRTUAL QPU {{ String(chipIndex + 1).padStart(2, '0') }}</span><h5>{{ chip.virtualQpuId }}</h5></div><el-form-item label="物理 Qubits"><el-input-number v-model="chip.physicalQubitCount" :min="1" :max="12" @change="trimChipEdges(chip)"/></el-form-item></header><el-form-item label="虚拟 QPU ID"><el-input v-model="chip.virtualQpuId"/></el-form-item><strong>PHYSICAL COUPLING MAP / 芯片内部连接</strong><div v-for="(edge,index) in chip.physicalCouplingMap" :key="index" class="edge-row"><span>耦合 {{ index + 1 }}</span><el-input-number v-model="edge.source" :min="0" :max="chip.physicalQubitCount - 1"/><b>—</b><el-input-number v-model="edge.target" :min="0" :max="chip.physicalQubitCount - 1"/><el-button text type="danger" @click="chip.physicalCouplingMap.splice(index, 1)">删除</el-button></div><el-button size="small" @click="chip.physicalCouplingMap.push({ source: 0, target: 1 })">添加物理耦合边</el-button></article></div>
          <div class="method-line"><span>分区策略 <b>{{ architecture.partition.partitionStrategy }}</b></span><span>初始布局 <b>{{ architecture.partition.initialLayout }}</b></span><span>路由方法 <b>{{ architecture.partition.routingMethod }}</b></span></div>
        </article></details>
      </section>

      <section v-show="activeStep === 2" class="step-panel">
        <header><span>STEP 03</span><h3>提交前确认</h3><p>将比较同一分子、{{ form.architectures.length }} 种架构和各自的路由代价；前端不会生成综合最优评分。</p></header>
        <div class="compare-grid"><article v-for="architecture in form.architectures" :key="architecture.architectureId"><span>{{ architecture.architectureId }}</span><h4>{{ architecture.architectureId }}</h4><dl><div><dt>虚拟 QPU</dt><dd>{{ architecture.partition.virtualQpus.length }}</dd></div><div><dt>分区间拓扑</dt><dd>{{ edgeText(architecture.partition.interQpuTopology) }}</dd></div><div><dt>各芯片物理容量</dt><dd>{{ architecture.partition.virtualQpus.map(chip => chip.physicalQubitCount).join(' / ') }}</dd></div><div><dt>芯片内耦合边</dt><dd>{{ architecture.partition.virtualQpus.map(chip => chip.physicalCouplingMap.length).join(' / ') }}</dd></div><div><dt>布局 / 路由</dt><dd>{{ architecture.partition.initialLayout }} / {{ architecture.partition.routingMethod }}</dd></div></dl></article></div>
      </section>

      <section v-show="activeStep === 3" class="step-panel">
        <header><span>STEP 04</span><h3>提交并查看比较进度</h3><p>提交后将创建一个 Study；后续只恢复和轮询该 Study，不会重复提交分子问题。</p></header>
        <div class="submit-summary"><article><span>分子问题</span><strong>{{ form.moleculeName }}</strong><p>{{ form.geometry.length }} atoms · {{ form.basisSet }} · VQE {{ form.ansatzLayers }} layers</p></article><article><span>部署架构</span><strong>{{ form.architectures.length }} 个</strong><p>{{ form.architectures.map(item => item.architectureId).join(' · ') }}</p></article><article><span>固定执行</span><strong>logical_virtual_qpu</strong><p>模拟器 · 非真实 QPU</p></article></div>
        <el-alert v-if="validationErrors.length" type="error" :closable="false" title="请修正以下字段"><ul><li v-for="error in validationErrors" :key="error">{{ error }}</li></ul></el-alert>
        <el-alert v-if="requestError" type="error" :closable="false"><template #title>{{ requestError.title }}</template><p>{{ requestError.message }}</p><p v-if="requestError.code" class="mono">{{ requestError.code }} · {{ requestError.stage || '—' }}</p><el-button v-if="requestError.status === 401" size="small" @click="goToLogin">重新登录</el-button></el-alert>
      </section>

      <footer class="actions"><el-button v-if="activeStep > 0" @click="activeStep--">上一步</el-button><span>步骤 {{ activeStep + 1 }} / 4</span><el-button v-if="activeStep < 3" type="primary" @click="nextStep">下一步</el-button><el-button v-else type="primary" :loading="submitting" :disabled="submitting" @click="submit">提交 Study</el-button></footer>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clonePreset } from '../services/moleculeWorkflowService.js'
import { clearAuthSession, readUser } from '../services/authStorage.js'
import { createCopilotSettingsDraft, savePendingCopilotDraft } from '../services/assistantCopilotContext.js'
import { cloneStudyArchitecture, createArchitecture, createMolecularStudyForm, buildMolecularStudyPayload, normalizeMolecularStudyError, submitMolecularStudy, validateMolecularStudyForm } from '../services/molecularStudyService.js'
import { saveRecentMolecularStudy } from '../services/molecularStudyStorage.js'
import BeginnerSettingsGuide from '../components/BeginnerSettingsGuide.vue'

const router = useRouter()
const steps = ['分子问题', '架构方案', '对比确认', '提交执行']
const activeStep = ref(0)
const form = reactive(createMolecularStudyForm('H2'))
const validationErrors = ref([])
const requestError = ref(null)
const submitting = ref(false)

function applyPreset(name) {
  const preset = clonePreset(name)
  form.moleculeName = preset.moleculeName
  form.geometry = preset.geometry
  form.charge = preset.charge
  form.spinMultiplicity = preset.spinMultiplicity
  form.basisSet = preset.basisSet
}

function syncArchitecture(architecture) {
  const count = Number(architecture.partition.partitionCount)
  architecture.partition.interQpuTopology = Array.from({ length: count - 1 }, (_, index) => ({ source: index, target: index + 1 }))
  architecture.partition.virtualQpus = Array.from({ length: count }, (_, index) => architecture.partition.virtualQpus[index] || {
    virtualQpuId: `${architecture.architectureId}-QPU-${index + 1}`,
    physicalQubitCount: 4,
    physicalCouplingMap: [{ source: 0, target: 1 }, { source: 1, target: 2 }, { source: 2, target: 3 }],
  })
}

function trimChipEdges(chip) {
  chip.physicalCouplingMap = chip.physicalCouplingMap.filter(edge => edge.source < chip.physicalQubitCount && edge.target < chip.physicalQubitCount)
}

function addArchitecture() { form.architectures.push(createArchitecture(form.architectures.length + 1)) }
function copyArchitecture(architecture, index) { form.architectures.push(cloneStudyArchitecture(architecture, `${index + 1}-${form.architectures.length + 1}`)) }
function edgeText(edges) { return edges?.length ? edges.map(edge => `${edge.source}—${edge.target}`).join(', ') : '—' }
function goToLogin() { router.push(`/auth?tab=login&redirect=${encodeURIComponent('/app/molecular-studies/new')}`) }
function askCopilotAboutSettings() { if (savePendingCopilotDraft(readUser(), createCopilotSettingsDraft('molecular_study'))) router.push('/app/copilot') }
function nextStep() { validationErrors.value = validateMolecularStudyForm(form); if (!validationErrors.value.length || activeStep.value < 3) activeStep.value += 1 }

async function submit() {
  validationErrors.value = validateMolecularStudyForm(form)
  if (validationErrors.value.length) return
  submitting.value = true
  requestError.value = null
  try {
    const accepted = await submitMolecularStudy(buildMolecularStudyPayload(form))
    saveRecentMolecularStudy(accepted)
    await router.push(`/app/molecular-studies/${encodeURIComponent(accepted.study_id)}`)
  } catch (error) {
    requestError.value = normalizeMolecularStudyError(error)
    if (requestError.value.status === 401) clearAuthSession()
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.study-create-page{display:grid;gap:22px}.page-head{min-height:190px;padding:34px;border:1px solid #c7cdc5;display:flex;align-items:flex-end;justify-content:space-between;gap:24px;background:#e7eae3}.page-head>div:first-child{max-width:790px}.page-head span,.step-panel>header>span,.architecture-editor>header span{color:#6e7b72;font:700 .66rem ui-monospace,monospace;letter-spacing:.12em}.page-head h2{margin:12px 0 9px;font-size:clamp(2.1rem,4.5vw,4.5rem);line-height:.92;letter-spacing:-.065em}.page-head p,.step-panel>header p{margin:0;color:#66726a;line-height:1.6;font-size:.82rem}.contract-tags{display:flex;flex-wrap:wrap;gap:8px}.advanced-settings{border:1px solid #d3dbcf;background:#fbfcfa}.advanced-settings>summary{padding:14px 16px;color:#42662f;cursor:pointer;font-weight:700;font-size:.82rem}.advanced-settings[open]>summary{border-bottom:1px solid #dce4d7}.advanced-settings> :not(summary){margin-left:18px;margin-right:18px}.step-rail{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #ccd2ca;background:#fff}.step-rail span{min-height:62px;padding:14px 18px;border-right:1px solid #dce1da;display:flex;align-items:center;gap:12px;color:#758178;font-size:.76rem}.step-rail span:last-child{border-right:0}.step-rail b{color:#93a19a;font:700 .68rem ui-monospace,monospace}.step-rail .active{background:#17201d;color:#fff}.step-rail .active b,.step-rail .done b{color:#b5f04c}.step-rail .done{color:#2e5134}.builder{border:1px solid #cbd1c9;background:#fff}.step-panel{padding:34px}.step-panel>header{margin-bottom:28px}.step-panel h3{margin:7px 0;font-size:1.75rem;letter-spacing:-.035em}.preset-row{margin-bottom:18px;display:flex;align-items:center;flex-wrap:wrap;gap:9px}.preset-row span{margin-right:10px;color:#76817a;font-size:.75rem}.atom-editor{border:1px solid #d8ddd6;overflow:auto}.atom-row{min-width:720px;min-height:55px;padding:7px 12px;border-bottom:1px solid #e3e6e0;display:grid;grid-template-columns:36px 105px repeat(3,minmax(110px,1fr)) 58px;gap:10px;align-items:center}.atom-row:last-child{border-bottom:0}.atom-head{min-height:38px;background:#f2f4f0;color:#728078;font-size:.68rem}.atom-row b{color:#70954b;font:700 .68rem ui-monospace,monospace}.add-atom{margin:13px 0 25px}.form-grid{display:grid;gap:16px}.form-grid.four{grid-template-columns:repeat(4,1fr)}.form-grid.three{grid-template-columns:repeat(3,1fr)}.form-grid :deep(.el-select),.form-grid :deep(.el-input-number){width:100%}.arch-heading,.architecture-editor>header,.chip-editor>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.architecture-editor{margin:22px 0;padding:24px;border:1px solid #cdd3cb;background:#f7f8f5}.architecture-editor h4{margin:6px 0 0;font-size:1.15rem}.topology-block,.chip-editor{margin-top:20px;padding:20px;border:1px solid #d6dbd4;background:#fff}.topology-block>strong,.chip-editor>strong{font:700 .69rem ui-monospace,monospace;color:#577b39;letter-spacing:.04em}.topology-block p{margin:7px 0 15px;color:#738078;font-size:.75rem}.edge-row{min-height:44px;margin:7px 0;padding:5px 9px;display:grid;grid-template-columns:1fr 110px 20px 110px 52px;gap:8px;align-items:center;background:#f3f5f1;font-size:.72rem}.chip-grid,.compare-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.chip-editor header h5{margin:5px 0;font-size:1rem}.chip-editor header span{color:#739b50;font:700 .65rem ui-monospace,monospace}.chip-editor :deep(.el-form-item){margin:16px 0}.chip-editor>header :deep(.el-form-item){margin:0;max-width:135px}.method-line{margin-top:14px;display:flex;gap:15px;flex-wrap:wrap;color:#66736b;font-size:.72rem}.method-line b{font-family:ui-monospace,monospace}.compare-grid article{min-height:280px;padding:24px;border:1px solid #cfd5cd}.compare-grid article>span{color:#759b52;font:700 .66rem ui-monospace,monospace}.compare-grid h4{margin:9px 0 22px;font-size:1.2rem}.compare-grid dl{margin:0;display:grid;gap:11px}.compare-grid dl div{display:grid;grid-template-columns:135px 1fr;gap:10px;border-top:1px solid #e0e4df;padding-top:10px}.compare-grid dt{color:#748079;font-size:.7rem}.compare-grid dd{margin:0;font:600 .7rem/1.5 ui-monospace,monospace;overflow-wrap:anywhere}.submit-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#cfd5cd}.submit-summary article{min-height:155px;padding:23px;background:#f4f6f2;display:grid;align-content:space-between}.submit-summary span{color:#738078;font-size:.68rem}.submit-summary strong{font:700 .95rem ui-monospace,monospace;overflow-wrap:anywhere}.submit-summary p{margin:0;color:#68746d;font-size:.73rem}.actions{min-height:78px;padding:14px 30px;border-top:1px solid #dfe3dd;display:flex;align-items:center;justify-content:flex-end;gap:12px}.actions>span{margin-right:auto;color:#768178;font:700 .68rem ui-monospace,monospace}.mono{font-family:ui-monospace,monospace}@media(max-width:1050px){.form-grid.four{grid-template-columns:repeat(2,1fr)}}@media(max-width:780px){.page-head,.arch-heading{align-items:flex-start;flex-direction:column}.step-rail{grid-template-columns:repeat(2,1fr)}.step-rail span:nth-child(2){border-right:0}.chip-grid,.compare-grid,.submit-summary,.form-grid.four,.form-grid.three{grid-template-columns:1fr}.step-panel{padding:22px}.edge-row{grid-template-columns:1fr 70px 15px 70px 45px}.actions{padding:14px 20px}}
.form-grid.one{grid-template-columns:minmax(0,360px)}
.form-grid.two{grid-template-columns:repeat(2,1fr)}
.chip-editor>header :deep(.el-input-number){width:135px}
@media(max-width:780px){.form-grid.two{grid-template-columns:1fr}}
.study-create-page,.page-head,.builder,.step-panel,.atom-editor{min-width:0;max-width:100%;box-sizing:border-box}.study-create-page{width:100%}.page-head>div:first-child{min-width:0}.atom-editor{overflow:auto}.simulation-note{margin-top:12px!important;color:#42662f!important;font:700 .7rem ui-monospace,monospace!important}.contract-tags :deep(.el-tag){border-color:#b7cbaa;background:#edf4e8;color:#385a2c;font-weight:700}.contract-tags :deep(.el-tag--warning){border-color:#e4c476;background:#fff5dc;color:#895d10}
/* P1.6A visual refinement */
.study-create-page{gap:22px}.page-head,.builder,.panel{border-radius:var(--lz-radius);box-shadow:var(--lz-shadow)}.page-head{background:var(--lz-bg-soft)}.page-head h2{line-height:var(--lz-title-leading);letter-spacing:-.045em}.page-head p,.panel header p{line-height:var(--lz-body-leading)}.step-rail .active{background:var(--lz-accent);color:#e5f2ea}.panel{padding:var(--lz-space-panel)}.advanced-settings{border-radius:var(--lz-radius-small);background:var(--lz-bg-soft)}.architecture,.topology-editors>section,.chip-editor{border-color:var(--lz-line);background:var(--lz-bg-soft)}
</style>
