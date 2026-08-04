<template>
  <section class="workflow-page">
    <div v-if="isLoading" class="loading-state"><el-skeleton :rows="10" animated /></div>

    <el-result
      v-else-if="loadError"
      icon="error"
      title="无法加载文献复现工作流"
      :sub-title="loadError"
    >
      <template #extra><el-button type="primary" @click="loadWorkflow">重试</el-button></template>
    </el-result>

    <template v-else-if="workflow">
      <header class="workflow-hero">
        <div>
          <span class="eyebrow">Literature Reproduction Workflow</span>
          <h2>FeN4C66 + Li2S4 文献复现输入</h2>
          <p class="workflow-id">Workflow · {{ workflow.workflow_id }}</p>
        </div>
        <div class="hero-tags">
          <el-tag effect="dark" type="info">{{ dataSourceLabel }}</el-tag>
          <el-tag effect="dark" type="warning">{{ validationLabel }}</el-tag>
          <el-tag effect="plain">{{ workflowStatusLabel }}</el-tag>
        </div>
      </header>

      <el-alert
        type="warning"
        :closable="false"
        title="这是公开文献数据的复现输入链。文献优化几何已就绪不等于平台独立 DFT 重算已完成；后续量子阶段尚未开始时不会显示能量曲线、QPU 状态或材料推荐。"
      />

      <section class="workflow-summary">
        <div><span>数据来源</span><b>{{ dataSourceLabel }}</b></div>
        <div><span>科学验证等级</span><b>{{ validationLabel }}</b></div>
        <div><span>论文 DOI</span><b>{{ workflow.payload?.source_doi || '后端未返回' }}</b></div>
        <div><span>创建时间</span><b>{{ formatDate(workflow.created_at) }}</b></div>
      </section>

      <section class="stage-panel">
        <div class="section-heading">
          <div>
            <span class="eyebrow">Evidence Chain</span>
            <h3>文献复现工作流阶段</h3>
          </div>
          <el-button plain @click="router.push('/app/research-benchmarks')">返回文献基准</el-button>
        </div>

        <ol class="stage-timeline">
          <li v-for="stage in displayStages" :key="stage.key" :class="stageStateClass(stage)">
            <span class="stage-marker">{{ stage.index }}</span>
            <article class="stage-card">
              <div class="stage-card-head">
                <div><span class="eyebrow">{{ stage.source ? dataSourceLabel : '后续研究步骤' }}</span><h4>{{ stage.label }}</h4></div>
                <el-tag :type="stageTagType(stage)" effect="plain">{{ stageStatusLabel(stage) }}</el-tag>
              </div>
              <p>{{ stageDescription(stage) }}</p>
              <p v-if="stage.stage.created_at" class="stage-audit">阶段记录时间：{{ formatDate(stage.stage.created_at) }}</p>
              <el-alert
                v-if="stage.stage.warnings?.length"
                class="stage-warning"
                type="warning"
                :closable="false"
                :title="stage.stage.warnings.join('；')"
              />
              <dl v-if="stage.stage?.objects?.length" class="stage-objects">
                <div v-for="object in stage.stage.objects" :key="object.object_id">
                  <dt>{{ object.object_type }}</dt><dd>{{ object.status }}</dd>
                </div>
              </dl>
              <div v-if="stage.stage?.confirmations?.length" class="confirmation-list">
                <span v-for="confirmation in stage.stage.confirmations" :key="confirmation.object_id">
                  已确认 · {{ formatDate(confirmation.confirmed_at) }}
                </span>
              </div>
              <div v-if="stage.stage?.artifacts?.length" class="artifact-list">
                <div v-for="artifact in stage.stage.artifacts" :key="artifact.artifact_id" class="artifact-item">
                  <div>
                    <strong>{{ artifactMetadata[artifact.artifact_id]?.filename || artifact.artifact_role }}</strong>
                    <small>{{ artifactMetadata[artifact.artifact_id]?.media_type || artifact.resource_type }} · {{ artifactMetadata[artifact.artifact_id]?.size_bytes ?? '大小待查询' }} bytes</small>
                    <small class="hash">SHA-256 · {{ artifactMetadata[artifact.artifact_id]?.checksum_sha256 || '元数据待查询' }}</small>
                    <small v-if="artifactErrors[artifact.artifact_id]" class="artifact-error">{{ artifactErrors[artifact.artifact_id] }}</small>
                  </div>
                  <el-button size="small" :disabled="Boolean(artifactErrors[artifact.artifact_id])" @click="downloadArtifact(artifact)">下载</el-button>
                </div>
              </div>
              <p v-else-if="stage.key === 'hamiltonian' || stage.key === 'vqe'" class="not-started-note">尚未开始；不会显示任何 Hamiltonian、VQE、QPU 或材料推荐结论。</p>
            </article>
          </li>
        </ol>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useStructureWorkflow } from '../composables/use-structure-workflow'
import {
  downloadStructureWorkflowArtifact,
  fetchStructureWorkflow,
  fetchStructureWorkflowArtifact,
} from '../api/platformApi'

const STAGE_DEFINITIONS = [
  { key: 'structure', label: '结构解析', source: true },
  { key: 'active_site', label: 'Fe-N4 活性位点', source: true },
  { key: 'adsorption_model', label: 'Li2S4 吸附构型', source: true },
  { key: 'geometry_and_dft', label: '文献优化几何', source: true },
  { key: 'quantum_region', label: '量子区', source: false },
  { key: 'active_space', label: '活性空间', source: false },
  { key: 'hamiltonian', label: 'Hamiltonian', source: false },
  { key: 'vqe', label: 'VQE', source: false },
]

const route = useRoute()
const router = useRouter()
const { syncWorkflowFromDetail } = useStructureWorkflow()
const workflow = ref(null)
const isLoading = ref(false)
const loadError = ref('')
const artifactMetadata = ref({})
const artifactErrors = ref({})

const dataSourceLabel = computed(() => (
  workflow.value?.data_source === 'literature_open_dataset' ? '公开文献数据集' : workflow.value?.data_source || '后端未返回'
))
const validationLabel = computed(() => (
  workflow.value?.scientific_validation_level === 'reproduction_baseline_only'
    ? '仅文献复现基线'
    : workflow.value?.scientific_validation_level || '后端未返回'
))
const workflowStatusLabel = computed(() => mapWorkflowStatus(workflow.value?.status))
const displayStages = computed(() => {
  const stagesByKey = new Map((workflow.value?.stages || []).map(stage => [stage.stage_name, stage]))
  return STAGE_DEFINITIONS.map((definition, index) => ({ ...definition, index: index + 1, stage: stagesByKey.get(definition.key) || { status: 'not_started', objects: [], artifacts: [] } }))
})

watch(() => route.params.workflowId, loadWorkflow, { immediate: true })

async function loadWorkflow() {
  const workflowId = route.params.workflowId
  if (!workflowId) return
  isLoading.value = true
  loadError.value = ''
  artifactMetadata.value = {}
  artifactErrors.value = {}
  try {
    const response = await fetchStructureWorkflow(workflowId)
    workflow.value = response.data
    if (workflow.value.data_source !== 'literature_open_dataset') {
      loadError.value = '该工作流不是公开文献数据集的复现输入，不能在此页面展示。'
      workflow.value = null
      return
    }
    syncWorkflowFromDetail(workflow.value)
    await loadArtifactMetadata()
  } catch (error) {
    workflow.value = null
    loadError.value = readErrorMessage(error, '网络请求失败，请稍后重试。')
  } finally {
    isLoading.value = false
  }
}

async function loadArtifactMetadata() {
  const artifacts = displayStages.value.flatMap(stage => stage.stage.artifacts || [])
  const uniqueArtifacts = [...new Map(artifacts.map(artifact => [artifact.artifact_id, artifact])).values()]
  const results = await Promise.allSettled(uniqueArtifacts.map(async artifact => ({ artifact, response: await fetchStructureWorkflowArtifact(workflow.value.workflow_id, artifact.artifact_id) })))
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      artifactMetadata.value[result.value.artifact.artifact_id] = result.value.response.data
      return
    }
    const artifact = uniqueArtifacts[index]
    artifactErrors.value[artifact.artifact_id] = readErrorMessage(result.reason, '无法读取 Artifact 元数据。')
  })
}

async function downloadArtifact(artifact) {
  try {
    const response = await downloadStructureWorkflowArtifact(workflow.value.workflow_id, artifact.artifact_id)
    const filename = artifactMetadata.value[artifact.artifact_id]?.filename || `${artifact.artifact_id}.bin`
    const objectUrl = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(objectUrl)
  } catch (error) {
    const message = readErrorMessage(error, 'Artifact 下载失败。')
    artifactErrors.value[artifact.artifact_id] = message
    ElMessage.error(message)
  }
}

function mapWorkflowStatus(status) {
  const labels = {
    literature_reproduction_input_selected: '已选定文献复现输入',
    literature_reproduction_geometry_ready: '文献优化几何已就绪',
  }
  return labels[status] || status || '后端未返回'
}

function stageStatusLabel(stage) {
  if (stage.stage.status === 'not_started') return '尚未开始'
  if (stage.key === 'geometry_and_dft' && stage.stage.status === 'completed') return '已登记文献优化几何'
  if (stage.key === 'adsorption_model' && stage.stage.status === 'literature_selected') return '已选择文献优化候选'
  if (stage.stage.status === 'confirmed') return '已确认'
  return stage.stage.status
}

function stageDescription(stage) {
  if (stage.stage.status === 'not_started') return '该步骤尚未开始，页面不会用占位数据模拟科研结果。'
  if (stage.key === 'geometry_and_dft') return '该几何来自公开文献的已优化候选；平台独立 DFT 重算尚未完成。'
  if (stage.source) return '该阶段保留公开文献候选的来源与追溯关系。'
  return '仅在后端真实创建相应对象后，才会在此展示结果。'
}

function stageStateClass(stage) {
  return stage.stage.status === 'not_started' ? 'is-pending' : 'is-ready'
}

function stageTagType(stage) {
  if (stage.stage.status === 'not_started') return 'info'
  if (stage.key === 'geometry_and_dft') return 'warning'
  return 'success'
}

function formatDate(value) {
  if (!value) return '后端未返回'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function readErrorMessage(error, fallback) {
  return error.response?.data?.detail?.message || error.response?.data?.detail || error.message || fallback
}
</script>

<style scoped>
.workflow-page { display: grid; gap: 20px; color: var(--lz-text); }.workflow-hero, .workflow-summary, .stage-panel { border: 1px solid var(--lz-line); border-radius: 18px; background: linear-gradient(135deg, rgba(9, 27, 43, .96), rgba(7, 17, 30, .92)); }.workflow-hero { padding: 26px; display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; background: radial-gradient(circle at 88% 12%, rgba(209, 164, 62, .22), transparent 32%), linear-gradient(135deg, rgba(9, 31, 51, .98), rgba(7, 17, 30, .96)); }.eyebrow { color: var(--lz-cyan); font-size: .75rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }.workflow-hero h2, .section-heading h3, .stage-card h4 { margin: 8px 0; }.workflow-id { margin: 0; color: var(--lz-muted); overflow-wrap: anywhere; }.hero-tags { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }.workflow-summary { padding: 18px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }.workflow-summary div { padding-right: 14px; border-right: 1px solid rgba(135, 184, 215, .18); }.workflow-summary div:last-child { border: 0; }.workflow-summary span { display: block; color: var(--lz-muted); font-size: .75rem; }.workflow-summary b { display: block; margin-top: 6px; overflow-wrap: anywhere; font-size: .86rem; }.stage-panel { padding: 22px; }.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }.stage-timeline { list-style: none; margin: 22px 0 0; padding: 0; display: grid; gap: 14px; }.stage-timeline li { position: relative; display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 14px; }.stage-timeline li:not(:last-child)::before { content: ''; position: absolute; left: 17px; top: 36px; bottom: -14px; width: 2px; background: rgba(115, 183, 215, .25); }.stage-marker { width: 36px; height: 36px; display: inline-grid; place-items: center; border: 1px solid rgba(115, 183, 215, .45); border-radius: 50%; background: #0d283d; color: var(--lz-cyan); font-weight: 700; z-index: 1; }.is-pending .stage-marker { color: var(--lz-muted); border-color: rgba(135, 184, 215, .2); background: #0a1824; }.stage-card { min-width: 0; padding: 17px; border: 1px solid rgba(135, 184, 215, .2); border-radius: 12px; background: rgba(6, 17, 29, .7); }.stage-card-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }.stage-card > p { margin: 8px 0 0; color: var(--lz-muted); line-height: 1.6; }.stage-audit { font-size: .77rem; }.stage-warning { margin-top: 12px; --el-alert-bg-color: rgba(201, 139, 32, .1); --el-alert-border-color: rgba(223, 174, 71, .28); }.stage-objects { margin: 13px 0 0; display: flex; flex-wrap: wrap; gap: 8px; }.stage-objects div, .confirmation-list span { padding: 5px 8px; border-radius: 6px; background: rgba(111, 195, 224, .08); font-size: .75rem; }.stage-objects dt, .stage-objects dd { display: inline; margin: 0; }.stage-objects dt { color: var(--lz-muted); }.stage-objects dd::before { content: ' · '; }.confirmation-list { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; color: #78d9b5; }.artifact-list { margin-top: 14px; display: grid; gap: 8px; }.artifact-item { padding: 10px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid rgba(135, 184, 215, .16); border-radius: 8px; }.artifact-item strong, .artifact-item small { display: block; overflow-wrap: anywhere; }.artifact-item small { margin-top: 3px; color: var(--lz-muted); font-size: .73rem; }.artifact-item .hash { font-family: Consolas, 'SFMono-Regular', monospace; }.artifact-error { color: #f1a28e !important; }.not-started-note { color: #9fb7c9 !important; font-style: italic; }.loading-state { padding: 28px; }
@media (max-width: 800px) { .workflow-hero, .section-heading { flex-direction: column; }.hero-tags { justify-content: flex-start; }.workflow-summary { grid-template-columns: 1fr 1fr; }.workflow-summary div:nth-child(2) { border-right: 0; }.workflow-summary div:nth-child(-n+2) { border-bottom: 1px solid rgba(135, 184, 215, .18); padding-bottom: 12px; } }
@media (max-width: 520px) { .workflow-summary { grid-template-columns: 1fr; }.workflow-summary div { border-right: 0; border-bottom: 1px solid rgba(135, 184, 215, .18); padding-bottom: 12px; }.workflow-summary div:last-child { border-bottom: 0; }.artifact-item { align-items: flex-start; flex-direction: column; } }
</style>
