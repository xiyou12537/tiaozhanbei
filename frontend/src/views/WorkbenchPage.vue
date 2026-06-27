<template>
  <div class="workbench-page">
    <div class="banner">
      <div>
        <strong>这里是工作台，不再承担项目介绍。</strong>
        <p>首页负责讲清楚系统背景与基础知识；工作台只负责候选材料筛选、实验发起和当前原型可运行的分布式编译任务。</p>
      </div>
      <router-link to="/app/overview" class="banner-link">查看项目介绍</router-link>
    </div>

    <div class="top-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Candidate Workspace</span>
            <h2>候选材料筛选</h2>
          </div>
          <el-tag type="info" effect="light">工作台主入口</el-tag>
        </div>

        <div class="screening-toolbar">
          <div class="toolbar-item">
            <label>筛选目标</label>
            <div class="fake-input">高活性 + 可部署 + 可解释推荐</div>
          </div>
          <div class="toolbar-item">
            <label>实验模板</label>
            <div class="fake-input">完整链路模板 / 编译子域验证模板</div>
          </div>
          <div class="toolbar-item">
            <label>当前阶段</label>
            <div class="fake-input">{{ currentStageLabel }}</div>
          </div>
        </div>

        <div class="candidate-grid">
          <div v-for="item in candidatePool" :key="item.name" class="candidate-card">
            <div class="candidate-head">
              <strong>{{ item.name }}</strong>
              <el-tag size="small" :type="item.tagType" effect="light">{{ item.tag }}</el-tag>
            </div>
            <span class="candidate-focus">{{ item.focus }}</span>
            <p>{{ item.note }}</p>
            <div class="candidate-metrics">
              <div class="metric-chip"><span>化学潜力</span><strong>{{ item.chem }}</strong></div>
              <div class="metric-chip"><span>部署潜力</span><strong>{{ item.deploy }}</strong></div>
            </div>
          </div>
        </div>

        <div class="screening-actions">
          <button class="primary-btn" disabled>创建候选筛选任务</button>
          <router-link class="secondary-btn" to="/app/capability?tab=partition">进入当前可执行链路</router-link>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Queue</span>
            <h2>活动实验</h2>
          </div>
        </div>
        <div class="queue-list">
          <div v-for="item in previewExperimentQueue" :key="item.id" class="queue-item">
            <div class="queue-top">
              <strong>{{ item.caseName }}</strong>
              <span :class="['queue-badge', item.status]">{{ queueStatusMap[item.status] }}</span>
            </div>
            <small>{{ item.id }} · {{ item.owner }}</small>
            <div class="queue-progress">
              <span>{{ item.stage }}</span>
              <el-progress :percentage="item.progress" :show-text="false" :stroke-width="6" />
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="bottom-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Workflow State</span>
            <h2>当前实验状态</h2>
          </div>
        </div>
        <div class="summary-grid">
          <div class="summary-card">
            <span>当前工作流</span>
            <strong>{{ workflowHeadline }}</strong>
            <small>{{ workflowSubline }}</small>
          </div>
          <div class="summary-card">
            <span>当前阶段</span>
            <strong>{{ currentStageLabel }}</strong>
            <small>{{ shared.taskId ? `Task ${shared.taskId.slice(0, 8)}` : '尚未创建任务' }}</small>
          </div>
          <div class="summary-card">
            <span>分区结果</span>
            <strong>{{ partitionSummary }}</strong>
            <small>{{ shared.partitionResult ? `${shared.partitionResult.global_gates} 个全局门` : '等待分区计算' }}</small>
          </div>
          <div class="summary-card">
            <span>映射结果</span>
            <strong>{{ mappingSummary }}</strong>
            <small>{{ shared.mapping?.valid ? `${shared.mapping.total_epr_cost} EPR 代价` : '等待映射分析' }}</small>
          </div>
        </div>

        <div class="stage-list">
          <div
            v-for="stage in compactStages"
            :key="stage.key"
            class="stage-row"
            :class="resolveStageStatus(stage)"
          >
            <div class="stage-main">
              <div class="stage-title-row">
                <strong>{{ stage.label }}</strong>
                <span class="stage-status">{{ stageStatusLabel(resolveStageStatus(stage)) }}</span>
              </div>
              <span class="stage-owner">{{ stage.owner }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <span class="panel-kicker">Current Prototype</span>
            <h2>当前可执行结果摘要</h2>
          </div>
        </div>

        <div v-if="shared.circuit" class="info-block">
          <div class="info-head">
            <strong>输入工件</strong>
            <span>QASM</span>
          </div>
          <div class="info-grid">
            <div class="info-cell">
              <span>量子比特</span>
              <strong>{{ shared.circuit.num_qubits }}</strong>
            </div>
            <div class="info-cell">
              <span>总门数</span>
              <strong>{{ shared.circuit.total_gates }}</strong>
            </div>
            <div class="info-cell">
              <span>多比特门</span>
              <strong>{{ shared.circuit.multi_qubit_gates }}</strong>
            </div>
            <div class="info-cell">
              <span>电路 ID</span>
              <strong class="mono">{{ shared.circuit.circuit_id?.slice(0, 8) }}</strong>
            </div>
          </div>
        </div>

        <div v-if="shared.partitionResult" class="info-block">
          <div class="info-head">
            <strong>分布式编译结果</strong>
            <span>Distributed Compiler Service</span>
          </div>
          <div class="info-grid">
            <div class="info-cell">
              <span>分区数</span>
              <strong>{{ shared.partitionResult.num_partitions }}</strong>
            </div>
            <div class="info-cell">
              <span>传态次数</span>
              <strong>{{ shared.partitionResult.teleportations }}</strong>
            </div>
            <div class="info-cell">
              <span>优化后门数</span>
              <strong>{{ shared.partitionResult.optimized_gate_count }}</strong>
            </div>
            <div class="info-cell">
              <span>耗时</span>
              <strong>{{ shared.partitionResult.elapsed_seconds }}s</strong>
            </div>
          </div>
        </div>

        <div v-if="shared.mapping?.valid" class="info-block">
          <div class="info-head">
            <strong>映射聚合结果</strong>
            <span>Frontend aggregated view</span>
          </div>
          <div class="info-grid">
            <div class="info-cell">
              <span>EPR 代价</span>
              <strong>{{ shared.mapping.total_epr_cost }}</strong>
            </div>
            <div class="info-cell">
              <span>子图代价</span>
              <strong>{{ Math.round(shared.mapping.subgraph_cost || 0) }}</strong>
            </div>
            <div class="info-cell wide">
              <span>芯片映射</span>
              <strong class="mapping-text">{{ mappingPairs }}</strong>
            </div>
          </div>
        </div>

        <div v-if="!shared.circuit" class="empty-state">
          <strong>当前原型还没有运行任务</strong>
          <p>先在上方确定候选材料和实验目标，再进入编译能力页执行 QASM 上传、分区和映射。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { previewExperimentQueue, workflowStages } from '../platform'

const shared = inject('shared')

const candidatePool = [
  {
    name: 'Fe-N4 单原子位',
    tag: '优先验证',
    tagType: 'success',
    focus: '吸附位筛选 + 编译部署基线',
    note: '适合作为完整链路的默认案例，便于后续接入评分与推荐模块。',
    chem: '89.2',
    deploy: '76.4',
  },
  {
    name: 'CoS2 边缘位点',
    tag: '化学建模',
    tagType: 'warning',
    focus: '中间体稳定性与构型比较',
    note: '更适合验证 Chemistry Modeling Service 与活性位模板管理。',
    chem: '84.6',
    deploy: '81.9',
  },
  {
    name: 'Ni 团簇负载体系',
    tag: '编译联调',
    tagType: 'info',
    focus: 'QASM 工件输入 + 拓扑映射对比',
    note: '适合当前原型阶段直接跑分区与映射，验证部署代价差异。',
    chem: '78.8',
    deploy: '72.1',
  },
]

const compactStages = workflowStages.filter(stage =>
  ['created', 'validated', 'screening', 'distributed_compiling', 'aggregating', 'completed'].includes(stage.key)
)

const stageLabelMap = Object.fromEntries(workflowStages.map(item => [item.key, item.label]))

const queueStatusMap = {
  running: '运行中',
  queued: '排队中',
  completed: '已完成',
}

const currentStageLabel = computed(() => stageLabelMap[shared.currentStage] || '等待创建')

const workflowHeadline = computed(() => {
  if (shared.mapping?.valid) return '当前候选任务已得到部署结果'
  if (shared.partitionResult) return '候选任务已完成分区，等待映射'
  if (shared.workflowStatus === 'running') return '候选任务运行中'
  if (shared.circuit) return '实验输入已准备'
  return '尚未开始候选筛选任务'
})

const workflowSubline = computed(() => {
  if (shared.lastError) return shared.lastError
  if (shared.mapping?.valid) return '当前结果已经能作为后续统一结果视图的原型输入。'
  if (shared.partitionResult) return '可以继续进入映射分析，比较不同目标拓扑。'
  return '工作台先负责材料筛选与任务组织，具体计算由能力页执行。'
})

const partitionSummary = computed(() => {
  if (!shared.partitionResult) return '--'
  return `${shared.partitionResult.num_partitions} 个分区`
})

const mappingSummary = computed(() => {
  if (!shared.mapping?.valid) return '--'
  return `${Object.keys(shared.mapping.mapping || {}).length} 个芯片槽位`
})

const mappingPairs = computed(() => {
  const entries = Object.entries(shared.mapping?.mapping || {})
  if (!entries.length) return '--'
  return entries.map(([chip, part]) => `${chip} → ${part}`).join(' / ')
})

function resolveStageStatus(stage) {
  const rawStatus = shared.stageRuns?.[stage.key]
  if (rawStatus && rawStatus !== 'planned') return rawStatus
  if (stage.availability === 'planned') return 'planned'
  if (stage.availability === 'partial') return 'partial'
  return 'pending'
}

function stageStatusLabel(status) {
  const labelMap = {
    pending: '待执行',
    running: '运行中',
    success: '已完成',
    failed: '失败',
    retrying: '重试中',
    skipped: '跳过',
    partial: '部分接通',
    planned: '占位',
  }
  return labelMap[status] || '待执行'
}
</script>

<style scoped>
.workbench-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.banner,
.panel,
.summary-card,
.candidate-card,
.queue-item {
  background: #fff;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
}

.banner {
  padding: 18px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.banner strong {
  display: block;
  color: #101828;
  font-size: 0.96rem;
}

.banner p {
  margin-top: 6px;
  color: #667085;
  font-size: 0.82rem;
  line-height: 1.7;
}

.banner-link,
.primary-btn,
.secondary-btn {
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  font-size: 0.84rem;
  font-weight: 600;
}

.banner-link,
.secondary-btn {
  background: #fff;
  border-color: #dce4f2;
  color: #2456b8;
}

.primary-btn {
  background: linear-gradient(135deg, #2ec5a7, #4e7cff);
  color: #fff;
}

.top-grid,
.bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: 18px;
}

.panel {
  padding: 18px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-kicker,
.toolbar-item label,
.candidate-focus,
.summary-card span,
.stage-owner,
.info-cell span,
.info-head span,
.queue-item small {
  color: #667085;
  font-size: 0.74rem;
}

.panel-head h2 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.08rem;
}

.screening-toolbar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.toolbar-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fake-input {
  height: 42px;
  border-radius: 10px;
  border: 1px solid #e6e9f0;
  background: #fafcff;
  padding: 0 12px;
  display: flex;
  align-items: center;
  color: #344054;
  font-size: 0.82rem;
}

.candidate-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.candidate-card {
  padding: 16px;
}

.candidate-head,
.queue-top,
.panel-head,
.stage-title-row,
.info-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.candidate-head strong,
.queue-top strong,
.stage-title-row strong,
.info-head strong,
.summary-card strong {
  color: #101828;
}

.candidate-head strong {
  font-size: 0.92rem;
}

.candidate-card p,
.empty-state p {
  margin-top: 8px;
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.7;
}

.candidate-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}

.metric-chip {
  border: 1px solid #edf0f5;
  border-radius: 10px;
  padding: 10px;
  background: #fafcff;
}

.metric-chip span {
  display: block;
  color: #667085;
  font-size: 0.72rem;
}

.metric-chip strong {
  display: block;
  margin-top: 6px;
  color: #101828;
  font-size: 0.96rem;
}

.screening-actions {
  margin-top: 14px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.queue-list,
.stage-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.queue-item {
  padding: 14px;
  background: #fafcff;
}

.queue-badge {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 0.72rem;
  display: inline-flex;
  align-items: center;
}

.queue-badge.running {
  background: #ecfdf3;
  color: #027a48;
}

.queue-badge.queued {
  background: #eff4ff;
  color: #2456b8;
}

.queue-badge.completed {
  background: #f2f4f7;
  color: #475467;
}

.queue-progress {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  padding: 16px;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 1.02rem;
}

.summary-card small,
.stage-status {
  display: block;
  margin-top: 6px;
  color: #98a2b3;
  font-size: 0.74rem;
  line-height: 1.5;
}

.stage-list {
  margin-top: 14px;
}

.stage-row {
  border: 1px solid #edf0f5;
  border-radius: 12px;
  padding: 14px;
}

.stage-row.success {
  border-color: #cfe8dd;
  background: #f7fcf9;
}

.stage-row.running {
  border-color: #f5dfb3;
  background: #fffaf1;
}

.stage-row.failed {
  border-color: #f3c7c2;
  background: #fff7f6;
}

.stage-row.planned,
.stage-row.partial {
  background: #fafbfc;
}

.stage-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-block + .info-block {
  margin-top: 14px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.info-cell {
  border: 1px solid #edf0f5;
  border-radius: 12px;
  padding: 14px;
  background: #fafcff;
}

.info-cell strong {
  display: block;
  margin-top: 6px;
  color: #101828;
  font-size: 0.98rem;
}

.info-cell.wide {
  grid-column: 1 / -1;
}

.mono,
.mapping-text {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.84rem;
}

.empty-state {
  border: 1px dashed #d0d5dd;
  border-radius: 14px;
  padding: 22px;
  background: #fafbfc;
}

.empty-state strong {
  display: block;
  color: #101828;
}

@media (max-width: 1180px) {
  .top-grid,
  .bottom-grid,
  .screening-toolbar,
  .candidate-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid,
  .info-grid,
  .candidate-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
