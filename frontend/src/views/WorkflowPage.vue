<template>
  <div class="public-stage-page">
    <section class="public-stage-hero">
      <div class="public-stage-shell">
        <div class="public-stage-grid">
          <div class="public-stage-copy">
            <span class="public-stage-kicker">Workflow</span>
            <h1>筛选流程</h1>

            <div class="public-stage-actions">
              <router-link class="public-button" to="/app/screening">发起筛选任务</router-link>
              <router-link class="public-button-ghost" to="/app/results">查看应用结果页</router-link>
            </div>
          </div>

          <aside class="public-stage-aside">
            <span class="public-panel-kicker">Flow Snapshot</span>
            <div class="public-stat-list">
              <article v-for="item in workflowStats" :key="item.title" class="public-stat-card">
                <span>{{ item.title }}</span>
                <strong>{{ item.value }}</strong>
                <small>{{ item.text }}</small>
              </article>
            </div>
          </aside>
        </div>
      </div>
    </section>

    <div class="public-stage-shell public-stage-stack">
      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Stage Summary</span>
            <h2>流程的三段式理解</h2>
          </div>
        </div>

        <div class="public-grid-3">
          <article v-for="item in phaseCards" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Detailed Stages</span>
            <h2>完整阶段明细</h2>
          </div>
          <router-link class="public-inline-link" to="/app/screening">去工作台查看实时状态</router-link>
        </div>

        <div class="public-list-stack">
          <article v-for="(item, index) in workflowSteps" :key="item.key" class="public-step-card">
            <span class="public-step-index">{{ index + 1 }}</span>
            <div>
              <strong>{{ item.title }}</strong>

              <div class="public-step-fields">
                <div>
                  <span class="public-field-label">输入</span>
                  <div class="public-field-text">{{ item.input }}</div>
                </div>
                <div>
                  <span class="public-field-label">处理</span>
                  <div class="public-field-text">{{ item.process }}</div>
                </div>
                <div>
                  <span class="public-field-label">输出</span>
                  <div class="public-field-text">{{ item.output }}</div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="public-callout-card">
        <div>
          <span class="public-panel-kicker">Execution</span>
          <strong>流程页负责讲结构，工作台负责跑任务</strong>
        </div>

        <div class="public-callout-actions">
          <router-link class="public-button" to="/app/screening">进入工作台</router-link>
          <router-link class="public-button-secondary" to="/results">查看示例结果</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useShowcase } from '../composables/useShowcase'

const { workflowSteps } = useShowcase()

const phaseCards = [
  {
    title: '经典粗筛',
    text: '从案例和候选材料出发，建立候选上下文，为后续建模准备统一入口。',
  },
  {
    title: '化学到量子的转换',
    text: '把科学问题映射成可编码、可编译的量子对象，形成明确工件边界。',
  },
  {
    title: '编译、评估与聚合',
    text: '完成分布式编译、模拟评估、综合评分，并统一收束到结果视图。',
  },
]

const workflowStats = computed(() => [
  {
    title: '阶段数量',
    value: String(workflowSteps.length),
    text: '前后端对齐的完整工作流阶段数。',
  },
  {
    title: '执行模式',
    value: 'queued',
    text: '支持异步推进、轮询刷新和任务日志追踪。',
  },
  {
    title: '统一输出',
    value: 'result_view',
    text: '所有阶段最终汇总为统一结果视图结构。',
  },
])
</script>
