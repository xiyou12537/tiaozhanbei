<template>
  <div class="screening-page">
    <section class="screening-hero">
      <div class="hero-copy">
        <span class="panel-kicker">Multi-material Screening</span>
        <h2>多材料化学筛选</h2>
        <p>选择候选材料后启动筛选任务，页面会展示经典粗筛、量子精修、真实排行榜和材料解释。</p>
      </div>

      <div class="hero-actions">
        <div class="status-chip" :class="screeningState.workflowStatus">
          <span></span>
          {{ statusLabel }}
        </div>
        <el-button :loading="screeningState.loadingBundle" :disabled="!screeningState.screeningWorkflowId" @click="handleRefresh">
          刷新结果
        </el-button>
        <el-button type="primary" :loading="screeningState.submitting" :disabled="!canSubmitScreening" @click="handleCreate">
          启动多材料筛选
        </el-button>
        <el-button :disabled="!screeningState.screeningWorkflowId" @click="handleViewResults">
          查看完整结果
        </el-button>
      </div>
    </section>

    <section class="workflow-entry-grid" aria-label="筛选方式">
      <article class="workflow-entry active">
        <div>
          <span class="entry-type">Built-in Candidates · Demo</span>
          <h3>内置候选材料筛选</h3>
          <p>使用平台候选库快速验证经典粗筛、量子精修与排行榜链路。</p>
        </div>
        <el-tag type="success" effect="plain">当前模式</el-tag>
      </article>
      <article class="workflow-entry research">
        <div>
          <span class="entry-type">User Structure · Research</span>
          <h3>用户自定义结构计算</h3>
          <p>上传真实结构，逐步确认活性位点、吸附构型、电荷、自旋与活性空间。</p>
        </div>
        <el-button type="primary" @click="handleOpenStructureWorkbench">进入科研建模</el-button>
      </article>
    </section>

    <section class="screening-metrics">
      <article class="metric-card">
        <span>已选材料</span>
        <strong>{{ selectedCandidateCount }} / {{ screeningState.candidates.length || 0 }}</strong>
        <small>至少选择 {{ minSelectedCandidates }} 个候选材料</small>
      </article>
      <article class="metric-card">
        <span>Workflow ID</span>
        <strong class="mono">{{ shortWorkflowId }}</strong>
        <small>{{ screeningState.screeningWorkflowId || '创建后生成任务编号' }}</small>
      </article>
      <article class="metric-card">
        <span>推荐材料</span>
        <strong><ChemicalFormula :text="screeningState.recommendedMaterial || '--'" /></strong>
        <small>来自后端真实 leaderboard</small>
      </article>
      <article class="metric-card accent">
        <span>候选数量</span>
        <strong>{{ screeningState.candidateCount || selectedCandidateCount }}</strong>
        <small>{{ screeningState.workflowStatus === 'completed' ? '筛选已完成' : submitHint }}</small>
      </article>
    </section>

    <div class="screening-grid">
      <aside class="setup-column">
        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Candidate Setup</span>
              <h3>候选材料</h3>
            </div>
            <el-tag size="small" :type="canSubmitScreening ? 'success' : 'warning'" effect="plain">
              已选 {{ selectedCandidateCount }}
            </el-tag>
          </div>

          <div v-loading="screeningState.loadingCandidates" class="candidate-list">
            <button
              v-for="item in screeningState.candidates"
              :key="item.name"
              type="button"
              class="candidate-card"
              :class="{ selected: screeningState.selectedCandidates.includes(item.name) }"
              @click="toggleCandidate(item.name)"
            >
              <span class="candidate-check">
                <el-checkbox :model-value="screeningState.selectedCandidates.includes(item.name)" />
              </span>
              <span class="candidate-main">
                <strong><ChemicalFormula :text="item.name" /></strong>
                <small>{{ item.materialFamily || item.family || 'candidate' }}</small>
              </span>
              <span class="candidate-score">{{ formatMetric(item.adsorptionStrength) }}</span>
            </button>
          </div>

          <div v-if="screeningState.lastError" class="warning-card">
            {{ screeningState.lastError }}
          </div>

          <div class="setup-actions">
            <el-button type="primary" :loading="screeningState.submitting" :disabled="!canSubmitScreening" @click="handleCreate">
              启动多材料筛选
            </el-button>
            <el-button :loading="screeningState.loadingBundle" :disabled="!screeningState.screeningWorkflowId" @click="handleRefresh">
              重新拉取结果
            </el-button>
            <el-button :disabled="!screeningState.screeningWorkflowId" @click="handleViewResults">
              查看完整结果
            </el-button>
          </div>
        </section>

        <section class="surface-panel">
          <div class="panel-heading compact">
            <div>
              <span class="panel-kicker panel-kicker-dark">Workflow</span>
              <h3>联调链路</h3>
            </div>
          </div>
          <div class="flow-list">
            <div v-for="item in flowSteps" :key="item.label" class="flow-item" :class="{ done: item.done }">
              <span>{{ item.index }}</span>
              <strong>{{ item.label }}</strong>
            </div>
          </div>
        </section>
      </aside>

      <main class="result-column">
        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Leaderboard</span>
              <h3>材料排行榜</h3>
            </div>
            <el-tag v-if="screeningState.leaderboard.length" size="small" type="success" effect="plain">
              {{ screeningState.leaderboard.length }} rows
            </el-tag>
          </div>

          <div v-if="!screeningState.leaderboard.length" class="empty-state">
            <strong>等待筛选任务</strong>
            <p>选择至少 3 个候选材料并启动任务后，这里会显示后端返回的真实排行榜。</p>
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
              <span class="rank">#{{ item.score.rank_position }}</span>
              <span class="leaderboard-name">
                <strong><ChemicalFormula :text="item.candidateMaterial" /></strong>
                <small>{{ recommendationLevelLabel(item.score.recommendation_level) }}</small>
              </span>
              <span class="score-bar">
                <i :style="{ width: `${scorePercent(item.score.final_score)}%` }"></i>
              </span>
              <span class="final-score">{{ formatMetric(item.score.final_score) }}</span>
            </button>
          </div>
        </section>

        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Classical Screening</span>
              <h3>经典粗筛</h3>
            </div>
          </div>

          <div class="table-wrap">
            <table class="screening-table">
              <thead>
                <tr>
                  <th>材料</th>
                  <th>吸附</th>
                  <th>催化</th>
                  <th>稳定</th>
                  <th>导电</th>
                  <th>合成</th>
                  <th>粗筛分</th>
                  <th>结论</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in screeningState.classicalScreeningResults" :key="item.candidateMaterial">
                  <td><ChemicalFormula :text="item.candidateMaterial" /></td>
                  <td>{{ formatMetric(item.screening.adsorption_score) }}</td>
                  <td>{{ formatMetric(item.screening.catalytic_activity_score) }}</td>
                  <td>{{ formatMetric(item.screening.stability_score) }}</td>
                  <td>{{ formatMetric(item.screening.conductivity_score) }}</td>
                  <td>{{ formatMetric(item.screening.synthesis_score) }}</td>
                  <td><strong>{{ formatMetric(item.screening.classical_screening_score) }}</strong></td>
                  <td>
                    <el-tag size="small" :type="item.screening.passed ? 'success' : 'warning'" effect="plain">
                      {{ item.screening.passed ? '通过' : '保留' }}
                    </el-tag>
                  </td>
                </tr>
                <tr v-if="!screeningState.classicalScreeningResults.length">
                  <td colspan="8" class="table-empty">暂无经典粗筛结果</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Quantum Refinement</span>
              <h3>量子精修</h3>
            </div>
          </div>

          <div v-if="!screeningState.quantumRefinementResults.length" class="empty-state compact">
            <strong>暂无量子精修结果</strong>
            <p>后端返回精修结果后会展示 qubit、Pauli 项、执行质量和精修分。</p>
          </div>

          <div v-else class="quantum-grid">
            <article v-for="item in screeningState.quantumRefinementResults" :key="item.candidateMaterial" class="quantum-card">
              <div class="quantum-head">
                <strong><ChemicalFormula :text="item.candidateMaterial" /></strong>
                <span>{{ item.distributedExecution.execution_backend || 'backend' }}</span>
              </div>
              <div class="quantum-stats">
                <span>Qubits <b>{{ item.quantumProblem.qubit_count ?? '--' }}</b></span>
                <span>Pauli <b>{{ item.quantumProblem.pauli_term_count ?? '--' }}</b></span>
                <span>Quality <b>{{ formatMetric(item.distributedExecution.execution_quality) }}</b></span>
                <span>Refine <b>{{ formatMetric(item.quantumRefinement.quantum_refine_score) }}</b></span>
                <span>Adsorption <b>{{ formatMetric(item.quantumRefinement.refined_adsorption_energy) }}</b></span>
                <span>Barrier <b>{{ formatMetric(item.quantumRefinement.barrier_proxy) }}</b></span>
              </div>
            </article>
          </div>
        </section>

        <section class="surface-panel detail-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Explanation</span>
              <h3>推荐解释与风险提示</h3>
            </div>
            <el-tag v-if="screeningState.loadingExplanation" size="small" effect="plain">加载中</el-tag>
          </div>

          <div v-if="selectedLeaderboardRow" class="detail-grid">
            <article class="score-breakdown">
              <span>Selected Material</span>
              <strong><ChemicalFormula :text="selectedLeaderboardRow.candidateMaterial" /></strong>
              <div class="score-stack">
                <ScoreLine label="Classical" :value="selectedLeaderboardRow.score.classical_screening_score" />
                <ScoreLine label="Quantum" :value="selectedLeaderboardRow.score.quantum_refine_score" />
                <ScoreLine label="Deploy" :value="selectedLeaderboardRow.score.deploy_score" />
                <ScoreLine label="Confidence" :value="selectedLeaderboardRow.score.confidence_score" />
                <ScoreLine label="Final" :value="selectedLeaderboardRow.score.final_score" strong />
              </div>
            </article>

            <article class="explanation-card">
              <span>Recommendation</span>
              <p>{{ activeExplanation?.recommendationReason || selectedLeaderboardRow.score.reason || '--' }}</p>
              <span>Risk Notes</span>
              <ul>
                <li v-for="item in activeRiskNotes" :key="item">{{ item }}</li>
              </ul>
            </article>
          </div>

          <div v-else class="empty-state compact">
            <strong>暂无材料解释</strong>
            <p>排行榜生成后默认展示第一名，也可以点击任意材料切换解释。</p>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import { useScreeningWorkflow } from '../composables/useScreeningWorkflow'

const router = useRouter()

const {
  screeningState,
  selectedCandidateCount,
  canSubmitScreening,
  selectedLeaderboardRow,
  minSelectedCandidates,
  loadCandidates,
  toggleCandidate,
  createScreeningWorkflow,
  refreshScreeningWorkflow,
  restoreLatestScreeningWorkflow,
  selectMaterial,
} = useScreeningWorkflow()

const ScoreLine = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: [Number, String], default: '--' },
    strong: { type: Boolean, default: false },
  },
  setup(props) {
    return () =>
      h('div', { class: ['score-line', { strong: props.strong }] }, [
        h('span', props.label),
        h('i', { style: { width: `${scorePercent(props.value)}%` } }),
        h('b', formatMetric(props.value)),
      ])
  },
})

onMounted(async () => {
  try {
    await loadCandidates()
    await restoreLatestScreeningWorkflow()
  } catch (error) {
    if (screeningState.screeningWorkflowId) {
      ElMessage.warning(error.response?.data?.detail || '最近一次筛选任务暂时不可恢复')
    }
  }
})

const shortWorkflowId = computed(() => {
  return screeningState.screeningWorkflowId ? screeningState.screeningWorkflowId.slice(0, 8) : '--'
})

const statusLabel = computed(() => {
  const map = {
    idle: '待启动',
    completed: '已完成',
    created: '已创建',
    running: '运行中',
    failed: '失败',
  }
  return map[screeningState.workflowStatus] || screeningState.workflowStatus || '待启动'
})

const submitHint = computed(() => {
  if (canSubmitScreening.value) return '可以启动筛选'
  return `还需选择 ${minSelectedCandidates - selectedCandidateCount.value} 个`
})

const activeExplanation = computed(() => screeningState.selectedMaterialExplanation || selectedLeaderboardRow.value?.explanation || null)

const activeRiskNotes = computed(() => {
  const notes = activeExplanation.value?.riskNotes || selectedLeaderboardRow.value?.score?.risk_notes || []
  return notes.length ? notes : ['暂无明显风险提示']
})

const flowSteps = computed(() => [
  { index: '01', label: '选择 3 个候选材料', done: selectedCandidateCount.value >= minSelectedCandidates },
  { index: '02', label: '创建多材料筛选任务', done: !!screeningState.screeningWorkflowId },
  { index: '03', label: '查看经典粗筛结果', done: screeningState.classicalScreeningResults.length >= 3 },
  { index: '04', label: '查看量子精修结果', done: screeningState.quantumRefinementResults.length >= 2 },
  { index: '05', label: '查看真实排行榜', done: screeningState.leaderboard.length > 0 },
  { index: '06', label: '查看第一名解释', done: !!activeExplanation.value },
])

async function handleCreate() {
  try {
    await createScreeningWorkflow()
    ElMessage.success('多材料筛选任务已创建')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '创建筛选任务失败')
  }
}

async function handleRefresh() {
  try {
    await refreshScreeningWorkflow()
    ElMessage.success('筛选结果已刷新')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '刷新筛选结果失败')
  }
}

function handleViewResults() {
  router.push('/app/results')
}

function handleOpenStructureWorkbench() {
  router.push('/app/structure-workbench')
}

async function handleSelectMaterial(candidateMaterial) {
  await selectMaterial(candidateMaterial)
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

function recommendationLevelLabel(value) {
  const map = {
    strong_recommend: 'Strong Recommend',
    recommend: 'Recommend',
    backup: 'Backup',
    not_recommended: 'Not Recommended',
  }
  return map[value] || value || '--'
}
</script>

<style scoped>
.screening-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #101828;
}

.screening-hero,
.surface-panel,
.metric-card,
.candidate-card,
.leaderboard-row,
.quantum-card,
.warning-card,
.empty-state {
  border-radius: 8px;
}

.screening-hero {
  min-height: 168px;
  padding: 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  background:
    linear-gradient(115deg, rgba(5, 18, 31, 0.96), rgba(10, 45, 57, 0.88)),
    url('../assets/chemistry-hero.png') center / cover;
  box-shadow: 0 18px 46px rgba(2, 10, 18, 0.2);
}

.hero-copy {
  max-width: 760px;
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
  max-width: 680px;
  color: rgba(232, 241, 252, 0.78);
  line-height: 1.75;
}

.hero-actions,
.setup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-actions {
  justify-content: flex-end;
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

.screening-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.workflow-entry-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.workflow-entry {
  min-height: 120px;
  padding: 18px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  background: rgba(248, 251, 255, 0.96);
  box-shadow: 0 18px 40px rgba(2, 10, 18, 0.14);
}

.workflow-entry.active {
  border-left: 3px solid #18aa8d;
}

.workflow-entry.research {
  border-left: 3px solid #1677ff;
}

.entry-type {
  color: #0f766e;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.workflow-entry h3 {
  margin: 7px 0 0;
  color: #101828;
  font-size: 1rem;
}

.workflow-entry p {
  margin: 7px 0 0;
  color: #667085;
  font-size: 0.8rem;
  line-height: 1.6;
}

.metric-card,
.surface-panel {
  border: 1px solid rgba(166, 204, 247, 0.12);
  background: rgba(248, 251, 255, 0.96);
  box-shadow: 0 18px 40px rgba(2, 10, 18, 0.14);
}

.metric-card,
.surface-panel {
  padding: 18px;
}

.metric-card span,
.metric-card small,
.candidate-main small,
.quantum-head span,
.score-breakdown span,
.explanation-card span {
  color: #667085;
  font-size: 0.76rem;
}

.metric-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.08rem;
}

.metric-card small {
  display: block;
  margin-top: 8px;
  line-height: 1.55;
}

.metric-card.accent {
  background: linear-gradient(135deg, rgba(24, 186, 169, 0.12), rgba(55, 125, 255, 0.1)), #fff;
}

.screening-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.setup-column,
.result-column {
  display: grid;
  gap: 18px;
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

.candidate-list {
  margin-top: 18px;
  display: grid;
  gap: 10px;
}

.candidate-card,
.leaderboard-row {
  width: 100%;
  border: 1px solid #e6ebf2;
  display: grid;
  align-items: center;
  gap: 12px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.candidate-card {
  grid-template-columns: 32px minmax(0, 1fr) auto;
  padding: 12px;
}

.candidate-card:hover,
.leaderboard-row:hover {
  transform: translateY(-1px);
}

.candidate-card.selected,
.leaderboard-row.active {
  border-color: rgba(55, 125, 255, 0.34);
  background: rgba(55, 125, 255, 0.06);
}

.candidate-check {
  display: inline-flex;
}

.candidate-main strong {
  display: block;
  color: #101828;
  font-size: 0.92rem;
}

.candidate-main small {
  display: block;
  margin-top: 4px;
}

.candidate-score {
  color: #2456b8;
  font-size: 0.8rem;
  font-weight: 700;
}

.warning-card {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.24);
  background: rgba(245, 158, 11, 0.08);
  color: #7a4100;
  font-size: 0.82rem;
  line-height: 1.6;
}

.setup-actions {
  margin-top: 18px;
}

.flow-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.flow-item {
  padding: 12px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  display: grid;
  grid-template-columns: 40px 1fr;
  align-items: center;
  gap: 10px;
  background: #fff;
}

.flow-item span {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: #edf4ff;
  color: #2456b8;
  font-size: 0.74rem;
  font-weight: 800;
}

.flow-item strong {
  color: #101828;
  font-size: 0.88rem;
}

.flow-item.done {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(34, 197, 94, 0.05);
}

.empty-state {
  margin-top: 16px;
  padding: 18px;
  border: 1px dashed #d0d5dd;
  background: #fbfcfe;
}

.empty-state.compact {
  padding: 14px;
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

.leaderboard-list {
  margin-top: 18px;
  display: grid;
  gap: 10px;
}

.leaderboard-row {
  grid-template-columns: 48px minmax(160px, 1fr) minmax(160px, 0.7fr) 72px;
  padding: 14px;
}

.rank {
  color: #2456b8;
  font-size: 0.82rem;
  font-weight: 800;
}

.leaderboard-name strong {
  display: block;
  color: #101828;
}

.leaderboard-name small {
  display: block;
  margin-top: 5px;
  color: #667085;
  font-size: 0.72rem;
}

.score-bar {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #edf2f7;
}

.score-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #18baa9, #377dff);
}

.final-score {
  color: #101828;
  font-size: 1rem;
  font-weight: 800;
  text-align: right;
}

.table-wrap {
  margin-top: 18px;
  overflow-x: auto;
}

.screening-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

.screening-table th,
.screening-table td {
  padding: 12px;
  border-bottom: 1px solid #e6ebf2;
  text-align: left;
  font-size: 0.82rem;
}

.screening-table th {
  color: #667085;
  font-weight: 700;
  background: #f8fbff;
}

.screening-table td {
  color: #101828;
}

.table-empty {
  text-align: center;
  color: #98a2b3 !important;
}

.quantum-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.quantum-card {
  padding: 16px;
  border: 1px solid #e6ebf2;
  background: #f8fbff;
}

.quantum-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.quantum-head strong {
  color: #101828;
}

.quantum-stats {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.quantum-stats span {
  padding: 10px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  display: grid;
  gap: 6px;
  background: #fff;
  color: #667085;
  font-size: 0.72rem;
}

.quantum-stats b {
  color: #101828;
  font-size: 0.9rem;
}

.detail-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: minmax(280px, 0.84fr) minmax(0, 1.16fr);
  gap: 12px;
}

.score-breakdown,
.explanation-card {
  padding: 16px;
  border: 1px solid #e6ebf2;
  border-radius: 8px;
  background: #f8fbff;
}

.score-breakdown strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.2rem;
}

.score-stack {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.score-line {
  display: grid;
  grid-template-columns: 86px minmax(0, 1fr) 54px;
  align-items: center;
  gap: 10px;
}

.score-line span {
  color: #667085;
  font-size: 0.74rem;
}

.score-line i {
  height: 7px;
  border-radius: 999px;
  background: linear-gradient(90deg, #18baa9, #377dff);
}

.score-line b {
  color: #101828;
  text-align: right;
  font-size: 0.82rem;
}

.score-line.strong b {
  color: #0f766e;
  font-size: 0.92rem;
}

.explanation-card p {
  margin: 8px 0 18px;
  color: #344054;
  line-height: 1.75;
}

.explanation-card ul {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #475467;
  line-height: 1.75;
}

.mono {
  font-family: Consolas, 'SFMono-Regular', monospace;
}

.screening-page :deep(.el-button),
.screening-page :deep(.el-checkbox__inner) {
  border-radius: 8px;
}

@media (max-width: 1280px) {
  .screening-grid {
    grid-template-columns: 320px minmax(0, 1fr);
  }

  .quantum-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .screening-hero,
  .screening-grid,
  .screening-metrics,
  .workflow-entry-grid {
    grid-template-columns: 1fr;
  }

  .screening-hero {
    display: grid;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .leaderboard-row {
    grid-template-columns: 44px minmax(0, 1fr) 68px;
  }

  .score-bar {
    grid-column: 2 / -1;
  }
}

@media (max-width: 680px) {
  .quantum-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
