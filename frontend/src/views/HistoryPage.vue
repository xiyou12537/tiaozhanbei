<template>
  <div class="history-page">
    <section class="hero-console">
      <img class="hero-image" :src="heroImage" alt="历史记录主视觉" />
      <div class="hero-overlay"></div>

      <div class="hero-content">
        <div class="hero-copy">
          <span class="panel-kicker">Workflow Archive</span>
          <h2>历史记录</h2>
        </div>

        <div class="hero-stats">
          <div class="stat-card">
            <span>平台归档</span>
            <strong>{{ workflowArchive.length }}</strong>
          </div>
          <div class="stat-card">
            <span>筛选任务</span>
            <strong>{{ screeningArchive.length }}</strong>
          </div>
          <div class="stat-card">
            <span>平台完成</span>
            <strong>{{ archiveCompletedCount }}</strong>
          </div>
          <div class="stat-card">
            <span>编译记录</span>
            <strong>{{ records.length }}</strong>
          </div>
          <div class="stat-card">
            <span>平均传态</span>
            <strong>{{ avgTeleport }}</strong>
          </div>
        </div>
      </div>
    </section>

    <section class="surface-panel">
      <div class="panel-head">
        <div>
          <span class="panel-kicker panel-kicker-dark">Screening Archive</span>
          <h3>多材料筛选任务</h3>
        </div>
        <el-button size="small" class="refresh-btn" @click="loadArchive">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <div class="panel-body">
        <div v-if="!screeningArchive.length" class="empty-state archive-empty">
          <div class="empty-icon">
            <el-icon :size="40"><FolderOpened /></el-icon>
          </div>
          <h4>暂无多材料筛选归档</h4>
          <p>在筛选工作台创建任务后，这里会记录最近的 screening workflow，并支持重新进入结果页。</p>
          <el-button type="primary" @click="$router.push('/app/screening')">前往筛选工作台</el-button>
        </div>

        <div v-else class="timeline-list archive-list">
          <article v-for="item in screeningArchive" :key="item.workflowId" class="timeline-card archive-card">
            <div class="timeline-top">
              <div>
                <span class="time-stamp">{{ item.createdAt?.slice(0, 19) || item.updatedAt?.slice(0, 19) || '--' }}</span>
                <strong class="timeline-title">
                  <ChemicalFormula :text="item.recommendedMaterial || 'Screening Workflow'" />
                </strong>
              </div>
              <el-tag :type="item.status === 'completed' ? 'success' : item.status === 'failed' ? 'danger' : 'warning'" size="small">
                {{ item.status || 'created' }}
              </el-tag>
            </div>

            <div class="metric-grid screening-metric-grid">
              <div class="metric-box">
                <span>Workflow ID</span>
                <strong class="mono">{{ item.workflowId?.slice(0, 8) || '--' }}</strong>
              </div>
              <div class="metric-box">
                <span>Case ID</span>
                <strong class="mono">{{ item.caseId || '--' }}</strong>
              </div>
              <div class="metric-box">
                <span>候选材料数</span>
                <strong>{{ item.candidateCount || item.selectedCandidates?.length || '--' }}</strong>
              </div>
              <div class="metric-box accent">
                <span>推荐材料</span>
                <strong><ChemicalFormula :text="item.recommendedMaterial || '--'" /></strong>
              </div>
            </div>

            <div class="timeline-meta">
              <span class="meta-item">source={{ item.source || 'backend' }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">created={{ item.createdAt?.slice(0, 19) || '--' }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">updated={{ item.updatedAt?.slice(0, 19) || '--' }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">candidates={{ item.selectedCandidates?.join(' / ') || '--' }}</span>
            </div>

            <div class="history-actions">
              <el-button
                type="primary"
                size="small"
                @click="$router.push({ path: '/app/results', query: { workflowId: item.workflowId } })"
              >
                进入结果页
              </el-button>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="surface-panel">
      <div class="panel-head">
        <div>
          <span class="panel-kicker panel-kicker-dark">Platform Archive</span>
          <h3>平台工作流归档</h3>
        </div>
        <el-button size="small" :loading="loading" class="refresh-btn" @click="loadHistory">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <div v-loading="loading" class="panel-body">
        <div v-if="!workflowArchive.length" class="empty-state archive-empty">
          <div class="empty-icon">
            <el-icon :size="40"><FolderOpened /></el-icon>
          </div>
          <h4>暂无平台工作流归档</h4>
          <p>从工作台创建并刷新过平台任务后，这里会自动归档最近的工作流快照。</p>
          <el-button type="primary" @click="$router.push('/app/screening')">前往工作台</el-button>
        </div>

        <div v-else class="timeline-list archive-list">
          <article v-for="item in workflowArchive" :key="item.workflowId" class="timeline-card archive-card">
            <div class="timeline-top">
              <div>
                <span class="time-stamp">{{ item.updatedAt?.slice(0, 19) || '--' }}</span>
                <strong class="timeline-title">
                  <ChemicalFormula :text="item.candidateMaterial || 'Platform Workflow'" />
                </strong>
              </div>
              <el-tag
                :type="item.overallStatus === 'completed' ? 'success' : item.overallStatus === 'cancelled' ? 'info' : 'warning'"
                size="small"
                effect="light"
              >
                {{ item.overallStatus || 'created' }}
              </el-tag>
            </div>

            <div class="metric-grid">
              <div class="metric-box">
                <span>工作流 ID</span>
                <strong class="mono">{{ item.workflowId?.slice(0, 8) }}</strong>
              </div>
              <div class="metric-box">
                <span>当前阶段</span>
                <strong>{{ item.currentStage || '--' }}</strong>
              </div>
              <div class="metric-box accent">
                <span>Final Score</span>
                <strong>{{ item.resultSummary?.final_score ?? '--' }}</strong>
              </div>
              <div class="metric-box">
                <span>排名</span>
                <strong>{{ item.resultSummary?.rank_position ?? '--' }}</strong>
              </div>
              <div class="metric-box">
                <span>进度</span>
                <strong>{{ item.completedStageCount ?? 0 }}/{{ item.totalStageCount ?? 7 }}</strong>
              </div>
            </div>

            <div class="timeline-meta">
              <span class="meta-item">mode={{ item.executionMode || '--' }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">gate={{ formatBooleanResult(item.resultSummary?.gatekeeping_passed) }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">screening={{ formatBooleanResult(item.resultSummary?.screening_passed) }}</span>
            </div>

            <div v-if="item.scientificSnapshot" class="tag-block">
              <span class="tag-label">科学指标</span>
              <el-tag size="small" effect="plain" class="part-tag">qubit={{ item.scientificSnapshot.qubit_count ?? '--' }}</el-tag>
              <el-tag size="small" effect="plain" class="part-tag">partition={{ item.scientificSnapshot.partition_count ?? '--' }}</el-tag>
              <el-tag size="small" effect="plain" class="part-tag">teleport={{ item.scientificSnapshot.teleportations ?? '--' }}</el-tag>
              <el-tag size="small" effect="plain" class="part-tag">fidelity={{ item.scientificSnapshot.fidelity_score ?? '--' }}</el-tag>
            </div>

            <div v-if="item.artifacts" class="tag-block">
              <span class="tag-label">结果工件</span>
              <el-tag size="small" type="success" effect="plain" class="map-tag">
                topology={{ item.artifacts.topology_name || '--' }}
              </el-tag>
              <el-tag size="small" type="success" effect="plain" class="map-tag">
                qasm={{ Array.isArray(item.artifacts.qasm_preview) ? item.artifacts.qasm_preview.length : 0 }} lines
              </el-tag>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="surface-panel">
      <div class="panel-head">
        <div>
          <span class="panel-kicker panel-kicker-dark">Capability Timeline</span>
          <h3>旧版编译记录</h3>
        </div>
      </div>

      <div v-loading="loading" class="panel-body">
        <div v-if="!loading && records.length === 0" class="empty-state">
          <div class="empty-icon">
            <el-icon :size="40"><FolderOpened /></el-icon>
          </div>
          <h4>暂无编译记录</h4>
          <p>完成一次分区计算后，旧版编译结果会继续保存在这里。</p>
          <el-button type="primary" @click="$router.push('/app/capability?tab=partition')">
            <el-icon><Cpu /></el-icon>
            前往能力页
          </el-button>
        </div>

        <div v-if="records.length" class="timeline-list">
          <article v-for="rec in records" :key="rec.task_id" class="timeline-card">
            <div class="timeline-top">
              <div>
                <span class="time-stamp">{{ rec.created_at?.slice(0, 19) || '--' }}</span>
                <strong class="timeline-title"><ChemicalFormula :text="rec.circuit_name" /></strong>
              </div>
              <el-tag :type="rec.status === 'completed' ? 'success' : 'danger'" size="small" effect="light">
                {{ rec.status === 'completed' ? '已完成' : '失败' }}
              </el-tag>
            </div>

            <div class="metric-grid">
              <div class="metric-box">
                <span>量子比特</span>
                <strong>{{ rec.num_qubits }}</strong>
              </div>
              <div class="metric-box">
                <span>总门数</span>
                <strong>{{ rec.total_gates }}</strong>
              </div>
              <div class="metric-box accent">
                <span>传态次数</span>
                <strong>{{ rec.result?.teleportations ?? '?' }}</strong>
              </div>
              <div class="metric-box">
                <span>全局门数</span>
                <strong>{{ rec.result?.global_gates ?? '?' }}</strong>
              </div>
              <div class="metric-box">
                <span>耗时</span>
                <strong class="mono">{{ rec.elapsed_seconds }}s</strong>
              </div>
            </div>

            <div class="timeline-meta">
              <span class="meta-item">k={{ rec.params?.num_partitions }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">b1={{ rec.params?.b1 }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">b2={{ rec.params?.b2 }}</span>
            </div>

            <div v-if="rec.result?.partitions?.length" class="tag-block">
              <span class="tag-label">分区结果</span>
              <el-tag
                v-for="p in rec.result.partitions"
                :key="p.index"
                size="small"
                effect="plain"
                class="part-tag"
              >
                P{{ p.index + 1 }}({{ p.size }})
              </el-tag>
            </div>

            <div v-if="rec.mappings?.length" class="tag-block">
              <span class="tag-label">芯片映射</span>
              <el-tag
                v-for="m in rec.mappings"
                :key="m.topology_name"
                size="small"
                type="success"
                effect="plain"
                class="map-tag"
              >
                {{ m.topology_name }}: EPR={{ m.epr_cost }}
              </el-tag>
            </div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchUserHistory } from '../api'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import { readArchivedScreeningWorkflows } from '../services/screeningArchiveStorage'
import { fetchScreeningWorkflowHistory } from '../services/screeningWorkflowService'
import { readArchivedWorkflows } from '../services/workflowArchiveStorage'
import heroImage from '../assets/chemistry-hero.png'

const records = ref([])
const workflowArchive = ref([])
const screeningArchive = ref([])
const loading = ref(false)

const archiveCompletedCount = computed(() =>
  workflowArchive.value.filter(item => item.overallStatus === 'completed').length
)

const avgTeleport = computed(() => {
  const values = records.value
    .map(item => item.result?.teleportations)
    .filter(value => typeof value === 'number')

  if (!values.length) return '--'

  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)
})

async function loadArchive() {
  workflowArchive.value = readArchivedWorkflows()
  try {
    const backendArchive = await fetchScreeningWorkflowHistory()
    screeningArchive.value = backendArchive.length ? backendArchive : readArchivedScreeningWorkflows()
  } catch (error) {
    console.error('load screening workflow archive failed:', error)
    screeningArchive.value = readArchivedScreeningWorkflows()
  }
}

async function loadHistory() {
  loading.value = true
  try {
    await loadArchive()
    const { data } = await fetchUserHistory()
    records.value = data.history || []
  } catch (error) {
    console.error('load history failed:', error)
  } finally {
    loading.value = false
  }
}

function formatBooleanResult(value) {
  if (value === true) return 'passed'
  if (value === false) return 'failed'
  return '--'
}

onMounted(loadHistory)
</script>

<style scoped>
.history-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-console {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  background: #081a2c;
  min-height: 280px;
}

.hero-image,
.hero-overlay {
  position: absolute;
  inset: 0;
}

.hero-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero-overlay {
  background:
    linear-gradient(90deg, rgba(4, 13, 24, 0.92) 0%, rgba(4, 13, 24, 0.68) 45%, rgba(4, 13, 24, 0.42) 100%),
    linear-gradient(180deg, rgba(8, 18, 32, 0.16) 0%, rgba(8, 18, 32, 0.58) 100%);
}

.hero-content {
  position: relative;
  z-index: 1;
  min-height: 280px;
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.9fr);
  gap: 18px;
  align-items: end;
}

.panel-kicker {
  color: #67d5ca;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}

.panel-kicker-dark {
  color: #0f766e;
}

.hero-copy h2 {
  margin-top: 6px;
  font-size: 1.18rem;
  color: #f8fbff;
}

.hero-copy p {
  margin-top: 10px;
  max-width: 760px;
  color: rgba(228, 236, 246, 0.84);
  font-size: 0.84rem;
  line-height: 1.75;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(166, 204, 247, 0.16);
  background: rgba(8, 20, 35, 0.58);
  backdrop-filter: blur(12px);
}

.stat-card span {
  color: rgba(223, 232, 243, 0.72);
  font-size: 0.74rem;
}

.stat-card strong {
  display: block;
  margin-top: 8px;
  color: #f8fbff;
  font-size: 1.16rem;
}

.surface-panel {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.02rem;
}

.panel-body {
  margin-top: 14px;
}

.timeline-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.archive-list {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.timeline-card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid #e6ebf2;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
}

.archive-card {
  background: linear-gradient(180deg, #ffffff, #f7fbff);
}

.timeline-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.time-stamp {
  display: block;
  color: #98a2b3;
  font-size: 0.72rem;
}

.timeline-title {
  display: block;
  margin-top: 6px;
  color: #101828;
}

.metric-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.metric-box {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.metric-box.accent {
  background: linear-gradient(180deg, #f7fbff, #ffffff);
}

.metric-box span,
.tag-label,
.meta-item {
  color: #667085;
  font-size: 0.74rem;
}

.metric-box strong {
  display: block;
  margin-top: 6px;
  color: #101828;
}

.mono {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}

.timeline-meta {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  color: #98a2b3;
}

.tag-block {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.history-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.empty-state {
  padding: 24px;
  border-radius: 16px;
  border: 1px dashed #d0d5dd;
  background: #fafbfc;
  text-align: center;
}

.empty-icon {
  color: #98a2b3;
  margin-bottom: 12px;
}

.empty-state h4 {
  color: #101828;
}

.empty-state p {
  margin-top: 8px;
  color: #667085;
  line-height: 1.7;
}

@media (max-width: 1100px) {
  .hero-content,
  .timeline-list,
  .archive-list,
  .metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
