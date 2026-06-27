<template>
  <div class="preview-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <span class="hero-kicker">System Preview</span>
        <h2>量智硫光最终系统预览</h2>
        <p>
          这个页面不局限于当前已接通的后端接口，而是把目标平台的最终信息结构先做出来。
          你后面只需要围绕这个预览提修改，我再把它逐步替换成真实接口和真实流程。
        </p>
        <div class="hero-actions">
          <router-link class="primary-btn" to="/app/workbench">看真实工作台原型</router-link>
          <router-link class="secondary-btn" to="/app/capability?tab=partition">看当前已接通能力</router-link>
        </div>
      </div>
      <div class="hero-metrics">
        <div class="metric-card">
          <span>平台服务</span>
          <strong>12</strong>
          <small>按领域职责分离</small>
        </div>
        <div class="metric-card">
          <span>工作流阶段</span>
          <strong>10</strong>
          <small>统一状态机追踪</small>
        </div>
        <div class="metric-card">
          <span>当前可运行子域</span>
          <strong>1</strong>
          <small>分布式编译原型</small>
        </div>
        <div class="metric-card">
          <span>前端视图层</span>
          <strong>3</strong>
          <small>展示层 / 工作台 / 能力页</small>
        </div>
      </div>
    </section>

    <section class="main-grid">
      <div class="column-main">
        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Launchpad</span>
              <h3>实验发起面板</h3>
            </div>
            <el-tag type="info" effect="light">预览结构</el-tag>
          </div>
          <div class="launchpad-grid">
            <div class="launch-card">
              <label>预置案例</label>
              <div class="fake-input">Fe-N4 单原子催化位 / 吸附位筛选</div>
            </div>
            <div class="launch-card">
              <label>实验模板</label>
              <div class="fake-input">完整链路模板 · screening → scoring</div>
            </div>
            <div class="launch-card">
              <label>量子工件入口</label>
              <div class="fake-input">QASM artifact / circuit skeleton</div>
            </div>
            <div class="launch-card">
              <label>执行策略</label>
              <div class="fake-input">同步元数据 + 异步领域任务</div>
            </div>
          </div>
          <div class="launchpad-footer">
            <span>预览意图：把“新建实验”做成一个平台入口，而不是电路上传表单。</span>
            <button class="ghost-btn" disabled>创建实验工作流</button>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Workflow Orchestration</span>
              <h3>统一编排视图</h3>
            </div>
          </div>
          <div class="workflow-grid">
            <div
              v-for="stage in workflowStages"
              :key="stage.key"
              class="workflow-card"
              :class="stage.availability"
            >
              <div class="workflow-card-head">
                <strong>{{ stage.label }}</strong>
                <span>{{ stage.owner }}</span>
              </div>
              <p>{{ stage.description }}</p>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Result Workspace</span>
              <h3>结果看板预览</h3>
            </div>
          </div>
          <div class="result-grid">
            <div class="result-card score">
              <span>综合评分</span>
              <strong>83.7</strong>
              <small>FinalScore / recommendation rank #1</small>
            </div>
            <div class="result-card chem">
              <span>化学性能</span>
              <strong>89.2</strong>
              <small>adsorption / stability / reaction profile</small>
            </div>
            <div class="result-card deploy">
              <span>部署代价</span>
              <strong>76.4</strong>
              <small>partition / mapping / communication efficiency</small>
            </div>
            <div class="result-card artifacts">
              <span>输出资产</span>
              <strong>5</strong>
              <small>result_view / chart_dataset / report_bundle</small>
            </div>
          </div>
          <div class="recommend-grid">
            <div v-for="item in previewRecommendationCards" :key="item.title" class="recommend-card">
              <span>{{ item.title }}</span>
              <strong>{{ item.primary }}</strong>
              <small>{{ item.secondary }}</small>
              <p>{{ item.note }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="column-side">
        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Queue</span>
              <h3>活动工作流</h3>
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
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Service Health</span>
              <h3>服务运行面板</h3>
            </div>
          </div>
          <div class="health-list">
            <div v-for="service in previewServiceHealth" :key="service.name" class="health-row">
              <div>
                <strong>{{ service.name }}</strong>
                <small>{{ service.latency }} · {{ service.successRate }}</small>
              </div>
              <span :class="['health-badge', service.status]">{{ healthStatusMap[service.status] }}</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Artifacts</span>
              <h3>工件与审计</h3>
            </div>
          </div>
          <div class="artifact-list">
            <div v-for="artifact in previewArtifacts" :key="artifact.name" class="artifact-row">
              <div class="artifact-main">
                <strong>{{ artifact.name }}</strong>
                <small>{{ artifact.domain }}</small>
              </div>
              <div class="artifact-meta">
                <span>{{ artifact.type }}</span>
                <small>{{ artifact.owner }}</small>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">Boundary</span>
              <h3>服务边界卡片</h3>
            </div>
          </div>
          <div class="boundary-list">
            <div v-for="service in compactServices" :key="service.name" class="boundary-item">
              <strong>{{ service.name }}</strong>
              <span>{{ service.boundary }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import {
  platformServices,
  previewArtifacts,
  previewExperimentQueue,
  previewRecommendationCards,
  previewServiceHealth,
  workflowStages,
} from '../platform'

const queueStatusMap = {
  running: '运行中',
  queued: '排队中',
  completed: '已完成',
}

const healthStatusMap = {
  healthy: '正常',
  planned: '规划中',
}

const compactServices = platformServices.slice(0, 6)
</script>

<style scoped>
.preview-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-panel,
.panel,
.metric-card,
.launch-card,
.workflow-card,
.result-card,
.recommend-card {
  background: #fff;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
}

.hero-panel {
  padding: 22px;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
}

.hero-kicker,
.panel-kicker {
  color: #667085;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hero-copy h2 {
  margin-top: 8px;
  font-size: 1.5rem;
  color: #101828;
}

.hero-copy p {
  margin-top: 10px;
  color: #475467;
  font-size: 0.86rem;
  line-height: 1.8;
  max-width: 760px;
}

.hero-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.primary-btn,
.secondary-btn,
.ghost-btn {
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

.primary-btn {
  background: linear-gradient(135deg, #2ec5a7, #4e7cff);
  color: #fff;
}

.secondary-btn {
  background: #fff;
  border-color: #dce4f2;
  color: #2456b8;
}

.ghost-btn {
  background: #f8fafc;
  color: #98a2b3;
  border-color: #e6e9f0;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  padding: 16px;
}

.metric-card span,
.metric-card small,
.queue-item small,
.artifact-main small,
.artifact-meta small,
.workflow-card-head span,
.result-card small,
.recommend-card small,
.boundary-item span,
.health-row small,
.launch-card label {
  color: #667085;
  font-size: 0.74rem;
}

.metric-card strong {
  display: block;
  margin-top: 8px;
  font-size: 1.4rem;
  color: #101828;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.85fr);
  gap: 18px;
}

.column-main,
.column-side {
  display: flex;
  flex-direction: column;
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

.panel-head h3 {
  margin-top: 6px;
  font-size: 1.04rem;
  color: #101828;
}

.launchpad-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.launch-card {
  padding: 14px;
}

.fake-input {
  margin-top: 8px;
  height: 42px;
  border-radius: 10px;
  border: 1px solid #e6e9f0;
  background: #fafcff;
  display: flex;
  align-items: center;
  padding: 0 12px;
  color: #344054;
  font-size: 0.82rem;
}

.launchpad-footer {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #edf0f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #667085;
  font-size: 0.78rem;
}

.workflow-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.workflow-card {
  padding: 14px;
}

.workflow-card.online {
  border-color: #cfe8dd;
}

.workflow-card.partial {
  border-color: #f4ddb3;
}

.workflow-card.planned {
  background: #fafbfc;
}

.workflow-card-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.workflow-card-head strong,
.queue-top strong,
.health-row strong,
.artifact-main strong,
.boundary-item strong,
.recommend-card strong {
  color: #101828;
  font-size: 0.9rem;
}

.workflow-card p,
.recommend-card p {
  margin-top: 8px;
  color: #475467;
  font-size: 0.8rem;
  line-height: 1.6;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.result-card {
  padding: 16px;
}

.result-card span,
.recommend-card span,
.queue-progress span,
.artifact-meta span {
  color: #667085;
  font-size: 0.74rem;
}

.result-card strong {
  display: block;
  margin-top: 10px;
  color: #101828;
  font-size: 1.36rem;
}

.score { background: linear-gradient(180deg, #f7fcf9, #fff); }
.chem { background: linear-gradient(180deg, #f7fbff, #fff); }
.deploy { background: linear-gradient(180deg, #fffaf1, #fff); }
.artifacts { background: linear-gradient(180deg, #fbf8ff, #fff); }

.recommend-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.recommend-card {
  padding: 16px;
}

.queue-list,
.health-list,
.artifact-list,
.boundary-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.queue-item,
.health-row,
.artifact-row,
.boundary-item {
  border: 1px solid #edf0f5;
  border-radius: 12px;
  padding: 14px;
  background: #fafcff;
}

.queue-top,
.health-row,
.artifact-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.queue-badge,
.health-badge {
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  flex-shrink: 0;
}

.queue-badge.running,
.health-badge.healthy {
  background: #ecfdf3;
  color: #027a48;
}

.queue-badge.queued,
.health-badge.planned {
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

.artifact-main,
.artifact-meta,
.boundary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.artifact-meta {
  align-items: flex-end;
}

@media (max-width: 1180px) {
  .hero-panel,
  .main-grid,
  .result-grid,
  .recommend-grid,
  .workflow-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .hero-panel,
  .panel {
    padding: 16px;
  }

  .hero-metrics,
  .launchpad-grid {
    grid-template-columns: 1fr;
  }

  .launchpad-footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
