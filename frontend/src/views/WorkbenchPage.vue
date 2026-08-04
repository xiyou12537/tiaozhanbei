<template>
  <div class="workbench-page">
    <section class="workbench-hero">
      <div class="hero-copy">
        <span class="panel-kicker">Screening Workbench</span>
        <h2>候选材料筛选工作台</h2>
      </div>

      <div class="hero-actions">
        <div class="status-chip" :class="workflowState.workflowStatus">
          <span></span>
          {{ workflowStatusLabel }}
        </div>
        <el-button :loading="refreshing" :disabled="!workflowState.workflowId" @click="handleRefresh">
          刷新
        </el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreateWorkflow">
          创建工作流
        </el-button>
      </div>
    </section>

    <section class="metric-grid">
      <article class="metric-card">
        <span>当前材料</span>
        <strong><ChemicalFormula :text="workflowState.selectedCandidate || '--'" /></strong>
        <small>{{ currentCandidate?.family || '等待选择候选材料' }}</small>
      </article>
      <article class="metric-card">
        <span>工作流编号</span>
        <strong class="mono">{{ shortWorkflowId }}</strong>
        <small>{{ workflowState.workflowId ? '已创建，可继续跟踪' : '创建后自动生成' }}</small>
      </article>
      <article class="metric-card">
        <span>当前阶段</span>
        <strong>{{ currentStageTitle }}</strong>
        <small>{{ cleanProgressText }}</small>
      </article>
      <article class="metric-card accent">
        <span>综合评分</span>
        <strong>{{ finalScoreText }}</strong>
        <small>{{ scoreNote }}</small>
      </article>
    </section>

    <div class="workbench-grid">
      <aside class="left-rail">
        <section class="surface-panel setup-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Task Setup</span>
              <h3>任务配置</h3>
            </div>
            <el-tag size="small" effect="plain" :type="workflowState.apiReady ? 'success' : 'warning'">
              {{ workflowState.apiReady ? '接口已连接' : '演示数据' }}
            </el-tag>
          </div>

          <div class="field-list">
            <label class="field">
              <span>预置案例</span>
              <el-select v-model="workflowState.selectedCaseId" placeholder="选择案例" filterable>
                <el-option
                  v-for="item in workflowState.cases"
                  :key="item.id"
                  :label="toSubscriptFormula(item.title)"
                  :value="item.id"
                />
              </el-select>
            </label>

            <label class="field">
              <span>候选材料</span>
              <el-select v-model="workflowState.selectedCandidate" placeholder="选择材料" filterable>
                <el-option
                  v-for="item in workflowState.candidates"
                  :key="item.name"
                  :label="toSubscriptFormula(item.name)"
                  :value="item.name"
                />
              </el-select>
            </label>

            <label class="field">
              <span>执行模式</span>
              <el-segmented v-model="workflowState.executionMode" :options="executionModeOptions" />
            </label>

            <label class="field">
              <span>QASM 工件（可选）</span>
              <el-input
                v-model="workflowState.qasmContent"
                type="textarea"
                :rows="4"
                resize="none"
                placeholder="当前材料筛选主流程可不上传 QASM；需要联动编译能力页时再填写。"
              />
            </label>
          </div>

          <div class="setup-actions">
            <el-button type="primary" :loading="submitting" @click="handleCreateWorkflow">
              启动筛选
            </el-button>
            <el-button :disabled="!workflowState.pollingActive" @click="clearPolling">
              停止轮询
            </el-button>
            <el-button type="danger" plain :disabled="!canCancel" :loading="cancelling" @click="handleCancel">
              取消任务
            </el-button>
          </div>
        </section>

        <section class="surface-panel">
          <div class="panel-heading compact">
            <div>
              <span class="panel-kicker panel-kicker-dark">Pipeline</span>
              <h3>流程导航</h3>
            </div>
          </div>

          <div class="step-list">
            <button
              v-for="item in flowSteps"
              :key="item.key"
              class="step-item"
              :class="[item.status, { active: selectedStepKey === item.key }]"
              @click="selectedStepKey = item.key"
            >
              <span class="step-index">{{ item.index }}</span>
              <span class="step-main">
                <strong>{{ item.title }}</strong>
                <small>{{ item.summary }}</small>
              </span>
              <span class="step-state">{{ statusLabel(item.status) }}</span>
            </button>
          </div>
        </section>
      </aside>

      <main class="main-workspace">
        <section class="surface-panel focus-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Current Stage</span>
              <h3>{{ activeStep.title }}</h3>
            </div>
            <el-tag size="small" :type="activeStepTagType">
              {{ statusLabel(activeStep.status) }}
            </el-tag>
          </div>

          <p class="stage-description">{{ activeStep.detail }}</p>

          <div class="stage-card-grid">
            <article v-for="item in activeStepCards" :key="item.label" class="stage-card">
              <span>{{ item.label }}</span>
              <strong><ChemicalFormula :text="item.value" /></strong>
              <small>{{ item.note }}</small>
            </article>
          </div>
        </section>

        <section class="surface-panel execution-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Execution</span>
              <h3>执行概览</h3>
            </div>
            <router-link class="inline-link" to="/app/results">查看完整结果</router-link>
          </div>

          <div class="execution-grid">
            <div class="progress-block">
              <span>总体进度</span>
              <strong>{{ workflowState.progressPercent }}%</strong>
              <el-progress :percentage="workflowState.progressPercent" :stroke-width="9" />
            </div>
            <div class="result-block">
              <span>推荐结论</span>
              <strong>{{ resultHeadline }}</strong>
              <small>{{ resultSubline }}</small>
            </div>
            <div class="result-block">
              <span>拓扑/执行</span>
              <strong>{{ topologyText }}</strong>
              <small>{{ executionStateLabel }}</small>
            </div>
          </div>
        </section>

        <section class="surface-panel log-panel">
          <div class="panel-heading compact">
            <div>
              <span class="panel-kicker panel-kicker-dark">Events</span>
              <h3>任务日志</h3>
            </div>
          </div>

          <div v-if="warningMessages.length" class="warning-stack">
            <div v-for="item in warningMessages" :key="item" class="warning-card">
              {{ item }}
            </div>
          </div>

          <div v-if="workflowState.eventLogs.length" class="log-list">
            <article v-for="item in visibleEventLogs" :key="item.index" class="log-item">
              <span class="log-index">#{{ item.index }}</span>
              <div>
                <strong>{{ item.eventType }}</strong>
                <small>{{ cleanStageTitle(item.stageName) }}</small>
                <p>{{ formatPayload(item.payload) }}</p>
              </div>
            </article>
          </div>

          <div v-else class="empty-state">
            <strong>暂无任务日志</strong>
            <p>创建工作流后，这里会显示阶段调度、执行状态和结果聚合事件。</p>
          </div>
        </section>
      </main>
    </div>

    <section class="surface-panel assistant-shell">
      <div class="assistant-summary">
        <div>
          <span class="panel-kicker panel-kicker-dark">Assistant</span>
          <h3>任务问答</h3>
        </div>
        <el-button @click="isResearchAssistantOpen = !isResearchAssistantOpen">
          {{ isResearchAssistantOpen ? '收起问答' : '展开问答' }}
        </el-button>
      </div>

      <AssistantPanel
        v-if="isResearchAssistantOpen"
        class="assistant-panel-inner"
        kicker="Research Assistant"
        title="当前任务问答"
        description="围绕当前阶段、候选材料和结果指标进行追问。"
        placeholder="输入关于当前材料、阶段或结果的问题..."
        :quickQuestions="assistantQuickQuestions"
        :helperCards="assistantCards"
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AssistantPanel from '../components/AssistantPanel.vue'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import { useWorkflow } from '../composables/useWorkflow'

const SUBSCRIPT_DIGIT_MAP = {
  0: '₀',
  1: '₁',
  2: '₂',
  3: '₃',
  4: '₄',
  5: '₅',
  6: '₆',
  7: '₇',
  8: '₈',
  9: '₉',
  x: 'ₓ',
}

function toSubscriptFormula(value) {
  return String(value ?? '').replace(/([A-Z][a-z]?)(\d+|x)/g, (_, elementSymbol, subscriptValue) => {
    const subscriptText = String(subscriptValue)
      .split('')
      .map(character => SUBSCRIPT_DIGIT_MAP[character] || character)
      .join('')
    return `${elementSymbol}${subscriptText}`
  })
}

const STAGE_TITLE_MAP = {
  created: '任务创建',
  screening: '候选粗筛',
  chem_modeling: '化学建模',
  quantum_encoding: '量子编码',
  distributed_compiling: '分布式编译',
  simulation_evaluating: '仿真评估',
  scoring: '综合评分',
  aggregating: '结果聚合',
  completed: '任务完成',
  cancelled: '已取消',
  failed: '执行失败',
}

const executionModeOptions = [
  { label: '异步 queued', value: 'queued' },
  { label: '同步 sync', value: 'sync' },
]

const selectedStepKey = ref('materials')
const submitting = ref(false)
const refreshing = ref(false)
const cancelling = ref(false)
const isResearchAssistantOpen = ref(false)

const {
  workflowState,
  currentCase,
  currentCandidate,
  loadBootstrap,
  createWorkflow,
  refreshWorkflowBundle,
  stopWorkflow,
  clearPolling,
} = useWorkflow()

onMounted(() => {
  loadBootstrap()
})

watch(
  () => workflowState.currentStage,
  value => {
    const routeMap = {
      created: 'materials',
      screening: 'screening',
      chem_modeling: 'quantum',
      quantum_encoding: 'quantum',
      distributed_compiling: 'execution',
      simulation_evaluating: 'execution',
      scoring: 'scoring',
      aggregating: 'results',
      completed: 'results',
    }
    if (routeMap[value]) selectedStepKey.value = routeMap[value]
  },
  { immediate: true }
)

const workflowStatusLabel = computed(() => {
  const labelMap = {
    idle: '等待创建',
    created: '任务已创建',
    screening: '候选粗筛中',
    chem_modeling: '化学建模中',
    quantum_encoding: '量子编码中',
    distributed_compiling: '分布式编译中',
    simulation_evaluating: '仿真评估中',
    scoring: '综合评分中',
    aggregating: '结果聚合中',
    completed: '已完成',
    cancelled: '已取消',
    failed: '执行失败',
  }
  return labelMap[workflowState.workflowStatus] || '等待创建'
})

const shortWorkflowId = computed(() => {
  if (!workflowState.workflowId) return '--'
  return workflowState.workflowId.slice(0, 8)
})

const currentStageTitle = computed(() => cleanStageTitle(workflowState.currentStage))
const cleanProgressText = computed(() => {
  if (!workflowState.workflowId) return '等待创建筛选任务'
  if (workflowState.workflowStatus === 'completed') return '全部阶段已完成'
  if (workflowState.workflowStatus === 'cancelled') return '任务已取消'
  return `执行中：${currentStageTitle.value}`
})

const canCancel = computed(() => {
  return !!workflowState.workflowId && !['completed', 'cancelled'].includes(workflowState.workflowStatus)
})

const resultSummary = computed(() => workflowState.resultView?.summary || workflowState.resultSummary?.summary || {})
const scientificSnapshot = computed(() => workflowState.resultView?.scientificSnapshot || {})
const finalScoreText = computed(() => resultSummary.value.final_score ?? '--')
const scoreNote = computed(() => {
  if (resultSummary.value.gatekeeping_passed === true) return '已通过门控'
  if (resultSummary.value.gatekeeping_passed === false) return '建议谨慎评估'
  return '等待评分阶段完成'
})
const topologyText = computed(() => workflowState.resultView?.artifacts?.topology_name || workflowState.artifacts?.topology_name || '等待推荐')
const resultHeadline = computed(() => {
  if (resultSummary.value.final_score != null) return `FinalScore ${resultSummary.value.final_score}`
  return '等待结果生成'
})
const resultSubline = computed(() => {
  if (resultSummary.value.rank_position != null) return `当前推荐排名 #${resultSummary.value.rank_position}`
  return workflowState.resultView ? '已生成结果视图' : '流程完成后自动展示推荐结论'
})
const executionStateLabel = computed(() => {
  const compiling = workflowState.stageRuns.distributed_compiling
  if (compiling === 'success') return '编译与执行评估已完成'
  if (compiling === 'running') return '正在执行分布式编译'
  if (compiling === 'failed') return '分布式执行失败'
  return '等待执行阶段'
})

const warningMessages = computed(() => {
  const messages = []
  if (workflowState.bootstrapError) {
    messages.push('平台工作流接口暂时不可用，工作台已切换为演示数据。')
  }
  if (workflowState.lastError) {
    messages.push('最近一次工作流请求失败，请确认后端已启动后重试。')
  }
  return messages
})

const visibleEventLogs = computed(() => workflowState.eventLogs.slice(-6).reverse())

const flowSteps = computed(() => [
  {
    key: 'materials',
    index: '01',
    title: '材料选择',
    status: workflowState.selectedCandidate ? 'completed' : 'pending',
    summary: '选择案例、候选材料和执行模式',
  },
  {
    key: 'screening',
    index: '02',
    title: '候选粗筛',
    status: normalizeStatus(workflowState.stageRuns.screening),
    summary: '生成候选上下文和门控判断',
  },
  {
    key: 'quantum',
    index: '03',
    title: '量子任务生成',
    status: normalizeStatus(workflowState.stageRuns.quantum_encoding || workflowState.stageRuns.chem_modeling),
    summary: '完成化学建模和量子编码',
  },
  {
    key: 'execution',
    index: '04',
    title: '分布式执行',
    status: normalizeStatus(workflowState.stageRuns.distributed_compiling || workflowState.stageRuns.simulation_evaluating),
    summary: '完成分区、映射和仿真评估',
  },
  {
    key: 'scoring',
    index: '05',
    title: '综合评分',
    status: normalizeStatus(workflowState.stageRuns.scoring),
    summary: resultSummary.value.final_score != null ? `FinalScore ${resultSummary.value.final_score}` : '计算最终推荐依据',
  },
  {
    key: 'results',
    index: '06',
    title: '结果查看',
    status: workflowState.resultView ? 'completed' : normalizeStatus(workflowState.stageRuns.aggregating),
    summary: workflowState.resultView ? '结果视图已生成' : '等待聚合输出',
  },
])

const activeStep = computed(() => {
  const map = {
    materials: {
      title: '材料选择与任务配置',
      status: flowSteps.value[0].status,
      detail: '',
    },
    screening: {
      title: '候选粗筛',
      status: flowSteps.value[1].status,
      detail: '',
    },
    quantum: {
      title: '化学建模与量子编码',
      status: flowSteps.value[2].status,
      detail: '',
    },
    execution: {
      title: '分布式编译与仿真评估',
      status: flowSteps.value[3].status,
      detail: '',
    },
    scoring: {
      title: '综合评分',
      status: flowSteps.value[4].status,
      detail: '',
    },
    results: {
      title: '结果输出',
      status: flowSteps.value[5].status,
      detail: '',
    },
  }
  return map[selectedStepKey.value] || map.materials
})

const activeStepTagType = computed(() => {
  if (activeStep.value.status === 'completed') return 'success'
  if (activeStep.value.status === 'running') return 'warning'
  if (activeStep.value.status === 'failed') return 'danger'
  return 'info'
})

const activeStepCards = computed(() => {
  const cards = {
    materials: [
      { label: '预置案例', value: currentCase.value?.title || '--', note: '' },
      { label: '候选材料', value: workflowState.selectedCandidate || '--', note: currentCandidate.value?.note || '等待选择' },
      { label: '执行模式', value: workflowState.executionMode, note: workflowState.executionMode === 'queued' ? '异步推进，适合真实联调' : '同步返回，适合快速演示' },
      { label: '吸附强度', value: currentCandidate.value?.adsorptionStrength ?? '--', note: '' },
    ],
    screening: [
      { label: '阶段状态', value: statusLabel(flowSteps.value[1].status), note: serviceNote('screening') },
      { label: '候选家族', value: currentCandidate.value?.family || '--', note: '' },
      { label: '门控结论', value: gatekeepingText.value, note: '' },
      { label: '日志数量', value: String(workflowState.eventLogs.length), note: '' },
    ],
    quantum: [
      { label: '化学建模', value: statusLabel(normalizeStatus(workflowState.stageRuns.chem_modeling)), note: serviceNote('chem_modeling') },
      { label: '量子编码', value: statusLabel(normalizeStatus(workflowState.stageRuns.quantum_encoding)), note: serviceNote('quantum_encoding') },
      { label: 'QASM 输入', value: workflowState.qasmContent ? '已填写' : '未填写', note: '' },
      { label: '量子比特数', value: scientificSnapshot.value.qubit_count ?? '--', note: '' },
    ],
    execution: [
      { label: '分布式编译', value: statusLabel(normalizeStatus(workflowState.stageRuns.distributed_compiling)), note: serviceNote('distributed_compiling') },
      { label: '仿真评估', value: statusLabel(normalizeStatus(workflowState.stageRuns.simulation_evaluating)), note: serviceNote('simulation_evaluating') },
      { label: '拓扑推荐', value: topologyText.value, note: '' },
      { label: '保真度', value: scientificSnapshot.value.fidelity_score ?? '--', note: '' },
    ],
    scoring: [
      { label: '评分状态', value: statusLabel(flowSteps.value[4].status), note: serviceNote('scoring') },
      { label: 'FinalScore', value: finalScoreText.value, note: '' },
      { label: '门控', value: gatekeepingText.value, note: '' },
      { label: '排名', value: resultSummary.value.rank_position ?? '--', note: '' },
    ],
    results: [
      { label: '结果视图', value: workflowState.resultView ? '已生成' : '未生成', note: '' },
      { label: '推荐材料', value: workflowState.resultView?.candidateMaterial || workflowState.selectedCandidate || '--', note: '' },
      { label: '传输次数', value: scientificSnapshot.value.teleportations ?? '--', note: '' },
      { label: '下一步', value: workflowState.resultView ? '查看结果页' : '等待聚合', note: '' },
    ],
  }
  return cards[selectedStepKey.value] || cards.materials
})

const gatekeepingText = computed(() => {
  if (resultSummary.value.gatekeeping_passed === true) return '通过'
  if (resultSummary.value.gatekeeping_passed === false) return '未通过'
  return '--'
})

const assistantQuickQuestions = computed(() => {
  const map = {
    materials: ['我应该如何开始一次筛选？', 'queued 和 sync 有什么区别？', 'QASM 为什么可以不填？'],
    screening: ['粗筛阶段判断什么？', '门控结论怎么理解？', '候选材料家族有什么意义？'],
    quantum: ['化学建模和量子编码是什么关系？', '这一阶段输出哪些工件？', '量子比特数怎么看？'],
    execution: ['分布式执行阶段在做什么？', '拓扑推荐怎么理解？', '保真度指标说明什么？'],
    scoring: ['FinalScore 是怎么来的？', '门控和评分是什么关系？', '如何解释推荐排序？'],
    results: ['结果页重点看什么？', '如何向评审解释这个结论？', '下一步应该做什么？'],
  }
  return map[selectedStepKey.value] || map.materials
})

const assistantCards = computed(() => [
  { label: '当前阶段', value: activeStep.value.title, note: activeStep.value.detail },
  { label: '候选材料', value: workflowState.selectedCandidate || '--', note: currentCandidate.value?.family || '等待选择' },
  { label: '任务状态', value: workflowStatusLabel.value, note: cleanProgressText.value },
  { label: '日志数量', value: String(workflowState.eventLogs.length), note: '' },
])

function cleanStageTitle(stageName) {
  return STAGE_TITLE_MAP[stageName] || stageName || '等待创建'
}

function normalizeStatus(value) {
  if (value === 'success') return 'completed'
  if (value === 'running') return 'running'
  if (value === 'failed') return 'failed'
  if (value === 'skipped') return 'pending'
  return 'pending'
}

function statusLabel(status) {
  if (status === 'completed') return '已完成'
  if (status === 'running') return '进行中'
  if (status === 'failed') return '失败'
  return '未开始'
}

function serviceNote(stageName) {
  const run = workflowState.stageRunList.find(item => item.stageName === stageName)
  return run?.serviceName || '等待该阶段执行'
}

function formatPayload(payload) {
  if (!payload || typeof payload !== 'object') return '无附加信息'
  return Object.entries(payload)
    .slice(0, 3)
    .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(' · ')
}

async function handleCreateWorkflow() {
  if (!workflowState.selectedCandidate) {
    ElMessage.warning('请先选择候选材料')
    return
  }

  submitting.value = true
  try {
    await createWorkflow()
    ElMessage.success('工作流已创建')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '创建工作流失败')
  } finally {
    submitting.value = false
  }
}

async function handleRefresh() {
  if (!workflowState.workflowId) return
  refreshing.value = true
  try {
    await refreshWorkflowBundle()
    ElMessage.success('工作流详情已刷新')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '刷新工作流详情失败')
  } finally {
    refreshing.value = false
  }
}

async function handleCancel() {
  if (!canCancel.value) return
  cancelling.value = true
  try {
    await stopWorkflow()
    ElMessage.success('工作流已取消')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '取消工作流失败')
  } finally {
    cancelling.value = false
  }
}
</script>

<style scoped>
.workbench-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #101828;
}

.workbench-hero,
.metric-card,
.surface-panel,
.step-item,
.stage-card,
.progress-block,
.result-block,
.warning-card,
.log-item,
.empty-state {
  border-radius: 8px;
}

.workbench-hero {
  min-height: 150px;
  padding: 24px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  background:
    linear-gradient(115deg, rgba(6, 21, 35, 0.94), rgba(12, 45, 62, 0.88)),
    url('../assets/chemistry-hero.png') center / cover;
  box-shadow: 0 18px 46px rgba(2, 10, 18, 0.2);
}

.hero-copy {
  max-width: 720px;
}

.panel-kicker {
  color: #67d5ca;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.panel-kicker-dark {
  color: #0f766e;
}

.hero-copy h2 {
  margin-top: 8px;
  color: #f8fbff;
  font-size: 1.5rem;
  letter-spacing: 0;
}

.hero-copy p {
  margin-top: 10px;
  color: rgba(232, 241, 252, 0.78);
  line-height: 1.75;
  max-width: 680px;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.status-chip {
  height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(166, 204, 247, 0.18);
  color: #e8f1fc;
  background: rgba(255, 255, 255, 0.08);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  white-space: nowrap;
}

.status-chip span {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #98a2b3;
}

.status-chip.completed span {
  background: #22c55e;
}

.status-chip.failed span {
  background: #ef4444;
}

.status-chip.screening span,
.status-chip.chem_modeling span,
.status-chip.quantum_encoding span,
.status-chip.distributed_compiling span,
.status-chip.simulation_evaluating span,
.status-chip.scoring span,
.status-chip.aggregating span {
  background: #f59e0b;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card,
.surface-panel {
  border: 1px solid rgba(166, 204, 247, 0.12);
  background: rgba(248, 251, 255, 0.96);
  box-shadow: 0 18px 40px rgba(2, 10, 18, 0.14);
}

.metric-card {
  padding: 16px;
}

.metric-card span,
.metric-card small,
.stage-card span,
.stage-card small,
.progress-block span,
.result-block span,
.result-block small,
.log-item small {
  color: #667085;
  font-size: 0.76rem;
}

.metric-card strong,
.stage-card strong,
.progress-block strong,
.result-block strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.06rem;
}

.metric-card small,
.stage-card small,
.result-block small {
  display: block;
  margin-top: 8px;
  line-height: 1.55;
}

.metric-card.accent {
  background: linear-gradient(135deg, rgba(24, 186, 169, 0.12), rgba(55, 125, 255, 0.1)), #fff;
}

.workbench-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.left-rail,
.main-workspace {
  display: grid;
  gap: 18px;
}

.surface-panel {
  padding: 18px;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.panel-heading.compact {
  align-items: center;
}

.panel-heading h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.08rem;
  letter-spacing: 0;
}

.field-list {
  margin-top: 18px;
  display: grid;
  gap: 14px;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  color: #344054;
  font-size: 0.82rem;
  font-weight: 600;
}

.setup-actions {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.step-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.step-item {
  width: 100%;
  padding: 13px;
  border: 1px solid #e6ebf2;
  background: #fff;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.step-item:hover {
  transform: translateY(-1px);
}

.step-item.active {
  border-color: rgba(55, 125, 255, 0.34);
  background: rgba(55, 125, 255, 0.06);
}

.step-item.completed {
  border-color: rgba(34, 197, 94, 0.26);
}

.step-item.running {
  border-color: rgba(245, 158, 11, 0.34);
}

.step-index {
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: #edf4ff;
  color: #2456b8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.76rem;
  font-weight: 700;
}

.step-main strong {
  display: block;
  color: #101828;
  font-size: 0.9rem;
}

.step-main small {
  display: block;
  margin-top: 4px;
  color: #667085;
  font-size: 0.74rem;
  line-height: 1.45;
}

.step-state {
  color: #2456b8;
  font-size: 0.72rem;
  font-weight: 700;
  white-space: nowrap;
}

.focus-panel {
  min-height: 320px;
}

.stage-description {
  margin-top: 16px;
  max-width: 860px;
  color: #475467;
  line-height: 1.8;
}

.stage-card-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stage-card,
.progress-block,
.result-block {
  padding: 16px;
  border: 1px solid #e6ebf2;
  background: #f8fbff;
}

.execution-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 12px;
}

.progress-block :deep(.el-progress) {
  margin-top: 12px;
}

.inline-link {
  color: #2456b8;
  font-size: 0.84rem;
  font-weight: 700;
  text-decoration: none;
}

.warning-stack {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.warning-card {
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.24);
  background: rgba(245, 158, 11, 0.08);
  color: #7a4100;
  font-size: 0.82rem;
  line-height: 1.6;
}

.log-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.log-item {
  padding: 13px 14px;
  border: 1px solid #e6ebf2;
  background: #f8fbff;
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 12px;
}

.log-index {
  color: #2456b8;
  font-size: 0.78rem;
  font-weight: 700;
}

.log-item strong {
  color: #101828;
}

.log-item p {
  margin-top: 6px;
  color: #475467;
  font-size: 0.8rem;
  line-height: 1.55;
  word-break: break-word;
}

.empty-state {
  margin-top: 16px;
  padding: 18px;
  border: 1px dashed #d0d5dd;
  background: #fbfcfe;
}

.empty-state strong {
  color: #101828;
}

.empty-state p {
  margin-top: 8px;
  color: #475467;
  line-height: 1.65;
  font-size: 0.84rem;
}

.assistant-shell {
  background: #fff;
  border-color: rgba(166, 204, 247, 0.18);
  min-height: auto;
}

.assistant-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
}

.assistant-summary h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.08rem;
  letter-spacing: 0;
}

.assistant-summary p {
  margin-top: 8px;
  color: #475467;
  line-height: 1.65;
  font-size: 0.86rem;
}

.assistant-panel-inner {
  margin-top: 18px;
}

.mono {
  font-family: Consolas, 'SFMono-Regular', monospace;
}

.workbench-page :deep(.el-button),
.workbench-page :deep(.el-input__wrapper),
.workbench-page :deep(.el-textarea__inner),
.workbench-page :deep(.el-select__wrapper),
.workbench-page :deep(.el-segmented) {
  border-radius: 8px;
}

@media (max-width: 1280px) {
  .workbench-grid {
    grid-template-columns: 320px minmax(0, 1fr);
  }

  .stage-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .workbench-hero,
  .workbench-grid,
  .execution-grid {
    grid-template-columns: 1fr;
  }

  .workbench-hero {
    display: grid;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .metric-grid,
  .stage-card-grid {
    grid-template-columns: 1fr;
  }

  .step-item {
    grid-template-columns: 38px minmax(0, 1fr);
  }

  .step-state {
    grid-column: 2;
  }

  .assistant-summary {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
