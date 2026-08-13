<template>
  <div class="bond-create-page">
    <header class="page-head">
      <div>
        <span>LIH / DISCRETE BOND SCAN</span>
        <h2>LiH 键长扫描与部署评估</h2>
        <p>固定距离的离散扫描；最低点仅是近似键长候选，不是精确平衡键长。</p>
      </div>
      <div class="fixed-tags"><el-tag>模拟器</el-tag><el-tag type="warning">非真实 QPU</el-tag></div>
    </header>

    <section v-if="loadingCapabilities" class="loading">正在读取扫描能力…</section>
    <el-alert v-else-if="capabilityError" type="error" :closable="false" :title="capabilityError" />

    <main v-else class="builder">
      <div class="step-rail"><span v-for="(label, index) in steps" :key="label" :class="{ active: step === index }">{{ String(index + 1).padStart(2, '0') }} {{ label }}</span></div>

      <section v-show="step === 0" class="panel">
        <header><span>STEP 01</span><h3>扫描范围</h3></header>
        <div class="form-grid">
          <el-form-item label="分子"><el-input model-value="LiH" disabled /></el-form-item>
          <el-form-item label="起始距离 / Å"><el-input-number v-model="form.startDistance" :min="distanceMin" :max="distanceMax" :step="0.1" /></el-form-item>
          <el-form-item label="终止距离 / Å"><el-input-number v-model="form.endDistance" :min="distanceMin" :max="distanceMax" :step="0.1" /></el-form-item>
          <el-form-item label="扫描点数"><el-input-number v-model="form.pointCount" :min="capabilities.minimum_point_count" :max="capabilities.maximum_point_count" /></el-form-item>
        </div>
        <div class="distance-preview"><strong>按后端规则预览</strong><span v-for="distance in distances" :key="distance">{{ distance.toFixed(3) }} Å</span></div>
      </section>

      <section v-show="step === 1" class="panel">
        <header><span>STEP 02</span><h3>计算参数</h3></header>
        <div class="form-grid">
          <el-form-item label="电荷"><el-input-number v-model="form.charge" /></el-form-item>
          <el-form-item label="自旋多重度"><el-input-number v-model="form.spinMultiplicity" :min="1" /></el-form-item>
          <el-form-item label="基组"><el-select v-model="form.basisSet"><el-option v-for="basis in capabilities.supported_basis_sets" :key="basis" :value="basis" /></el-select></el-form-item>
          <el-form-item label="活性空间轨道数"><el-input-number v-model="form.activeSpaceOrbitals" :min="capabilities.active_space_orbital_range?.[0]" :max="capabilities.active_space_orbital_range?.[1]" /></el-form-item>
          <el-form-item label="Pauli 截断阈值"><el-input-number v-model="form.pauliCoefficientCutoff" :precision="8" :step="0.000001" /></el-form-item>
          <el-form-item label="VQE 层数"><el-input-number v-model="form.ansatzLayers" :min="1" :max="4" /></el-form-item>
          <el-form-item label="最大迭代数"><el-input-number v-model="form.maxIterations" :min="1" :max="500" /></el-form-item>
        </div>
      </section>

      <section v-show="step === 2" class="panel">
        <header class="arch-head"><div><span>STEP 03</span><h3>部署架构</h3><p>同一 Scan 只计算一次 PySCF、Hamiltonian 与 VQE。芯片间连接和芯片内耦合图是不同的对象。</p></div><el-button type="primary" @click="copyArchitecture">复制架构</el-button></header>
        <article v-for="(architecture, architectureIndex) in form.architectures" :key="architectureIndex" class="architecture">
          <header><strong>ARCH {{ String(architectureIndex + 1).padStart(2, '0') }}</strong><el-button text type="danger" :disabled="form.architectures.length <= minArchitectures" @click="form.architectures.splice(architectureIndex, 1)">删除</el-button></header>
          <div class="form-grid architecture-basics">
            <el-form-item label="架构 ID"><el-input v-model="architecture.architectureId" /></el-form-item>
            <el-form-item label="分区 / 虚拟 QPU 数"><el-input-number v-model="architecture.partition.partitionCount" :min="2" :max="3" @change="syncPartition(architecture)" /></el-form-item>
            <el-form-item label="分区策略"><el-select v-model="architecture.partition.partitionStrategy"><el-option value="sequential_greedy" label="sequential_greedy" /></el-select></el-form-item>
            <el-form-item label="路由方法"><el-select v-model="architecture.partition.routingMethod"><el-option value="shortest_path_swap" label="shortest_path_swap" /></el-select></el-form-item>
          </div>
          <div class="topology-editors">
            <section><header><b>INTER-QPU TOPOLOGY</b><small>芯片之间的连接</small><el-button text size="small" @click="addInterEdge(architecture)">+ 边</el-button></header><div v-for="(edge, edgeIndex) in architecture.partition.interQpuTopology" :key="`inter-${edgeIndex}`" class="edge-row"><el-input-number v-model="edge.source" :min="0" :max="architecture.partition.partitionCount - 1" /><span>—</span><el-input-number v-model="edge.target" :min="0" :max="architecture.partition.partitionCount - 1" /><el-button text type="danger" :disabled="architecture.partition.interQpuTopology.length === 1" @click="architecture.partition.interQpuTopology.splice(edgeIndex, 1)">×</el-button></div></section>
            <section><header><b>INITIAL LAYOUT</b><small>logical-to-physical 初始布局</small></header><el-select v-model="architecture.partition.initialLayout"><el-option value="identity" label="identity" /></el-select></section>
          </div>
          <div class="chips">
            <section v-for="(chip, chipIndex) in architecture.partition.virtualQpus" :key="chipIndex" class="chip-editor">
              <header><b>VIRTUAL QPU {{ String(chipIndex + 1).padStart(2, '0') }}</b><small>芯片内部物理耦合图</small></header>
              <el-form-item label="虚拟 QPU ID"><el-input v-model="chip.virtualQpuId" /></el-form-item>
              <el-form-item label="物理 Qubit 数"><el-input-number v-model="chip.physicalQubitCount" :min="1" :max="12" @change="trimChipEdges(chip)" /></el-form-item>
              <div class="coupling-title"><b>PHYSICAL COUPLING MAP</b><el-button text size="small" @click="addChipEdge(chip)">+ 耦合边</el-button></div>
              <div v-if="!chip.physicalCouplingMap.length" class="empty-edge">单物理 Qubit 可不配置耦合边</div>
              <div v-for="(edge, edgeIndex) in chip.physicalCouplingMap" :key="`physical-${edgeIndex}`" class="edge-row"><el-input-number v-model="edge.source" :min="0" :max="chip.physicalQubitCount - 1" /><span>—</span><el-input-number v-model="edge.target" :min="0" :max="chip.physicalQubitCount - 1" /><el-button text type="danger" @click="chip.physicalCouplingMap.splice(edgeIndex, 1)">×</el-button></div>
            </section>
          </div>
        </article>
      </section>

      <section v-show="step === 3" class="panel">
        <header><span>STEP 04</span><h3>确认并提交</h3></header>
        <div class="summary"><p>{{ form.startDistance }}–{{ form.endDistance }} Å · {{ form.pointCount }} 个离散点 · {{ form.architectures.length }} 个部署架构</p><p>只对通过验证的 VQE 离散最低能量点执行一次部署评估。逻辑分布式模拟，非真实 QPU。</p></div>
        <el-alert v-if="errors.length" type="error" title="请修正以下字段" :closable="false"><ul><li v-for="item in errors" :key="item">{{ item }}</li></ul></el-alert>
        <el-alert v-if="requestError" type="error" :title="requestError.title" :closable="false"><p>{{ requestError.message }}</p><p v-if="requestError.scanId" class="mono">Scan ID：{{ requestError.scanId }}</p></el-alert>
      </section>

      <footer><el-button v-if="step" @click="step--">上一步</el-button><span>步骤 {{ step + 1 }} / 4</span><el-button v-if="step < 3" type="primary" @click="next">下一步</el-button><el-button v-else type="primary" :loading="submitting" :disabled="submitting" @click="submit">提交键长扫描</el-button></footer>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { cloneStudyArchitecture } from '../services/molecularStudyService.js'
import { buildBondScanPayload, createBondScanArchitectures, createBondScanForm, getMolecularBondScanCapabilities, normalizeMolecularBondScanError, previewBondDistances, submitMolecularBondScan, validateBondScanForm } from '../services/molecularBondScanService.js'
import { createIdempotencyKey } from '../services/moleculeWorkflowService.js'
import { saveRecentMolecularBondScan } from '../services/molecularBondScanStorage.js'

const router = useRouter()
const route = useRoute()
const step = ref(0)
const capabilities = ref(null)
const loadingCapabilities = ref(true)
const capabilityError = ref('')
const errors = ref([])
const requestError = ref(null)
const submitting = ref(false)
const form = reactive(createBondScanForm(createBondScanArchitectures()))
const steps = ['扫描范围', '计算参数', '部署架构', '确认提交']
const distanceMin = computed(() => capabilities.value?.distance_range_angstrom?.[0] ?? 0.5)
const distanceMax = computed(() => capabilities.value?.distance_range_angstrom?.[1] ?? 5)
const minArchitectures = computed(() => capabilities.value?.deployment_architecture_count_range?.[0] ?? 3)
const distances = computed(() => previewBondDistances(form.startDistance, form.endDistance, form.pointCount))

function linearEdges(count) { return Array.from({ length: Math.max(count - 1, 0) }, (_, index) => ({ source: index, target: index + 1 })) }
function syncPartition(architecture) {
  const partition = architecture.partition
  const count = Number(partition.partitionCount)
  partition.virtualQpus = partition.virtualQpus.slice(0, count)
  while (partition.virtualQpus.length < count) {
    const chipIndex = partition.virtualQpus.length
    partition.virtualQpus.push({ virtualQpuId: `${architecture.architectureId || 'architecture'}-QPU-${chipIndex + 1}`, physicalQubitCount: 2, physicalCouplingMap: linearEdges(2) })
  }
  partition.interQpuTopology = linearEdges(count)
}
function trimChipEdges(chip) { chip.physicalCouplingMap = chip.physicalCouplingMap.filter(edge => edge.source < chip.physicalQubitCount && edge.target < chip.physicalQubitCount) }
function addInterEdge(architecture) { architecture.partition.interQpuTopology.push({ source: 0, target: Math.min(1, architecture.partition.partitionCount - 1) }) }
function addChipEdge(chip) { chip.physicalCouplingMap.push({ source: 0, target: Math.min(1, chip.physicalQubitCount - 1) }) }
function copyArchitecture() { form.architectures.push(cloneStudyArchitecture(form.architectures.at(-1), form.architectures.length + 1)) }
function next() { errors.value = validateBondScanForm(form, capabilities.value || {}); if (!errors.value.length) step.value += 1 }
async function submit() {
  errors.value = validateBondScanForm(form, capabilities.value || {})
  if (errors.value.length) return
  submitting.value = true
  requestError.value = null
  try {
    const { data } = await submitMolecularBondScan(buildBondScanPayload(form), { idempotencyKey: createIdempotencyKey() })
    saveRecentMolecularBondScan(data)
    await router.push(`/app/molecular-bond-scans/${encodeURIComponent(data.scan_id)}`)
  } catch (error) {
    requestError.value = normalizeMolecularBondScanError(error)
    if (requestError.value.status === 401) await router.replace({ path: '/auth', query: { tab: 'login', redirect: route.fullPath } })
  } finally { submitting.value = false }
}
onMounted(async () => {
  try {
    capabilities.value = await getMolecularBondScanCapabilities()
    form.basisSet = capabilities.value.supported_basis_sets?.[0] || form.basisSet
  } catch (error) {
    const normalized = normalizeMolecularBondScanError(error)
    capabilityError.value = normalized.message
    if (normalized.status === 401) await router.replace({ path: '/auth', query: { tab: 'login', redirect: route.fullPath } })
  } finally { loadingCapabilities.value = false }
})
</script>

<style scoped>
.bond-create-page{display:grid;gap:22px}.page-head{min-height:175px;padding:32px;border:1px solid #c7cdc5;background:#e7eae3;display:flex;align-items:flex-end;justify-content:space-between;gap:22px}.page-head span,.panel header>span{color:#6c7b70;font:700 .66rem ui-monospace,monospace;letter-spacing:.12em}.page-head h2{margin:10px 0;font-size:clamp(2rem,4vw,4.1rem);letter-spacing:-.06em}.page-head p{margin:0;color:#637067}.fixed-tags{display:flex;gap:8px;flex-wrap:wrap}.builder,.loading{border:1px solid #c9cec7;background:#fff}.loading{padding:32px}.step-rail{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #d9ded7}.step-rail span{padding:16px;color:#748079;font:700 .7rem ui-monospace,monospace}.step-rail .active{background:#17201d;color:#b5f04c}.panel{padding:32px}.panel h3{margin:8px 0 25px;font-size:1.6rem}.form-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.form-grid :deep(.el-input-number),.form-grid :deep(.el-select){width:100%}.distance-preview{display:flex;flex-wrap:wrap;gap:8px;padding:18px;border:1px solid #d5dbd3;background:#f4f6f2;font:600 .72rem ui-monospace,monospace}.distance-preview strong{width:100%;color:#647e4b}.distance-preview span{padding:5px 7px;border:1px solid #d5dbd3}.arch-head{display:flex;justify-content:space-between;gap:16px}.arch-head p{max-width:700px;color:#68736b;font-size:.82rem}.architecture{margin-top:16px;padding:20px;border:1px solid #d5dbd3;background:#f7f8f5}.architecture>header,.topology-editors header,.chip-editor header{display:flex;justify-content:space-between;gap:8px;align-items:center}.architecture-basics{margin-top:16px}.topology-editors,.chips{display:grid;grid-template-columns:1.1fr .9fr;gap:12px;margin-top:12px}.topology-editors>section,.chip-editor{padding:14px;border:1px solid #d5dbd3;background:#fff}.topology-editors b,.chip-editor b,.coupling-title b{color:#5f813e;font:700 .66rem ui-monospace,monospace}.topology-editors small,.chip-editor small{color:#79857d;font-size:.69rem}.edge-row{display:flex;align-items:center;gap:7px;margin-top:9px}.edge-row :deep(.el-input-number){width:94px}.chips{grid-template-columns:repeat(3,minmax(0,1fr))}.chip-editor :deep(.el-input-number){width:100%}.chip-editor :deep(.el-form-item){margin:12px 0}.coupling-title{display:flex;justify-content:space-between;align-items:center}.empty-edge{padding:10px 0;color:#849087;font-size:.72rem}.summary{padding:20px;border-left:3px solid #73994d;background:#f3f6f1;line-height:1.7}footer{min-height:72px;padding:14px 28px;border-top:1px solid #dde2dc;display:flex;align-items:center;gap:12px}footer span{margin-right:auto;color:#778179;font:700 .68rem ui-monospace,monospace}.mono{font-family:ui-monospace,monospace}@media(max-width:980px){.form-grid,.chips{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.page-head,.arch-head{align-items:flex-start;flex-direction:column}.step-rail,.form-grid,.topology-editors,.chips{grid-template-columns:1fr}.panel{padding:20px}.step-rail span{padding:11px;font-size:.6rem}.edge-row :deep(.el-input-number){width:88px}}</style>
