<template>
  <div class="molecule-entry-page">
    <header class="molecule-page-head">
      <div>
        <span class="lz-kicker">Molecule-to-distributed-simulation</span>
        <h2>小分子量子计算</h2>
        <p>从固定分子几何生成 Hamiltonian 与 VQE 线路，完成线路分区和虚拟节点逻辑分布式模拟。</p>
      </div>
      <div class="capability-badges" aria-label="执行能力说明">
        <el-tag effect="dark">模拟器</el-tag>
        <el-tag type="success" effect="plain">虚拟节点逻辑分布式模拟</el-tag>
        <el-tag type="warning" effect="plain">非真实 QPU</el-tag>
      </div>
    </header>

    <el-alert
      v-if="requestError"
      class="request-alert"
      type="error"
      :closable="false"
      show-icon
    >
      <template #title>{{ requestError.title }}</template>
      <p>{{ requestError.message }}</p>
      <p v-if="requestError.stage">失败阶段：{{ stageLabel(requestError.stage) }}</p>
      <p v-if="requestError.workflowId" class="mono">Workflow ID：{{ requestError.workflowId }}</p>
      <div class="alert-actions">
        <el-button v-if="requestError.retryable && retryContext" size="small" @click="retryNetworkRequest">使用原幂等 Key 重试</el-button>
        <router-link v-if="requestError.status === 401" to="/auth?tab=login"><el-button size="small">重新登录</el-button></router-link>
      </div>
    </el-alert>

    <section v-if="isSubmitting" class="calculation-state" aria-live="polite">
      <div class="calculation-title">
        <span class="running-indicator" aria-hidden="true"></span>
        <div>
          <strong>正在计算</strong>
          <p>POST 为同步长请求。返回前仅展示预计阶段，不代表任何阶段已经完成。</p>
        </div>
      </div>
      <ol class="estimated-stages">
        <li v-for="(stage, index) in stageDefinitions" :key="stage.id">
          <span>{{ String(index + 1).padStart(2, '0') }}</span>
          <strong>{{ stage.label }}</strong>
          <small>预计阶段</small>
        </li>
      </ol>
    </section>

    <div v-else class="entry-layout">
      <main class="molecule-form-panel">
        <section class="preset-section">
          <div>
            <span class="section-label">预置分子</span>
            <h3>选择起始几何</h3>
          </div>
          <el-radio-group v-model="selectedPreset" @change="applyPreset">
            <el-radio-button value="H2">H₂</el-radio-button>
            <el-radio-button value="LiH">LiH</el-radio-button>
            <el-radio-button value="H2O">H₂O</el-radio-button>
          </el-radio-group>
        </section>

        <el-form label-position="top" class="molecule-form" @submit.prevent>
          <div class="form-grid four-columns">
            <el-form-item label="分子名称" required><el-input v-model="form.moleculeName" maxlength="120" /></el-form-item>
            <el-form-item label="电荷" required><el-input-number v-model="form.charge" :min="-10" :max="10" :step="1" /></el-form-item>
            <el-form-item label="自旋多重度" required><el-input-number v-model="form.spinMultiplicity" :min="1" :max="11" :step="1" /></el-form-item>
            <el-form-item label="基组" required><el-input v-model="form.basisSet" maxlength="64" placeholder="sto-3g" /></el-form-item>
            <el-form-item label="活性空间轨道数" required><el-input-number v-model="form.activeSpaceOrbitals" :min="1" :max="6" /></el-form-item>
            <el-form-item label="Pauli 截断阈值" required><el-input-number v-model="form.pauliCoefficientCutoff" :min="0.00000001" :max="0.01" :step="0.000001" :precision="8" /></el-form-item>
            <el-form-item label="VQE 层数" required><el-input-number v-model="form.ansatzLayers" :min="1" :max="4" /></el-form-item>
            <el-form-item label="VQE 迭代数" required><el-input-number v-model="form.maxIterations" :min="1" :max="500" /></el-form-item>
          </div>

          <section class="form-subsection">
            <div class="subsection-head">
              <div><span class="section-label">Fixed geometry</span><h3>原子与三维坐标（Å）</h3></div>
              <el-button :disabled="form.geometry.length >= 10" @click="addAtom">添加原子</el-button>
            </div>
            <div class="atom-table" role="table" aria-label="原子与三维坐标">
              <div class="atom-row atom-head" role="row"><span>元素</span><span>X</span><span>Y</span><span>Z</span><span>操作</span></div>
              <div v-for="(atom, index) in form.geometry" :key="index" class="atom-row" role="row">
                <el-input v-model="atom.element" :aria-label="`第 ${index + 1} 个原子元素`" maxlength="2" />
                <el-input-number v-for="axis in [0, 1, 2]" :key="axis" v-model="atom.coordinates[axis]" :precision="6" :step="0.1" :aria-label="`第 ${index + 1} 个原子坐标 ${axis}`" />
                <el-button type="danger" plain :disabled="form.geometry.length === 1" @click="removeAtom(index)">删除</el-button>
              </div>
            </div>
            <p class="field-note">计算直接使用以上固定几何，不执行几何优化。</p>
          </section>

          <section class="form-subsection partition-section">
            <div class="subsection-head">
              <div><span class="section-label">Partition &amp; topology</span><h3>分区与虚拟节点拓扑</h3></div>
              <el-form-item label="分区数量" required><el-input-number v-model="form.partitionCount" :min="2" :max="3" @change="normalizeEdges" /></el-form-item>
            </div>
            <div class="topology-edges">
              <div v-for="(edge, index) in form.topologyEdges" :key="index" class="edge-row">
                <span>拓扑边 {{ index + 1 }}</span>
                <el-input-number v-model="edge.source" :min="0" :max="form.partitionCount - 1" aria-label="源节点" />
                <span>→</span>
                <el-input-number v-model="edge.target" :min="0" :max="form.partitionCount - 1" aria-label="目标节点" />
                <el-button type="danger" plain :disabled="form.topologyEdges.length === 1" @click="removeEdge(index)">删除</el-button>
              </div>
              <el-button :disabled="form.topologyEdges.length >= 3" @click="addEdge">添加拓扑边</el-button>
            </div>
          </section>

          <el-alert v-if="validationErrors.length" type="error" :closable="false" show-icon title="请修正以下字段">
            <ul><li v-for="message in validationErrors" :key="message">{{ message }}</li></ul>
          </el-alert>

          <div class="fixed-contract">
            <div><span>Hamiltonian 映射</span><strong>jordan_wigner</strong></div>
            <div><span>执行模式</span><strong>logical_virtual_qpu</strong></div>
            <div><span>能力边界</span><strong>模拟器 · 非真实 QPU</strong></div>
          </div>
          <div class="submit-row">
            <p>新任务会生成独立 Idempotency-Key；网络重试复用该 Key。</p>
            <el-button type="primary" size="large" :loading="isSubmitting" :disabled="isSubmitting" @click="startNewWorkflow">开始计算</el-button>
          </div>
        </el-form>
      </main>

      <aside class="recent-panel">
        <div class="recent-head">
          <div>
            <span class="section-label">Workflow history</span>
            <h3>最近任务</h3>
          </div>
          <el-tag v-if="recentSource === 'local'" type="warning" size="small" effect="plain">本机缓存</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">服务端记录</el-tag>
        </div>
        <p v-if="recentError" class="recent-error">{{ recentError }} <button type="button" @click="loadRecentWorkflows">重试</button></p>
        <div v-if="recentLoading && !recentWorkflows.length" class="empty-recent">正在读取最近任务…</div>
        <div v-if="recentWorkflows.length" class="recent-list">
          <router-link v-for="item in recentWorkflows" :key="item.workflowId" :to="`/app/molecule-workflows/${item.workflowId}`">
            <span class="recent-title">
              <strong>{{ item.moleculeName }}</strong>
              <el-tag v-if="item.validationStatus === 'passed'" size="small" type="success">计算通过</el-tag>
              <el-tag v-else-if="item.validationStatus === 'needs_review'" size="small" type="warning">需要复核</el-tag>
              <el-tag v-else size="small" type="info">待确认</el-tag>
            </span>
            <small class="mono">{{ item.workflowId }}</small>
            <span>{{ formatTime(item.completedAt) }}</span>
          </router-link>
        </div>
        <div v-else-if="!recentLoading" class="empty-recent">服务端暂无计算任务。</div>
        <router-link class="all-tasks-link" to="/app/molecule-workflows">查看全部任务 <span aria-hidden="true">→</span></router-link>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearAuthSession } from '../services/authStorage'
import {
  MOLECULE_STAGE_DEFINITIONS,
  buildMoleculeWorkflowPayload,
  canUseMoleculeWorkflowLocalFallback,
  clonePreset,
  createIdempotencyKey,
  listMoleculeWorkflows,
  normalizeMoleculeWorkflowError,
  stageLabel,
  submitMoleculeWorkflow,
  validateMoleculeWorkflowForm,
} from '../services/moleculeWorkflowService'
import { readRecentMoleculeWorkflows, saveRecentMoleculeWorkflow } from '../services/moleculeWorkflowStorage'

const router = useRouter()
const selectedPreset = ref('H2')
const form = reactive(clonePreset('H2'))
const validationErrors = ref([])
const requestError = ref(null)
const isSubmitting = ref(false)
const retryContext = ref(null)
const recentWorkflows = ref([])
const recentSource = ref('server')
const recentLoading = ref(false)
const recentError = ref('')
const stageDefinitions = MOLECULE_STAGE_DEFINITIONS

function toRecentViewItem(item) {
  return {
    workflowId: item.workflow_id,
    moleculeName: item.molecule_name || '未命名分子',
    validationStatus: item.validation_status || null,
    completedAt: item.completed_at || item.created_at || null,
  }
}

function localRecentViewItems() {
  return readRecentMoleculeWorkflows().slice(0, 5)
}

async function loadRecentWorkflows() {
  recentLoading.value = true
  recentError.value = ''
  try {
    const response = await listMoleculeWorkflows({ page: 1, page_size: 5 })
    recentWorkflows.value = (Array.isArray(response?.items) ? response.items : []).slice(0, 5).map(toRecentViewItem)
    recentSource.value = 'server'
  } catch (error) {
    recentError.value = '最近任务接口暂不可用。'
    if (!recentWorkflows.value.length && canUseMoleculeWorkflowLocalFallback(error)) {
      recentWorkflows.value = localRecentViewItems()
      recentSource.value = 'local'
    }
  } finally {
    recentLoading.value = false
  }
}

function replaceForm(next) {
  for (const key of Object.keys(form)) delete form[key]
  Object.assign(form, next)
  validationErrors.value = []
  requestError.value = null
  retryContext.value = null
}

function applyPreset(name) {
  replaceForm(clonePreset(name))
}

function addAtom() {
  if (form.geometry.length < 10) form.geometry.push({ element: 'H', coordinates: [0, 0, 0] })
}

function removeAtom(index) {
  if (form.geometry.length > 1) form.geometry.splice(index, 1)
}

function addEdge() {
  if (form.topologyEdges.length < 3) form.topologyEdges.push({ source: 0, target: Math.min(1, form.partitionCount - 1) })
}

function removeEdge(index) {
  if (form.topologyEdges.length > 1) form.topologyEdges.splice(index, 1)
}

function normalizeEdges() {
  for (const edge of form.topologyEdges) {
    edge.source = Math.min(edge.source, form.partitionCount - 1)
    edge.target = Math.min(edge.target, form.partitionCount - 1)
  }
}

async function performSubmission(payload, idempotencyKey) {
  isSubmitting.value = true
  requestError.value = null
  try {
    const result = await submitMoleculeWorkflow(payload, { idempotencyKey })
    saveRecentMoleculeWorkflow(result.data)
    retryContext.value = null
    await router.push(`/app/molecule-workflows/${result.data.workflow_id}`)
  } catch (error) {
    requestError.value = normalizeMoleculeWorkflowError(error)
    if (requestError.value.status === 401) clearAuthSession()
    if (requestError.value.retryable) retryContext.value = { payload, idempotencyKey: error.idempotencyKey || idempotencyKey }
  } finally {
    isSubmitting.value = false
  }
}

async function startNewWorkflow() {
  validationErrors.value = validateMoleculeWorkflowForm(form)
  if (validationErrors.value.length) return
  const payload = buildMoleculeWorkflowPayload(form)
  const idempotencyKey = createIdempotencyKey()
  retryContext.value = { payload, idempotencyKey }
  await performSubmission(payload, idempotencyKey)
}

async function retryNetworkRequest() {
  if (!retryContext.value || isSubmitting.value) return
  await performSubmission(retryContext.value.payload, retryContext.value.idempotencyKey)
}

function formatTime(value) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—'
}

onMounted(loadRecentWorkflows)
</script>

<style scoped>
.molecule-entry-page { display: grid; gap: 20px; }
.molecule-page-head, .preset-section, .subsection-head, .submit-row, .calculation-title { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.molecule-page-head h2 { margin: 6px 0 8px; font-size: clamp(1.65rem, 3vw, 2.3rem); }
.molecule-page-head p, .field-note, .submit-row p, .calculation-title p { margin: 0; color: var(--lz-muted); line-height: 1.6; }
.capability-badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.request-alert :deep(.el-alert__content) { width: 100%; }
.request-alert p { margin: 5px 0; }
.alert-actions { margin-top: 10px; display: flex; gap: 8px; }
.entry-layout { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 20px; align-items: start; }
.molecule-form-panel, .recent-panel, .calculation-state { border: 1px solid var(--lz-line); border-radius: 12px; background: rgba(8, 20, 36, 0.74); box-shadow: var(--lz-shadow); }
.molecule-form-panel { padding: 22px; }
.recent-panel { padding: 20px; position: sticky; top: 20px; }
.preset-section { padding-bottom: 20px; border-bottom: 1px solid var(--lz-line); }
.preset-section h3, .form-subsection h3, .recent-panel h3 { margin: 4px 0 0; }
.recent-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.section-label { color: var(--lz-cyan); font-size: 0.72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.molecule-form { margin-top: 20px; }
.form-grid { display: grid; gap: 14px; }
.four-columns { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.molecule-form :deep(.el-input-number) { width: 100%; }
.form-subsection { margin: 12px 0 22px; padding-top: 20px; border-top: 1px solid var(--lz-line); }
.subsection-head { margin-bottom: 14px; }
.subsection-head :deep(.el-form-item) { margin: 0; min-width: 150px; }
.atom-table { overflow-x: auto; }
.atom-row { min-width: 650px; display: grid; grid-template-columns: 100px repeat(3, minmax(130px, 1fr)) 82px; gap: 10px; align-items: center; margin-bottom: 10px; }
.atom-head { color: var(--lz-muted); font-size: .78rem; font-weight: 800; }
.edge-row { display: grid; grid-template-columns: 100px 120px 20px 120px 80px; gap: 10px; align-items: center; margin-bottom: 10px; }
.edge-row :deep(.el-input-number) { width: 120px; }
.fixed-contract { margin: 18px 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.fixed-contract div { padding: 14px; border: 1px solid var(--lz-line); border-radius: 8px; display: grid; gap: 6px; background: rgba(52, 214, 255, .04); }
.fixed-contract span { color: var(--lz-muted); font-size: .76rem; }
.fixed-contract strong { color: var(--lz-cyan); overflow-wrap: anywhere; }
.recent-list { display: grid; gap: 10px; margin-top: 14px; }
.recent-list a { padding: 12px; border: 1px solid var(--lz-line); border-radius: 8px; color: var(--lz-text); text-decoration: none; display: grid; gap: 5px; }
.recent-list a:hover { border-color: var(--lz-cyan); }
.recent-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.recent-list small, .recent-list span, .empty-recent { color: var(--lz-muted); font-size: .75rem; overflow-wrap: anywhere; }
.empty-recent { padding: 22px 0; line-height: 1.6; }
.recent-error { margin: 12px 0 0; color: #f2c35b; font-size: .76rem; line-height: 1.5; }
.recent-error button { padding: 0; border: 0; background: transparent; color: var(--lz-cyan); cursor: pointer; }
.all-tasks-link { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--lz-line); display: flex; justify-content: space-between; color: var(--lz-cyan); font-size: .82rem; font-weight: 700; text-decoration: none; }
.calculation-state { padding: 24px; }
.running-indicator { width: 18px; height: 18px; border: 2px solid rgba(52,214,255,.25); border-top-color: var(--lz-cyan); border-radius: 50%; animation: spin 1s linear infinite; }
.estimated-stages { list-style: none; padding: 0; margin: 22px 0 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.estimated-stages li { padding: 14px; border: 1px solid var(--lz-line); border-radius: 8px; display: grid; gap: 5px; }
.estimated-stages li > span { color: var(--lz-cyan); font-size: .72rem; font-weight: 800; }
.estimated-stages small { color: var(--lz-muted); }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1200px) { .entry-layout { grid-template-columns: 1fr; } .recent-panel { position: static; } .four-columns { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px) { .molecule-page-head, .preset-section, .subsection-head, .submit-row { align-items: flex-start; flex-direction: column; } .capability-badges { justify-content: flex-start; } .four-columns, .fixed-contract, .estimated-stages { grid-template-columns: 1fr; } .molecule-form-panel { padding: 16px; } }
</style>
