<template>
  <section class="benchmark-page">
    <header class="page-hero">
      <div>
        <span class="eyebrow">Literature Reproduction Workspace</span>
        <h2>FeN4C66-Li2S4 Materials Cloud 文献复现基准</h2>
        <p>周期性 FeN4C66 + Li2S4 · 公开文献数据集 · 仅文献复现基线</p>
      </div>
      <el-tag type="warning" effect="dark">仅文献复现基线</el-tag>
    </header>

    <el-alert
      class="scientific-boundary"
      type="warning"
      :closable="false"
      title="当前数据为公开文献中已优化候选的复现输入。平台尚未完成独立 DFT 重算；候选源能量的单位语义未确认，不能作为吸附能或材料推荐结论。"
    />

    <div v-if="isLoading" class="loading-state"><el-skeleton :rows="8" animated /></div>

    <el-result
      v-else-if="!benchmark"
      icon="info"
      title="尚未导入已审核的文献基准"
      sub-title="请联系研究基准管理员导入已审核数据集。"
    >
      <template #extra>
        <el-button v-if="canImport" type="primary" :loading="isImporting" @click="handleImport">
          导入已审核的 Materials Cloud 基准
        </el-button>
      </template>
    </el-result>

    <template v-else>
      <section class="overview-grid">
        <article class="overview-card source-card">
          <span class="card-label">公开文献数据集</span>
          <h3>{{ benchmark.title || 'FeN4C66-Li2S4 Materials Cloud 文献复现基准' }}</h3>
          <dl>
            <div><dt>模型</dt><dd>周期性 FeN4C66 + Li2S4</dd></div>
            <div><dt>论文 DOI</dt><dd><a :href="doiUrl" target="_blank" rel="noopener noreferrer">{{ benchmark.source_doi || '未返回' }}</a></dd></div>
            <div><dt>公开数据集</dt><dd><a :href="benchmark.source_url" target="_blank" rel="noopener noreferrer">Materials Cloud</a></dd></div>
            <div><dt>许可 / 版本</dt><dd>{{ benchmark.source_license || '未返回' }} · {{ benchmark.source_dataset_version || '未返回' }}</dd></div>
          </dl>
        </article>

        <article class="overview-card metric-card">
          <span class="card-label">已导入候选</span>
          <strong>{{ benchmark.candidate_count ?? '—' }}</strong>
          <small>候选构型由后端基准记录返回</small>
          <el-tag type="warning" effect="plain">{{ validationLabel }}</el-tag>
        </article>

        <article class="overview-card metadata-card">
          <span class="card-label">文献 DFT 元数据</span>
          <ul v-if="dftMetadataLines.length">
            <li v-for="item in dftMetadataLines" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b></li>
          </ul>
          <p v-else>后端尚未返回可展示的 DFT 元数据。</p>
        </article>
      </section>

      <section v-if="isCandidateRoute" class="candidate-workbench">
        <div class="section-heading">
          <div>
            <span class="eyebrow">Candidate Selection</span>
            <h3>文献候选构型</h3>
            <p>仅可单选一个组成校验通过的候选，创建属于当前用户的独立复现工作流。</p>
          </div>
          <el-button plain @click="router.push('/app/research-benchmarks')">返回基准概览</el-button>
        </div>

        <div class="candidate-controls">
          <el-input v-model="searchTerm" clearable placeholder="按文献候选 ID 精确搜索" />
          <el-select v-model="sortDirection" aria-label="优先序排序">
            <el-option label="优先序：升序" value="asc" />
            <el-option label="优先序：降序" value="desc" />
          </el-select>
          <el-checkbox v-model="onlyValidated">仅显示组成校验通过</el-checkbox>
          <span>{{ filteredCandidates.length }} / {{ candidates.length }} 个候选</span>
        </div>

        <div class="candidate-table" role="table" aria-label="文献候选构型">
          <div class="candidate-table-head" role="row">
            <span>文献候选 ID</span><span>优先序</span><span>源能量</span><span>组成校验</span><span>构型状态</span><span>操作</span>
          </div>
          <div ref="scrollContainer" class="virtual-scroll" role="rowgroup" @scroll="handleScroll">
            <div class="virtual-canvas" :style="{ height: `${virtualHeight}px` }">
              <div class="virtual-rows" :style="{ transform: `translateY(${virtualOffset}px)` }">
                <div v-for="candidate in visibleCandidates" :key="candidate.candidate_id" class="candidate-row" role="row">
                  <span class="candidate-id">{{ candidate.source_candidate_id }}</span>
                  <span>#{{ candidate.priority_rank }}</span>
                  <span>{{ formatEnergy(candidate) }}<small>源数据原始单位，未确认</small></span>
                  <span :class="compositionClass(candidate)">{{ compositionLabel(candidate) }}</span>
                  <span><el-tag size="small" effect="plain">文献候选构型</el-tag></span>
                  <span><el-button link type="primary" @click="openCandidateDrawer(candidate)">查看</el-button></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-else class="overview-action">
        <div>
          <span class="eyebrow">Next Step</span>
          <h3>查看 {{ benchmark.candidate_count ?? 0 }} 个文献候选</h3>
          <p>搜索、排序并选择一个可追溯的文献优化候选作为复现输入。</p>
        </div>
        <el-button type="primary" size="large" @click="openCandidates">查看文献候选</el-button>
      </section>

      <details v-if="canImport" class="admin-actions">
        <summary>管理操作</summary>
        <p>基准已导入后不可覆盖原始 Artifact；此操作仅在基准缺失时可用。</p>
        <el-button :loading="isImporting" @click="handleImport">导入已审核的 Materials Cloud 基准</el-button>
      </details>
    </template>

    <el-drawer v-model="isDrawerOpen" title="文献候选构型详情" size="min(560px, 94vw)">
      <template v-if="selectedCandidate">
        <dl class="drawer-details">
          <div><dt>文献候选 ID</dt><dd>{{ selectedCandidate.source_candidate_id }}</dd></div>
          <div><dt>优先序</dt><dd>#{{ selectedCandidate.priority_rank }}（仅代表源数据排序）</dd></div>
          <div><dt>源能量</dt><dd>{{ formatEnergy(selectedCandidate) }} · 源数据原始单位，未确认</dd></div>
          <div><dt>组成校验</dt><dd>{{ compositionLabel(selectedCandidate) }}</dd></div>
          <div><dt>坐标 Artifact</dt><dd class="mono">{{ selectedCandidate.coordinate_artifact_id }}</dd></div>
          <div><dt>Artifact 元数据</dt><dd>{{ candidateArtifactSummary }}</dd></div>
          <div><dt>来源说明</dt><dd>{{ selectedCandidate.source_metadata?.source_energy_semantics || '后端未返回来源说明。' }}</dd></div>
          <div><dt>坐标摘要</dt><dd>{{ coordinateSummary(selectedCandidate) }}</dd></div>
        </dl>
        <el-alert
          v-if="!isSelectable(selectedCandidate)"
          type="error"
          :closable="false"
          title="该候选的组成校验未通过或尚未返回，不能创建复现工作流。"
        />
        <p class="drawer-note">选择后，Artifact 将关联至当前用户的工作流；届时可在工作流详情中查看元数据和鉴权下载。</p>
        <el-button type="primary" :disabled="!isSelectable(selectedCandidate)" :loading="isSelecting" @click="confirmSelection">
          以此构型创建文献复现工作流
        </el-button>
      </template>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchResearchBenchmark,
  fetchResearchBenchmarkCandidateArtifact,
  fetchResearchBenchmarkCandidates,
  fetchResearchBenchmarks,
  importMaterialsCloudResearchBenchmark,
  selectResearchBenchmarkCandidate,
} from '../api/platformApi'
import {
  buildResearchBenchmarkDftMetadataLines,
  formatResearchBenchmarkComposition,
  formatResearchBenchmarkSourceEnergy,
  isResearchBenchmarkCandidateSelectable,
  mapResearchBenchmarkImportError,
} from '../services/research-benchmark-presentation'

const DEFAULT_BENCHMARK_KEY = 'fe-n4-c66-li2s4-literature-v1'
const ROW_HEIGHT_PX = 72
const VISIBLE_ROW_COUNT = 9
const OVERSCAN_ROW_COUNT = 5

const route = useRoute()
const router = useRouter()
const benchmark = ref(null)
const candidates = ref([])
const canImport = ref(false)
const isLoading = ref(false)
const isImporting = ref(false)
const isSelecting = ref(false)
const searchTerm = ref('')
const sortDirection = ref('asc')
const onlyValidated = ref(false)
const scrollTop = ref(0)
const isDrawerOpen = ref(false)
const selectedCandidate = ref(null)
const candidateArtifact = ref(null)
const candidateArtifactError = ref('')

const isCandidateRoute = computed(() => Boolean(route.params.benchmarkId))
const doiUrl = computed(() => (benchmark.value?.source_doi ? `https://doi.org/${benchmark.value.source_doi}` : '#'))
const validationLabel = computed(() => (
  benchmark.value?.scientific_validation_level === 'reproduction_baseline_only'
    ? '仅文献复现基线'
    : benchmark.value?.scientific_validation_level || '后端未返回'
))
const dftMetadataLines = computed(() => buildResearchBenchmarkDftMetadataLines(benchmark.value?.dft_metadata))
const candidateArtifactSummary = computed(() => {
  if (candidateArtifactError.value) return candidateArtifactError.value
  if (!candidateArtifact.value) return '正在读取 Artifact 元数据…'
  return `${candidateArtifact.value.filename} · ${candidateArtifact.value.media_type} · ${candidateArtifact.value.size_bytes} bytes · SHA-256 ${candidateArtifact.value.checksum_sha256}`
})
const filteredCandidates = computed(() => {
  const normalizedSearch = searchTerm.value.trim().toLowerCase()
  const direction = sortDirection.value === 'asc' ? 1 : -1
  return candidates.value
    .filter(candidate => !normalizedSearch || candidate.source_candidate_id?.toLowerCase() === normalizedSearch)
    .filter(candidate => !onlyValidated.value || isSelectable(candidate))
    .sort((first, second) => direction * ((first.priority_rank ?? Number.MAX_SAFE_INTEGER) - (second.priority_rank ?? Number.MAX_SAFE_INTEGER)))
})
const firstVisibleIndex = computed(() => Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT_PX) - OVERSCAN_ROW_COUNT))
const visibleCandidates = computed(() => filteredCandidates.value.slice(firstVisibleIndex.value, firstVisibleIndex.value + VISIBLE_ROW_COUNT + OVERSCAN_ROW_COUNT * 2))
const virtualHeight = computed(() => filteredCandidates.value.length * ROW_HEIGHT_PX)
const virtualOffset = computed(() => firstVisibleIndex.value * ROW_HEIGHT_PX)

watch(
  () => route.params.benchmarkId,
  () => loadPage(),
  { immediate: true }
)

async function loadPage() {
  isLoading.value = true
  candidates.value = []
  scrollTop.value = 0
  try {
    const requestedBenchmarkId = route.params.benchmarkId
    if (requestedBenchmarkId) {
      const [benchmarkResponse, candidatesResponse] = await Promise.all([
        fetchResearchBenchmark(requestedBenchmarkId),
        fetchResearchBenchmarkCandidates(requestedBenchmarkId),
      ])
      benchmark.value = benchmarkResponse.data
      candidates.value = candidatesResponse.data.items || []
      return
    }
    const response = await fetchResearchBenchmarks(DEFAULT_BENCHMARK_KEY)
    canImport.value = Boolean(response.data.can_import)
    benchmark.value = response.data.items?.[0] || null
  } catch (error) {
    benchmark.value = null
    ElMessage.error(readErrorMessage(error, '无法加载文献基准。'))
  } finally {
    isLoading.value = false
  }
}

function openCandidates() {
  router.push(`/app/research-benchmarks/${benchmark.value.benchmark_id}`)
}

function handleScroll(event) {
  scrollTop.value = event.target.scrollTop
}

async function openCandidateDrawer(candidate) {
  selectedCandidate.value = candidate
  candidateArtifact.value = null
  candidateArtifactError.value = ''
  isDrawerOpen.value = true
  try {
    const response = await fetchResearchBenchmarkCandidateArtifact(benchmark.value.benchmark_id, candidate.candidate_id)
    candidateArtifact.value = response.data
  } catch (error) {
    candidateArtifactError.value = readErrorMessage(error, '无法读取候选坐标 Artifact 元数据。')
  }
}

async function confirmSelection() {
  if (!selectedCandidate.value || isSelecting.value) return
  try {
    await ElMessageBox.confirm(
      '将把不可变的文献候选复制为一个属于当前用户的独立工作流。系统会保留论文 DOI、数据集、候选 ID、源能量和 Artifact 追溯关系。该操作不会执行独立 DFT 重算，也不会产生可用于材料推荐的吸附能。',
      '确认创建文献复现输入',
      { confirmButtonText: '创建复现输入', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  isSelecting.value = true
  try {
    const response = await selectResearchBenchmarkCandidate(benchmark.value.benchmark_id, selectedCandidate.value.candidate_id)
    ElMessage.success('已创建文献复现输入')
    isDrawerOpen.value = false
    await router.push(`/app/structure-workflows/${response.data.workflow_id}`)
  } catch (error) {
    ElMessage.error(readErrorMessage(error, '创建文献复现输入失败。'))
  } finally {
    isSelecting.value = false
  }
}

async function handleImport() {
  isImporting.value = true
  try {
    await importMaterialsCloudResearchBenchmark()
    ElMessage.success('已导入已审核的 Materials Cloud 基准')
    await nextTick()
    await loadPage()
  } catch (error) {
    const status = error.response?.status
    if (status === 409) {
      ElMessage.error(mapResearchBenchmarkImportError(status, '导入文献基准失败。'))
    } else if (status === 403) {
      ElMessage.error(mapResearchBenchmarkImportError(status, '导入文献基准失败。'))
    } else {
      ElMessage.error(readErrorMessage(error, '导入文献基准失败。'))
    }
  } finally {
    isImporting.value = false
  }
}

function isSelectable(candidate) {
  return isResearchBenchmarkCandidateSelectable(candidate)
}

function compositionLabel(candidate) {
  return formatResearchBenchmarkComposition(candidate)
}

function compositionClass(candidate) {
  return isSelectable(candidate) ? 'composition-ok' : 'composition-invalid'
}

function coordinateSummary(candidate) {
  const lattice = candidate.source_metadata?.lattice_matrix_angstrom
  return Array.isArray(lattice) && lattice.length ? `后端返回晶格矩阵（${lattice.length} × ${lattice[0]?.length || 0}）` : '后端未返回坐标摘要。'
}

function formatEnergy(candidate) {
  return formatResearchBenchmarkSourceEnergy(candidate)
}

function readErrorMessage(error, fallback) {
  return error.response?.data?.detail?.message || error.response?.data?.detail || error.message || fallback
}
</script>

<style scoped>
.benchmark-page { display: grid; gap: 20px; color: var(--lz-text); }
.page-hero, .overview-card, .candidate-workbench, .overview-action, .admin-actions { border: 1px solid var(--lz-line); border-radius: 18px; background: linear-gradient(135deg, rgba(9, 27, 43, .96), rgba(7, 17, 30, .92)); box-shadow: 0 18px 48px rgba(0, 0, 0, .18); }
.page-hero { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; padding: 26px; background: radial-gradient(circle at right top, rgba(214, 171, 70, .2), transparent 35%), linear-gradient(135deg, rgba(9, 31, 51, .98), rgba(7, 17, 30, .96)); }
.eyebrow, .card-label { color: var(--lz-cyan); font-size: .75rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }.page-hero h2, .section-heading h3, .overview-action h3 { margin: 8px 0; }.page-hero p, .section-heading p, .overview-action p, .admin-actions p, .metadata-card p { margin: 0; color: var(--lz-muted); line-height: 1.6; }.scientific-boundary { --el-alert-bg-color: rgba(201, 139, 32, .12); --el-alert-border-color: rgba(223, 174, 71, .36); }.overview-grid { display: grid; grid-template-columns: 1.25fr .7fr 1fr; gap: 16px; }.overview-card { padding: 20px; min-width: 0; }.source-card h3 { margin: 8px 0 16px; font-size: 1.05rem; }.source-card dl, .drawer-details { margin: 0; display: grid; gap: 10px; }.source-card dl div, .drawer-details div { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 12px; }.source-card dt, .drawer-details dt { color: var(--lz-muted); }.source-card dd, .drawer-details dd { margin: 0; overflow-wrap: anywhere; }.source-card a { color: var(--lz-cyan); }.metric-card { display: flex; flex-direction: column; gap: 10px; }.metric-card strong { font-size: 2.55rem; line-height: 1; }.metric-card small { color: var(--lz-muted); }.metric-card .el-tag { align-self: flex-start; margin-top: auto; }.metadata-card ul { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 8px; }.metadata-card li { display: flex; justify-content: space-between; gap: 12px; color: var(--lz-muted); font-size: .84rem; }.metadata-card b { color: var(--lz-text); text-align: right; }.overview-action { padding: 24px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }.candidate-workbench { padding: 22px; display: grid; gap: 18px; }.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }.candidate-controls { display: grid; grid-template-columns: minmax(220px, 1fr) 170px auto auto; align-items: center; gap: 12px; color: var(--lz-muted); }.candidate-table { min-width: 0; border: 1px solid rgba(135, 184, 215, .22); border-radius: 12px; overflow: hidden; }.candidate-table-head, .candidate-row { display: grid; grid-template-columns: minmax(130px, 1.1fr) 86px minmax(165px, 1.25fr) minmax(160px, 1.25fr) 130px 60px; gap: 12px; align-items: center; padding: 0 16px; }.candidate-table-head { height: 46px; color: var(--lz-muted); font-size: .76rem; background: rgba(104, 177, 215, .09); }.virtual-scroll { height: 648px; overflow: auto; }.virtual-canvas { position: relative; }.virtual-rows { position: absolute; left: 0; right: 0; top: 0; }.candidate-row { height: 72px; border-top: 1px solid rgba(135, 184, 215, .12); font-size: .84rem; }.candidate-row small { display: block; margin-top: 3px; color: var(--lz-muted); font-size: .7rem; }.candidate-id, .mono { font-family: Consolas, 'SFMono-Regular', monospace; overflow-wrap: anywhere; }.composition-ok { color: #67d9b4; }.composition-invalid { color: #f2aa78; }.admin-actions { padding: 16px 20px; color: var(--lz-muted); }.admin-actions summary { cursor: pointer; color: var(--lz-text); font-weight: 700; }.drawer-details { margin: 0 0 18px; }.drawer-note { color: var(--lz-muted); line-height: 1.6; }.loading-state { padding: 28px; }.el-drawer { --el-drawer-bg-color: #091b2b; }
@media (max-width: 1100px) { .overview-grid { grid-template-columns: 1fr 1fr; }.metadata-card { grid-column: 1 / -1; }.candidate-controls { grid-template-columns: 1fr 160px; }.candidate-controls .el-checkbox, .candidate-controls > span { grid-column: auto; } }
@media (max-width: 700px) { .page-hero, .overview-action, .section-heading { flex-direction: column; }.overview-grid { grid-template-columns: 1fr; }.metadata-card { grid-column: auto; }.candidate-controls { grid-template-columns: 1fr; align-items: stretch; }.candidate-table { overflow-x: auto; }.candidate-table-head, .candidate-row { min-width: 790px; }.virtual-scroll { height: 504px; }.source-card dl div, .drawer-details div { grid-template-columns: 1fr; gap: 4px; } }
</style>
