<template>
  <div class="workbench-page workspace-page">
    <header class="workbench-hero page-heading">
      <div>
        <span class="eyebrow">MOLECULAR COMPUTE WORKBENCH</span>
        <h2>把注意力留给<br><em>下一项分子计算。</em></h2>
        <p>从一个固定分子开始，持续查看任务状态、质量信号与可追溯结果。</p>
      </div>
      <div class="workbench-hero-actions">
        <el-button type="primary" size="large" @click="goTo('/app/molecules')">新建分子计算</el-button>
        <el-button @click="goTo('/app/molecule-workflows')">查看全部任务</el-button>
        <el-button data-testid="copilot-choose-task" text @click="askCopilotToChoose">我不懂，帮我选择计算方式</el-button>
      </div>
    </header>

    <section class="execution-boundary" aria-label="计算执行边界">
      <span class="boundary-dot" aria-hidden="true"></span>
      <div><strong>逻辑虚拟 QPU 模拟</strong><span>非真实 QPU</span></div>
      <details>
        <summary>查看执行字段</summary>
        <code>execution_mode=logical_virtual_qpu · is_real_qpu=false</code>
      </details>
    </section>

    <el-alert v-if="loadError" type="warning" :closable="false" show-icon>
      <template #title>最近任务暂时不可用</template>
      <p>工作台不会用未知数据替代服务端任务。{{ loadError }}</p>
      <el-button size="small" @click="loadTasks">重试</el-button>
    </el-alert>

    <template v-else>
      <section class="workbench-metrics" aria-label="任务概览">
        <article><span>最近任务</span><strong>{{ summary.total }}</strong><small>最近读取的 Workflow</small></article>
        <article><span>正在推进</span><strong>{{ summary.running }}</strong><small>已排队或计算中的任务</small></article>
        <article><span>待复核</span><strong>{{ summary.review }}</strong><small>需要先检查质量证据</small></article>
      </section>

      <section v-if="loading" class="workbench-panel loading-panel" role="status">正在读取你的任务…</section>

      <section v-else-if="!summary.total" class="workbench-empty workbench-panel">
        <span class="eyebrow">FIRST WORKFLOW</span>
        <h3>还没有分子计算。</h3>
        <p>默认配置已经准备好。选择分子并确认固定几何，即可创建第一项逻辑虚拟 QPU 模拟任务。</p>
        <el-button type="primary" @click="goTo('/app/molecules')">开始第一项计算</el-button>
      </section>

      <div v-else class="workbench-grid">
        <section class="workbench-panel recent-tasks" aria-labelledby="recent-tasks-title">
          <header class="panel-heading">
            <div><span class="eyebrow">RECENT ACTIVITY</span><h3 id="recent-tasks-title">最近任务</h3></div>
            <router-link to="/app/molecule-workflows">全部记录</router-link>
          </header>
          <div class="task-list">
            <router-link v-for="task in summary.recent" :key="task.workflow_id" :to="`/app/molecule-workflows/${encodeURIComponent(task.workflow_id)}`" class="task-row">
              <div><strong>{{ task.molecule_name || '未命名分子' }}</strong><small>{{ task.workflow_id }}</small></div>
              <div class="task-state"><span :class="['status-dot', taskStatus(task.status).tone]"></span><strong>{{ taskStatus(task.status).label }}</strong><small>{{ validationLabel(task.validation_status) }}</small></div>
            </router-link>
          </div>
        </section>

        <aside class="workbench-panel review-panel" aria-labelledby="review-title">
          <span class="eyebrow">QUALITY QUEUE</span>
          <h3 id="review-title">先处理待复核结果</h3>
          <p v-if="summary.review">有 {{ summary.review }} 项任务保留了结果，但不应直接视为可靠结论。</p>
          <p v-else>最近任务没有标记为待复核的结果。</p>
          <el-button text @click="goTo('/app/molecule-workflows')">打开任务记录 →</el-button>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listMoleculeWorkflows } from '../services/moleculeWorkflowService'
import { summarizeWorkbenchTasks, workflowStatusMeta } from '../services/workbenchService'
import { readUser } from '../services/authStorage'
import { createCopilotSelectionDraft, savePendingCopilotDraft } from '../services/assistantCopilotContext'

const tasks = ref([])
const loading = ref(false)
const loadError = ref('')
const summary = computed(() => summarizeWorkbenchTasks(tasks.value))
const router = useRouter()

const taskStatus = status => workflowStatusMeta(status)
const validationLabel = status => ({ passed: '质量验证通过', needs_review: '需要复核', failed: '质量验证未通过' }[status] || '质量待确认')
const goTo = path => router.push(path)
function askCopilotToChoose() {
  if (savePendingCopilotDraft(readUser(), createCopilotSelectionDraft())) router.push('/app/copilot')
}

async function loadTasks() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await listMoleculeWorkflows({ page: 1, page_size: 6 })
    tasks.value = Array.isArray(response?.items) ? response.items : []
  } catch {
    tasks.value = []
    loadError.value = '请稍后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.workbench-page{display:grid;gap:18px}.workbench-hero{min-height:262px;display:flex;align-items:end;justify-content:space-between;gap:36px;background:#f8f9f6}.workbench-hero h2{margin:12px 0;font:600 clamp(2.5rem,5.2vw,5.25rem)/.98 var(--lz-display);letter-spacing:-.065em}.workbench-hero h2 em{color:var(--lz-accent);font-style:normal}.workbench-hero p{max-width:590px;margin:0;color:var(--lz-muted);line-height:1.7}.workbench-hero-actions{display:flex;flex-wrap:wrap;gap:10px}.execution-boundary{min-height:44px;padding:10px 14px;border:1px solid var(--lz-line);display:flex;align-items:center;gap:11px;background:var(--lz-panel);color:var(--lz-muted);font:.72rem var(--lz-mono)}.execution-boundary>div{display:flex;align-items:center;gap:10px;min-width:0}.execution-boundary strong{color:var(--lz-text);white-space:nowrap}.execution-boundary>div span{color:var(--lz-muted);white-space:nowrap}.execution-boundary details{margin-left:auto}.execution-boundary summary{cursor:pointer;color:var(--lz-accent-deep);font-weight:700;white-space:nowrap}.execution-boundary code{display:block;margin-top:9px;color:var(--lz-muted);font:.68rem var(--lz-mono);white-space:nowrap}.boundary-dot{width:8px;height:8px;flex:0 0 8px;border-radius:50%;background:var(--lz-accent)}.workbench-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;border:1px solid var(--lz-line);background:var(--lz-line)}.workbench-metrics article{min-height:124px;padding:20px 22px;display:grid;align-content:space-between;background:var(--lz-panel)}.workbench-metrics span,.workbench-metrics small{color:var(--lz-muted);font-size:.75rem}.workbench-metrics strong{font:600 2rem/1 var(--lz-mono);color:var(--lz-text)}.workbench-panel{min-width:0;border:1px solid var(--lz-line);background:var(--lz-panel)}.loading-panel{min-height:180px;padding:26px;color:var(--lz-muted)}.workbench-empty{min-height:270px;padding:42px;display:grid;align-content:center;justify-items:start}.workbench-empty h3{margin:10px 0;font-size:1.7rem}.workbench-empty p{max-width:560px;margin:0 0 22px;color:var(--lz-muted);line-height:1.7}.workbench-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(260px,.7fr);gap:18px}.panel-heading{padding:20px 22px;border-bottom:1px solid var(--lz-line);display:flex;align-items:end;justify-content:space-between;gap:16px}.panel-heading h3,.review-panel h3{margin:7px 0 0;font-size:1.22rem}.panel-heading a{color:var(--lz-accent-deep);font-size:.78rem;text-decoration:none}.task-list{display:grid}.task-row{min-height:72px;padding:14px 22px;border-bottom:1px solid var(--lz-line-soft);display:flex;align-items:center;justify-content:space-between;gap:16px;color:inherit;text-decoration:none}.task-row:last-child{border-bottom:0}.task-row:hover,.task-row:focus-visible{background:var(--lz-bg-soft)}.task-row>div:first-child{min-width:0;display:grid;gap:5px}.task-row strong{font-size:.88rem}.task-row small{color:var(--lz-muted);font: .68rem var(--lz-mono);overflow-wrap:anywhere}.task-state{display:grid;grid-template-columns:auto auto;gap:5px 7px;align-items:center;text-align:right}.task-state small{grid-column:1 / -1}.status-dot{width:7px;height:7px;border-radius:50%;background:#879087}.status-dot.running{background:var(--lz-running)}.status-dot.completed{background:var(--lz-completed)}.status-dot.partial{background:var(--lz-partial)}.status-dot.failed{background:var(--lz-failed)}.review-panel{padding:22px;display:grid;align-content:start;gap:12px;background:#faf8f1}.review-panel p{margin:0;color:var(--lz-muted);line-height:1.65;font-size:.82rem}.review-panel :deep(.el-button){padding-left:0;color:var(--lz-accent-deep)}@media(max-width:780px){.workbench-hero{min-height:0;align-items:flex-start;flex-direction:column}.workbench-metrics,.workbench-grid{grid-template-columns:1fr}.workbench-hero-actions{width:100%}.task-row{align-items:flex-start;flex-direction:column}.task-state{text-align:left}.execution-boundary{align-items:flex-start;flex-wrap:wrap}.execution-boundary>div{width:calc(100% - 20px);display:grid;gap:2px}.execution-boundary details{width:100%;margin-left:20px}.execution-boundary code{white-space:normal;overflow-wrap:anywhere}}
</style>
