<template>
  <div class="screening-results-page">
    <section class="results-hero">
      <div class="hero-copy">
        <span class="panel-kicker">Screening Result</span>
        <h2>筛选结果</h2>
        <p>围绕最近一次多材料筛选任务，集中查看推荐结论、排行榜、候选材料证据链与风险提示。</p>
      </div>

      <div class="hero-actions">
        <div class="status-chip" :class="screeningState.workflowStatus">
          <span></span>
          {{ statusLabel }}
        </div>
        <el-button :loading="screeningState.loadingBundle" :disabled="!screeningState.screeningWorkflowId" @click="handleRefresh">
          刷新结果
        </el-button>
        <el-button type="primary" @click="goScreening">返回筛选工作台</el-button>
      </div>
    </section>

    <section v-if="!hasWorkflow" class="empty-panel">
      <div class="empty-icon">∴</div>
      <h3>还没有可展示的筛选结果</h3>
      <p>请先在筛选工作台选择候选材料并启动任务。任务完成后，结果页会展示真实 leaderboard、证据链和推荐解释。</p>
      <el-button type="primary" @click="goScreening">进入筛选工作台</el-button>
    </section>

    <template v-else>
      <section class="summary-grid">
        <article class="summary-card highlight">
          <span>推荐候选</span>
          <strong><ChemicalFormula :text="recommendedMaterial" /></strong>
          <small>{{ recommendationReason }}</small>
        </article>
        <article class="summary-card">
          <span>Workflow ID</span>
          <strong class="mono">{{ shortWorkflowId }}</strong>
          <small>{{ screeningState.screeningWorkflowId }}</small>
        </article>
        <article class="summary-card">
          <span>候选材料</span>
          <strong>{{ screeningState.candidateCount || screeningState.selectedCandidates.length || '--' }}</strong>
          <small>{{ selectedCandidateText }}</small>
        </article>
        <article class="summary-card accent">
          <span>Final Score</span>
          <strong>{{ finalScoreText }}</strong>
          <small>{{ recommendationLevelText }}</small>
        </article>
      </section>

      <div class="results-layout">
        <section class="surface-panel leaderboard-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Leaderboard</span>
              <h3>材料排行榜</h3>
            </div>
            <el-tag size="small" effect="plain">{{ screeningState.leaderboard.length }} rows</el-tag>
          </div>

          <div v-if="!screeningState.leaderboard.length" class="empty-inline">
            后端尚未返回排行榜，请刷新任务结果或稍后再试。
          </div>

          <div v-else class="leaderboard-list">
            <button
              v-for="item in screeningState.leaderboard"
              :key="item.candidateMaterial"
              type="button"
              class="leaderboard-row"
              :class="{ active: item.candidateMaterial === screeningState.selectedMaterialName }"
              @click="handleSelectMaterial(item.candidateMaterial)"
            >
              <span class="rank">#{{ item.score.rank_position || '--' }}</span>
              <span class="material-name">
                <strong><ChemicalFormula :text="item.candidateMaterial" /></strong>
                <small>{{ levelLabel(item.score.recommendation_level) }}</small>
              </span>
              <span class="score-track">
                <i :style="{ width: `${scorePercent(item.score.final_score)}%` }"></i>
              </span>
              <strong class="row-score">{{ formatMetric(item.score.final_score) }}</strong>
            </button>
          </div>
        </section>

        <section class="surface-panel detail-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Selected Material</span>
              <h3><ChemicalFormula :text="selectedName" /></h3>
            </div>
            <el-tag v-if="screeningState.loadingExplanation" size="small" effect="plain">加载解释</el-tag>
          </div>

          <div v-if="selectedLeaderboardRow" class="score-grid">
            <ScoreMetric label="Classical" :value="scoreBreakdown.classical_screening_score" />
            <ScoreMetric label="Quantum" :value="scoreBreakdown.quantum_refine_score" />
            <ScoreMetric label="Deploy" :value="scoreBreakdown.deploy_score" />
            <ScoreMetric label="Confidence" :value="scoreBreakdown.confidence_score" />
            <ScoreMetric label="Final" :value="selectedLeaderboardRow.score.final_score" strong />
          </div>

          <div class="material-meta">
            <article>
              <span>材料族</span>
              <strong>{{ selectedMaterial?.materialProfile?.materialFamily || '--' }}</strong>
            </article>
            <article>
              <span>活性位点</span>
              <strong>{{ selectedMaterial?.materialProfile?.activeSite || '--' }}</strong>
            </article>
            <article>
              <span>Material ID</span>
              <strong class="mono">{{ selectedMaterial?.materialProfile?.materialId || '--' }}</strong>
            </article>
          </div>
        </section>
      </div>

      <section class="surface-panel evidence-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker panel-kicker-dark">Evidence Panel</span>
            <h3>推荐证据链</h3>
          </div>
        </div>

        <div class="evidence-grid">
          <article class="evidence-card">
            <span>为什么推荐</span>
            <p>{{ recommendationReason }}</p>
          </article>
          <article class="evidence-card">
            <span>Classical Screening</span>
            <ul>
              <li v-for="item in classicalEvidence" :key="item.label">
                <b>{{ item.label }}</b>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </article>
          <article class="evidence-card">
            <span>Quantum Refinement</span>
            <ul>
              <li v-for="item in quantumEvidence" :key="item.label">
                <b>{{ item.label }}</b>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </article>
          <article class="evidence-card">
            <span>Distributed Execution</span>
            <ul>
              <li v-for="item in distributedEvidence" :key="item.label">
                <b>{{ item.label }}</b>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </article>
        </div>
      </section>

      <section class="surface-panel explanation-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker panel-kicker-dark">Explanation Layer</span>
            <h3>完整解释层</h3>
          </div>
        </div>

        <div class="explanation-grid">
          <article class="explanation-card">
            <span>分数拆解</span>
            <ul>
              <li v-for="item in scoreBreakdownRows" :key="item.label">
                <b>{{ item.label }}</b>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </article>
          <article class="explanation-card">
            <span>证据来源说明</span>
            <ul>
              <li v-for="item in evidenceSourceRows" :key="item.label">
                <b>{{ item.label }}</b>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </article>
          <article class="explanation-card">
            <span>模型局限</span>
            <p v-for="item in modelLimitations" :key="item">{{ item }}</p>
          </article>
          <article class="explanation-card accent">
            <span>下一步验证建议</span>
            <p>{{ nextValidationStep }}</p>
          </article>
        </div>
      </section>

      <section class="surface-panel risk-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker panel-kicker-dark">Risk Notes</span>
            <h3>风险提示与后续动作</h3>
          </div>
          <router-link class="text-link" to="/app/history">查看历史记录</router-link>
        </div>

        <div class="risk-list">
          <article v-for="item in activeRiskNotes" :key="item" class="risk-item">
            <span></span>
            <p>{{ item }}</p>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import { useScreeningWorkflow } from '../composables/useScreeningWorkflow'

const route = useRoute()
const router = useRouter()

const {
  screeningState,
  selectedMaterial,
  selectedLeaderboardRow,
  refreshScreeningWorkflow,
  restoreLatestScreeningWorkflow,
  loadScreeningWorkflowById,
  selectMaterial,
} = useScreeningWorkflow()

const ScoreMetric = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: [Number, String], default: '--' },
    strong: { type: Boolean, default: false },
  },
  setup(props) {
    return () =>
      h('article', { class: ['score-metric', { strong: props.strong }] }, [
        h('span', props.label),
        h('strong', formatMetric(props.value)),
      ])
  },
})

onMounted(loadRouteWorkflow)

watch(
  () => route.query.workflowId,
  () => {
    loadRouteWorkflow()
  }
)

async function loadRouteWorkflow() {
  try {
    const workflowId = typeof route.query.workflowId === 'string' ? route.query.workflowId : ''
    if (workflowId) {
      await loadScreeningWorkflowById(workflowId)
      return
    }
    await restoreLatestScreeningWorkflow()
  } catch (error) {
    ElMessage.warning(error.response?.data?.detail || '筛选结果暂时不可用，请确认后端任务仍可访问')
  }
}

const hasWorkflow = computed(() => Boolean(screeningState.screeningWorkflowId))
const shortWorkflowId = computed(() =>
  screeningState.screeningWorkflowId ? screeningState.screeningWorkflowId.slice(0, 8) : '--'
)
const selectedName = computed(() => selectedLeaderboardRow.value?.candidateMaterial || screeningState.selectedMaterialName || '--')
const recommendedMaterial = computed(() => screeningState.recommendedMaterial || selectedLeaderboardRow.value?.candidateMaterial || '--')
const finalScoreText = computed(() => formatMetric(selectedLeaderboardRow.value?.score?.final_score))
const selectedCandidateText = computed(() =>
  screeningState.selectedCandidates.length ? screeningState.selectedCandidates.join(' / ') : '来自最近一次筛选任务'
)
const activeExplanation = computed(() => screeningState.selectedMaterialExplanation || selectedLeaderboardRow.value?.explanation || null)
const scoreBreakdown = computed(() => {
  const score = selectedLeaderboardRow.value?.score || {}
  return {
    classical_screening_score: score.classical_screening_score,
    quantum_refine_score: score.quantum_refine_score,
    deploy_score: score.deploy_score,
    confidence_score: score.confidence_score,
    ...(score.score_breakdown || {}),
    ...(activeExplanation.value?.scoreBreakdown || {}),
  }
})
const recommendationReason = computed(
  () => activeExplanation.value?.recommendationReason || selectedLeaderboardRow.value?.score?.reason || '等待后端返回推荐解释'
)
const activeRiskNotes = computed(() => {
  const notes = activeExplanation.value?.riskNotes || selectedLeaderboardRow.value?.score?.risk_notes || []
  return notes.length ? notes : ['当前候选暂无明显风险提示，建议结合实验约束继续复核。']
})
const recommendationLevelText = computed(() => levelLabel(selectedLeaderboardRow.value?.score?.recommendation_level))
const scoreBreakdownRows = computed(() => {
  const weights = scoreBreakdown.value.weights || {}
  return [
    ['Classical', scoreBreakdown.value.classical_screening_score, weights.classical_screening_score],
    ['Quantum', scoreBreakdown.value.quantum_refine_score, weights.quantum_refine_score],
    ['Deploy', scoreBreakdown.value.deploy_score, weights.deploy_score],
    ['Confidence', scoreBreakdown.value.confidence_score, weights.confidence_score],
  ].map(([label, value, weight]) => ({
    label: weight === undefined ? label : `${label} (${formatPercentWeight(weight)})`,
    value: formatMetric(value),
  }))
})
const evidenceSourceRows = computed(() => {
  const sourceSummary = activeExplanation.value?.evidenceSourceSummary || selectedLeaderboardRow.value?.score?.evidence_source_summary || {}
  const rows = Object.entries(sourceSummary).map(([label, value]) => ({
    label: label.replaceAll('_', ' '),
    value: value || '--',
  }))
  return rows.length ? rows : [{ label: 'source', value: '后端暂未返回证据来源说明' }]
})
const modelLimitations = computed(() => {
  const limitations =
    activeExplanation.value?.modelLimitations || selectedLeaderboardRow.value?.score?.model_limitations || []
  return limitations.length ? limitations : ['后端暂未返回模型局限说明。']
})
const nextValidationStep = computed(() => {
  return (
    activeExplanation.value?.nextValidationStep ||
    selectedLeaderboardRow.value?.score?.next_validation_step ||
    '后端暂未返回下一步验证建议。'
  )
})
const statusLabel = computed(() => {
  const map = {
    idle: '待启动',
    created: '已创建',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return map[screeningState.workflowStatus] || screeningState.workflowStatus || '待启动'
})

const classicalEvidence = computed(() => {
  const evidence = activeExplanation.value?.keyEvidence?.screening || {}
  const screening = selectedMaterial.value?.screening || {}
  return [
    ['吸附', evidence.adsorption_score ?? screening.adsorption_score],
    ['催化', evidence.catalytic_activity_score ?? screening.catalytic_activity_score],
    ['稳定', evidence.stability_score ?? screening.stability_score],
    ['导电', evidence.conductivity_score ?? screening.conductivity_score],
    ['粗筛分', evidence.classical_screening_score ?? screening.classical_screening_score],
  ].map(([label, value]) => ({ label, value: formatMetric(value) }))
})

const quantumEvidence = computed(() => {
  const evidence = activeExplanation.value?.keyEvidence?.quantum_refinement || {}
  const quantum = selectedMaterial.value?.quantumRefinement || {}
  const problem = selectedMaterial.value?.quantumProblem || {}
  return [
    ['Qubits', evidence.qubit_count ?? problem.qubit_count],
    ['Pauli Terms', evidence.pauli_term_count ?? problem.pauli_term_count],
    ['精修分', evidence.quantum_refine_score ?? quantum.quantum_refine_score],
    ['吸附能', evidence.refined_adsorption_energy ?? quantum.refined_adsorption_energy],
    ['Barrier Proxy', evidence.barrier_proxy ?? quantum.barrier_proxy],
  ].map(([label, value]) => ({ label, value: formatMetric(value) }))
})

const distributedEvidence = computed(() => {
  const evidence = activeExplanation.value?.keyEvidence?.distributed_execution || {}
  const execution = selectedMaterial.value?.distributedExecution || {}
  const subcircuits = evidence.subcircuits ?? execution.subcircuits ?? []
  return [
    ['Backend', evidence.execution_backend ?? execution.execution_backend],
    ['Partitions', Array.isArray(subcircuits) ? subcircuits.length : subcircuits],
    ['Shots', evidence.shots ?? execution.shots],
    ['Quality', evidence.execution_quality ?? execution.execution_quality],
    ['Runtime', evidence.estimated_runtime ?? execution.estimated_runtime],
  ].map(([label, value]) => ({ label, value: formatMetric(value) }))
})

async function handleRefresh() {
  try {
    await refreshScreeningWorkflow()
    ElMessage.success('筛选结果已刷新')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '刷新筛选结果失败')
  }
}

async function handleSelectMaterial(candidateMaterial) {
  await selectMaterial(candidateMaterial)
}

function goScreening() {
  router.push('/app/screening')
}

function formatMetric(value) {
  if (value === null || value === undefined || value === '') return '--'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2)
}

function scorePercent(value) {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return 0
  if (numeric <= 1) return Math.max(0, Math.min(100, numeric * 100))
  return Math.max(0, Math.min(100, numeric))
}

function formatPercentWeight(value) {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return value
  return `${Math.round(numeric * 100)}%`
}

function levelLabel(value) {
  const map = {
    strong_recommend: '强推荐',
    recommend: '推荐',
    backup: '备选',
    not_recommended: '不推荐',
  }
  return map[value] || value || '--'
}
</script>

<style scoped>
.screening-results-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #101828;
}

.results-hero,
.surface-panel,
.summary-card,
.empty-panel {
  border-radius: 8px;
}

.results-hero {
  min-height: 168px;
  padding: 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  background:
    linear-gradient(115deg, rgba(5, 18, 31, 0.96), rgba(10, 45, 57, 0.86)),
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
  font-size: 1.56rem;
  letter-spacing: 0;
}

.hero-copy p {
  margin-top: 10px;
  color: rgba(232, 241, 252, 0.78);
  line-height: 1.75;
}

.hero-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.status-chip {
  height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(166, 204, 247, 0.18);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #e8f1fc;
  background: rgba(255, 255, 255, 0.08);
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

.status-chip.running span,
.status-chip.created span {
  background: #f2c35b;
}

.status-chip.failed span {
  background: #ef4444;
}

.empty-panel {
  padding: 38px;
  border: 1px dashed #d0d5dd;
  background: #fff;
  text-align: center;
}

.empty-icon {
  margin: 0 auto 14px;
  width: 52px;
  height: 52px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #edf4ff;
  color: #2456b8;
  font-size: 1.5rem;
  font-weight: 800;
}

.empty-panel h3 {
  color: #101828;
}

.empty-panel p {
  margin: 10px auto 18px;
  max-width: 620px;
  color: #667085;
  line-height: 1.75;
}

.summary-grid {
  display: grid;
  grid-template-columns: 1.2fr repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.summary-card,
.surface-panel {
  border: 1px solid rgba(166, 204, 247, 0.12);
  background: rgba(248, 251, 255, 0.96);
  box-shadow: 0 18px 40px rgba(2, 10, 18, 0.14);
}

.summary-card,
.surface-panel {
  padding: 18px;
}

.summary-card span,
.summary-card small {
  color: #667085;
  font-size: 0.76rem;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.14rem;
}

.summary-card small {
  display: block;
  margin-top: 8px;
  line-height: 1.55;
}

.summary-card.highlight {
  border-color: rgba(217, 166, 59, 0.32);
  background: linear-gradient(135deg, rgba(217, 166, 59, 0.12), rgba(55, 125, 255, 0.08)), #fff;
}

.summary-card.accent {
  background: linear-gradient(135deg, rgba(24, 186, 169, 0.12), rgba(55, 125, 255, 0.1)), #fff;
}

.results-layout {
  display: grid;
  grid-template-columns: minmax(420px, 0.92fr) minmax(0, 1.08fr);
  gap: 18px;
  align-items: start;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.panel-heading h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.08rem;
  letter-spacing: 0;
}

.leaderboard-list {
  margin-top: 18px;
  display: grid;
  gap: 10px;
}

.leaderboard-row {
  width: 100%;
  padding: 14px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  display: grid;
  grid-template-columns: 48px minmax(160px, 1fr) minmax(150px, 0.78fr) 72px;
  align-items: center;
  gap: 12px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease;
}

.leaderboard-row:hover {
  transform: translateY(-1px);
}

.leaderboard-row.active {
  border-color: rgba(55, 125, 255, 0.34);
  background: rgba(55, 125, 255, 0.06);
}

.rank {
  color: #2456b8;
  font-size: 0.82rem;
  font-weight: 800;
}

.material-name strong {
  display: block;
  color: #101828;
}

.material-name small {
  display: block;
  margin-top: 5px;
  color: #667085;
  font-size: 0.72rem;
}

.score-track {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #edf2f7;
}

.score-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #18baa9, #377dff);
}

.row-score {
  color: #101828;
  text-align: right;
}

.score-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.score-metric,
.material-meta article,
.evidence-card,
.risk-item {
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.score-metric {
  padding: 14px;
}

.score-metric span,
.material-meta span,
.evidence-card span {
  color: #667085;
  font-size: 0.74rem;
}

.score-metric strong,
.material-meta strong {
  display: block;
  margin-top: 8px;
  color: #101828;
}

.score-metric.strong {
  border-color: rgba(24, 186, 169, 0.28);
  background: rgba(24, 186, 169, 0.06);
}

.score-metric.strong strong {
  color: #0f766e;
}

.material-meta {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.material-meta article {
  padding: 14px;
}

.evidence-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: 1.2fr repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.explanation-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.evidence-card {
  padding: 16px;
  background: #f8fbff;
}

.explanation-card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.explanation-card.accent {
  border-color: rgba(24, 186, 169, 0.28);
  background: rgba(24, 186, 169, 0.06);
}

.explanation-card span {
  color: #667085;
  font-size: 0.74rem;
}

.evidence-card p {
  margin-top: 10px;
  color: #344054;
  line-height: 1.75;
}

.explanation-card p {
  margin-top: 10px;
  color: #344054;
  line-height: 1.75;
  font-size: 0.84rem;
}

.evidence-card ul {
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 9px;
  list-style: none;
}

.explanation-card ul {
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 9px;
  list-style: none;
}

.evidence-card li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #667085;
  font-size: 0.8rem;
}

.explanation-card li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #667085;
  font-size: 0.8rem;
}

.evidence-card li strong {
  color: #101828;
  text-align: right;
}

.explanation-card li strong {
  color: #101828;
  text-align: right;
}

.risk-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.risk-item {
  padding: 14px;
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 12px;
  align-items: start;
  background: #fffaf0;
}

.risk-item span {
  margin-top: 7px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #d9a63b;
}

.risk-item p {
  color: #594100;
  line-height: 1.65;
}

.empty-inline {
  margin-top: 18px;
  padding: 18px;
  border: 1px dashed #d0d5dd;
  border-radius: 8px;
  color: #667085;
  background: #fbfcfe;
}

.text-link {
  color: #2456b8;
  text-decoration: none;
  font-size: 0.84rem;
  font-weight: 700;
}

.mono {
  font-family: Consolas, 'SFMono-Regular', monospace;
}

.screening-results-page :deep(.el-button) {
  border-radius: 8px;
}

@media (max-width: 1280px) {
  .summary-grid,
  .results-layout,
  .evidence-grid,
  .explanation-grid {
    grid-template-columns: 1fr;
  }

  .score-grid,
  .material-meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .results-hero {
    display: grid;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .leaderboard-row {
    grid-template-columns: 44px minmax(0, 1fr) 66px;
  }

  .score-track {
    grid-column: 2 / -1;
  }

  .score-grid,
  .material-meta {
    grid-template-columns: 1fr;
  }
}
</style>
