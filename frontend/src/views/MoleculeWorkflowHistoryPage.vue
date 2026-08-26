<template>
  <div class="workflow-history-page">
    <header class="history-hero">
      <div>
        <span class="lz-kicker">任务管理</span>
        <h2>计算任务</h2>
        <p>查看正在推进、需要复核和未完成的分子计算；执行状态与质量状态始终分别保留。</p>
      </div>
      <div class="hero-actions">
        <el-button type="primary" @click="goToCreate">新建分子计算</el-button>
        <el-button :loading="isLoading" @click="refreshTasks">刷新任务</el-button>
      </div>
    </header>

    <section class="task-metrics" aria-label="任务概览">
      <article><span>{{ historyMetrics.totalLabel }}</span><strong>{{ historyMetrics.total }}</strong><small>服务端总量不等于当前页条数</small></article>
      <article><span>正在推进</span><strong>{{ historyMetrics.counts.running }}</strong><small>{{ historyMetrics.scopeLabel }}</small></article>
      <article><span>待复核</span><strong>{{ historyMetrics.counts.review }}</strong><button type="button" @click="applyQuickFilter('needs_review')">查看待复核</button></article>
      <article><span>未完成</span><strong>{{ historyMetrics.counts.failed }}</strong><button type="button" @click="applyQuickFilter('failed')">查看失败任务</button></article>
    </section>

    <section class="filter-panel" aria-label="任务筛选">
      <el-form class="filter-grid" label-position="top" @submit.prevent>
        <el-form-item label="分子名称">
          <el-input v-model="filterForm.molecule_name" aria-label="分子名称" maxlength="120" clearable placeholder="例如 LiH" @keyup.enter="applyFilters" />
        </el-form-item>
        <el-form-item label="执行状态">
          <el-select v-model="filterForm.status" aria-label="执行状态" clearable placeholder="全部执行状态">
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="质量状态">
          <el-select v-model="filterForm.validation_status" aria-label="质量状态" clearable placeholder="全部质量状态">
            <el-option label="计算通过" value="passed" />
            <el-option label="需要复核" value="needs_review" />
          </el-select>
        </el-form-item>
        <el-form-item label="每页数量">
          <el-select v-model="filterForm.page_size" aria-label="每页数量">
            <el-option :value="10" label="10 条" />
            <el-option :value="20" label="20 条" />
            <el-option :value="50" label="50 条" />
          </el-select>
        </el-form-item>
        <div class="filter-actions">
          <el-button type="primary" @click="applyFilters">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </el-form>
    </section>

    <el-alert v-if="queryIssues.length" class="history-alert" type="warning" :closable="false" show-icon>
      <template #title>筛选条件不合法</template>
      <ul><li v-for="issue in queryIssues" :key="issue">{{ issue }}</li></ul>
    </el-alert>

    <el-alert v-if="loadError" class="history-alert" type="error" :closable="false" show-icon>
      <template #title>{{ loadError.title }}</template>
      <p>{{ loadError.message }}</p>
      <div class="alert-actions">
        <el-button size="small" :loading="isLoading" @click="refreshTasks">重试</el-button>
          <el-button v-if="loadError.status === 401" size="small" @click="goToLogin">重新登录</el-button>
      </div>
    </el-alert>

    <section class="history-ledger">
      <div class="ledger-head">
        <div>
          <span class="section-label">任务队列与历史</span>
          <h3>继续处理任务</h3>
        </div>
        <div class="source-summary">
          <el-tag v-if="dataSource === 'local'" type="warning" effect="plain">本机缓存</el-tag>
          <el-tag v-else type="info" effect="plain">服务端记录</el-tag>
          <span v-if="dataSource === 'server'">服务端共 {{ pagination.total }} 条；状态计数仅覆盖当前页</span>
          <span v-else>接口不可用，未与服务端记录混合</span>
        </div>
      </div>

      <div v-if="isLoading && !items.length" class="initial-loading" role="status" aria-live="polite">
        <span class="loading-orbit" aria-hidden="true"></span>
        <span>正在加载计算任务…</span>
      </div>

      <div class="table-shell">
        <el-table
          v-loading="isLoading"
          :data="items"
          row-key="workflow_id"
          empty-text="没有符合条件的计算任务"
          class="history-table"
          @row-click="openWorkflow"
        >
          <el-table-column label="分子 / Workflow" fixed="left" min-width="238">
            <template #default="{ row }">
              <button class="workflow-cell" type="button" @click.stop="openWorkflow(row)">
                <strong>{{ row.molecule_name || '—' }}</strong>
                <span class="mono">{{ row.workflow_id }}</span>
              </button>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="168">
            <template #default="{ row }">{{ formatTimestamp(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="110">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="执行状态" width="112">
            <template #default="{ row }">
              <el-tag :type="executionMeta(row.status).type" effect="plain">{{ executionMeta(row.status).label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="质量状态" width="122">
            <template #default="{ row }">
              <el-tag :type="validationMeta(row.validation_status).type" effect="plain">{{ validationMeta(row.validation_status).label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="优化器" width="110">
            <template #default="{ row }">{{ formatValue(row.optimizer_name) }}</template>
          </el-table-column>
          <el-table-column label="Qubits" width="92" align="right">
            <template #default="{ row }">{{ formatValue(row.qubit_count) }}</template>
          </el-table-column>
          <el-table-column label="Pauli 项数" width="112" align="right">
            <template #default="{ row }">{{ formatValue(row.pauli_term_count) }}</template>
          </el-table-column>
          <el-table-column label="VQE 能量 (Ha)" min-width="150" align="right">
            <template #default="{ row }"><span class="mono number">{{ formatEnergy(row.vqe_energy_hartree) }}</span></template>
          </el-table-column>
          <el-table-column label="分布式能量 (Ha)" min-width="160" align="right">
            <template #default="{ row }"><span class="mono number">{{ formatEnergy(row.distributed_energy_hartree) }}</span></template>
          </el-table-column>
          <el-table-column label="能量误差 (Ha)" min-width="150" align="right">
            <template #default="{ row }"><span class="mono number">{{ formatEnergy(row.absolute_error_hartree) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="dataSource === 'server' && pagination.total_pages > 0" class="pagination-row">
        <span>第 {{ pagination.page }} / {{ pagination.total_pages }} 页</span>
        <el-pagination
          background
          :current-page="pagination.page"
          :page-size="pagination.page_size"
          :total="pagination.total"
          layout="prev, pager, next"
          @current-change="changePage"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  canUseMoleculeWorkflowLocalFallback,
  formatMoleculeWorkflowHistoryValue,
  listMoleculeWorkflows,
  moleculeWorkflowExecutionMeta,
  moleculeWorkflowValidationMeta,
  normalizeMoleculeWorkflowHistoryError,
  normalizeMoleculeWorkflowHistoryQuery,
} from '../services/moleculeWorkflowService'
import { readRecentMoleculeWorkflows } from '../services/moleculeWorkflowStorage'
import { summarizeHistoryMetrics } from '../services/productExperienceService.js'

const route = useRoute()
const router = useRouter()
const filterForm = reactive({ molecule_name: '', status: '', validation_status: '', page_size: 20 })
const items = ref([])
const pagination = reactive({ page: 1, page_size: 20, total: 0, total_pages: 0 })
const isLoading = ref(false)
const loadError = ref(null)
const queryIssues = ref([])
const dataSource = ref('server')
const retainedQueryIssues = ref([])
let requestVersion = 0
const historyMetrics = computed(() => summarizeHistoryMetrics({ items: items.value, total: pagination.total, dataSource: dataSource.value }))

function toRouteQuery(filters) {
  const query = { page: String(filters.page), page_size: String(filters.page_size) }
  if (filters.molecule_name) query.molecule_name = filters.molecule_name
  if (filters.status) query.status = filters.status
  if (filters.validation_status) query.validation_status = filters.validation_status
  return query
}

function sameQuery(left, right) {
  const leftParams = new URLSearchParams(left)
  const rightParams = new URLSearchParams(right)
  leftParams.sort()
  rightParams.sort()
  return leftParams.toString() === rightParams.toString()
}

function syncForm(filters) {
  filterForm.molecule_name = filters.molecule_name || ''
  filterForm.status = filters.status || ''
  filterForm.validation_status = filters.validation_status || ''
  filterForm.page_size = filters.page_size
}

function localFallbackItems() {
  return readRecentMoleculeWorkflows().slice(0, 10).map(item => ({
    workflow_id: item.workflowId,
    molecule_name: item.moleculeName,
    created_at: item.completedAt,
    completed_at: item.completedAt,
    duration_ms: null,
    status: 'completed',
    validation_status: item.validationStatus,
    optimizer_name: null,
    qubit_count: null,
    pauli_term_count: null,
    vqe_energy_hartree: null,
    distributed_energy_hartree: null,
    absolute_error_hartree: null,
  }))
}

async function loadHistory(filters) {
  const version = ++requestVersion
  isLoading.value = true
  loadError.value = null
  try {
    const response = await listMoleculeWorkflows(filters)
    if (version !== requestVersion) return
    items.value = Array.isArray(response?.items) ? response.items : []
    pagination.page = Number(response?.page) || filters.page
    pagination.page_size = Number(response?.page_size) || filters.page_size
    pagination.total = Number(response?.total) || 0
    pagination.total_pages = Number(response?.total_pages) || 0
    dataSource.value = 'server'
  } catch (error) {
    if (version !== requestVersion) return
    loadError.value = normalizeMoleculeWorkflowHistoryError(error)
    if (!items.value.length && canUseMoleculeWorkflowLocalFallback(error)) {
      items.value = localFallbackItems()
      dataSource.value = 'local'
    }
  } finally {
    if (version === requestVersion) isLoading.value = false
  }
}

async function restoreFromRoute() {
  const normalized = normalizeMoleculeWorkflowHistoryQuery(route.query)
  syncForm(normalized.filters)
  const canonicalQuery = toRouteQuery(normalized.filters)
  if (normalized.issues.length) {
    retainedQueryIssues.value = normalized.issues
    queryIssues.value = normalized.issues
    if (!sameQuery(route.query, canonicalQuery)) {
      await router.replace({ query: canonicalQuery })
      return
    }
  } else if (retainedQueryIssues.value.length) {
    queryIssues.value = retainedQueryIssues.value
    retainedQueryIssues.value = []
  } else {
    queryIssues.value = []
  }
  await loadHistory(normalized.filters)
}

function applyFilters() {
  router.push({
    query: toRouteQuery({
      page: 1,
      page_size: filterForm.page_size,
      ...(filterForm.molecule_name.trim() ? { molecule_name: filterForm.molecule_name.trim() } : {}),
      ...(filterForm.status ? { status: filterForm.status } : {}),
      ...(filterForm.validation_status ? { validation_status: filterForm.validation_status } : {}),
    }),
  })
}

function resetFilters() {
  retainedQueryIssues.value = []
  router.push({ query: { page: '1', page_size: '20' } })
}

function applyQuickFilter(kind) {
  const filters = {
    page: 1,
    page_size: filterForm.page_size,
    ...(filterForm.molecule_name.trim() ? { molecule_name: filterForm.molecule_name.trim() } : {}),
  }
  if (kind === 'needs_review') filters.validation_status = 'needs_review'
  if (kind === 'failed') filters.status = 'failed'
  router.push({ query: toRouteQuery(filters) })
}

function goToCreate() { router.push('/app/molecules') }
function goToLogin() { router.push('/auth?tab=login') }

function changePage(page) {
  const { filters } = normalizeMoleculeWorkflowHistoryQuery(route.query)
  router.push({ query: toRouteQuery({ ...filters, page }) })
}

function refreshTasks() {
  const { filters } = normalizeMoleculeWorkflowHistoryQuery(route.query)
  loadHistory(filters)
}

function openWorkflow(row) {
  if (row?.workflow_id) router.push(`/app/molecule-workflows/${encodeURIComponent(row.workflow_id)}`)
}

function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium' }).format(date)
}

function formatDuration(value) {
  if (value === null || value === undefined || value === '') return '—'
  const duration = Number(value)
  if (!Number.isFinite(duration)) return '—'
  return duration < 1000 ? `${Math.round(duration)} ms` : `${(duration / 1000).toFixed(2)} s`
}

const formatValue = value => formatMoleculeWorkflowHistoryValue(value)
const formatEnergy = value => formatMoleculeWorkflowHistoryValue(value, { digits: 8 })
const executionMeta = status => moleculeWorkflowExecutionMeta(status)
const validationMeta = status => moleculeWorkflowValidationMeta(status)

watch(() => route.fullPath, restoreFromRoute)
onMounted(restoreFromRoute)
</script>

<style scoped>
.workflow-history-page { width:100%; min-width:0; max-width:100%; display: grid; gap: 20px; }
.history-hero, .ledger-head, .source-summary, .hero-actions, .pagination-row, .alert-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.history-hero { min-height: 170px; padding: 30px 34px; border: 1px solid var(--lz-line); background: #e7eae4; }
.history-hero h2 { margin: 12px 0 8px; font-size: clamp(2rem, 4vw, 4rem); line-height: .95; letter-spacing: -.055em; }
.history-hero p { max-width: 760px; margin: 0; color: var(--lz-muted); line-height: 1.65; }
.hero-actions { justify-content: flex-end; }
.task-metrics{min-width:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;border:1px solid var(--lz-line);background:var(--lz-line)}.task-metrics article{min-width:0;min-height:118px;padding:18px 20px;display:grid;align-content:space-between;gap:8px;background:var(--lz-panel)}.task-metrics span,.task-metrics small{color:var(--lz-muted);font-size:.72rem;overflow-wrap:anywhere}.task-metrics strong{font:700 1.75rem/1 var(--lz-mono)}.task-metrics button{width:max-content;max-width:100%;padding:0;border:0;background:transparent;color:var(--lz-accent-deep);font:700 .74rem var(--lz-body);cursor:pointer}.task-metrics button:focus-visible{outline:2px solid var(--lz-accent);outline-offset:3px}
.history-hero,.task-metrics,.filter-panel, .history-ledger { min-width:0; max-width:100%; box-sizing:border-box; }.filter-panel, .history-ledger { border: 1px solid var(--lz-line); border-radius: 0; background: #fff; box-shadow: none; }
.filter-panel { padding: 18px 20px 4px; }
.filter-grid { display: grid; grid-template-columns: minmax(190px, 1.4fr) repeat(3, minmax(150px, 1fr)) auto; gap: 14px; align-items: end; }
.filter-grid :deep(.el-form-item) { margin-bottom: 14px; }
.filter-grid :deep(.el-select) { width: 100%; }
.filter-actions { padding-bottom: 14px; display: flex; gap: 8px; }
.history-alert :deep(.el-alert__content) { width: 100%; }
.history-alert p { margin: 6px 0; }
.history-alert ul { margin: 7px 0 0; padding-left: 20px; }
.alert-actions { margin-top: 10px; justify-content: flex-start; }
.history-ledger { overflow: hidden; }
.ledger-head { padding: 18px 20px; border-bottom: 1px solid var(--lz-line); }
.ledger-head h3 { margin: 4px 0 0; }
.section-label { color: var(--lz-cyan); font: 700 .67rem ui-monospace, monospace; letter-spacing: .1em; text-transform: uppercase; }
.source-summary { justify-content: flex-end; color: var(--lz-muted); font-size: .8rem; }
.table-shell { overflow-x: auto; }
.initial-loading { padding: 18px 20px; border-bottom: 1px solid var(--lz-line); display: flex; align-items: center; gap: 10px; color: var(--lz-muted); font-size: .84rem; }
.loading-orbit { width: 15px; height: 15px; border: 2px solid rgba(52, 214, 255, .22); border-top-color: var(--lz-cyan); border-radius: 50%; animation: history-spin .85s linear infinite; }
.history-table { min-width: 1560px; cursor: pointer; }
.history-table :deep(.el-table__inner-wrapper::before) { background: var(--lz-line); }
.history-table :deep(.el-table__row:hover > td.el-table__cell) { background: rgba(52, 214, 255, .07); }
.workflow-cell { width: 100%; padding: 0; border: 0; display: grid; gap: 5px; text-align: left; background: transparent; color: inherit; cursor: pointer; }
.workflow-cell strong { color: var(--lz-text); font-size: .95rem; }
.workflow-cell span { color: var(--lz-cyan); font-size: .73rem; overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.number { color: #27332d; font-size: .78rem; }
.pagination-row { padding: 16px 20px; border-top: 1px solid var(--lz-line); color: var(--lz-muted); font-size: .8rem; }
@keyframes history-spin { to { transform: rotate(360deg); } }
@media (max-width: 1180px) { .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .filter-actions { align-self: end; } }
@media (max-width: 720px) { .history-hero, .ledger-head, .pagination-row { align-items: flex-start; flex-direction: column; } .hero-actions { width: 100%; justify-content: flex-start; } .task-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-grid { grid-template-columns: 1fr; } .source-summary { justify-content: flex-start; flex-wrap: wrap; } }
</style>
