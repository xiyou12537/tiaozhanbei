<template>
  <div class="public-stage-page">
    <section class="public-stage-hero">
      <div class="public-stage-shell">
        <div class="public-stage-grid">
          <div class="public-stage-copy">
            <span class="public-stage-kicker">Architecture</span>
            <h1>系统架构</h1>

            <div class="public-stage-actions">
              <router-link class="public-button" to="/app/screening">进入工作台</router-link>
              <router-link class="public-button-ghost" to="/workflow">查看流程页</router-link>
            </div>
          </div>

          <aside class="public-stage-aside">
            <span class="public-panel-kicker">Architecture Snapshot</span>
            <div class="public-stat-list">
              <article v-for="item in architectureStats" :key="item.title" class="public-stat-card">
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
            <span class="public-panel-kicker">System Layers</span>
            <h2>平台分层</h2>
          </div>
        </div>

        <div class="public-grid-3">
          <article v-for="item in architectureLayers" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Responsibility Boundary</span>
            <h2>前后端职责边界</h2>
          </div>
        </div>

        <div class="public-grid-3">
          <article v-for="item in boundaryCards" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="public-callout-card">
        <div>
          <span class="public-panel-kicker">Coordination</span>
          <strong>架构页负责说明分工，联调页负责证明接口真的打通</strong>
        </div>

        <div class="public-callout-actions">
          <router-link class="public-button" to="/app/screening">去工作台</router-link>
          <router-link class="public-button-secondary" to="/app/knowledge">去知识页</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useShowcase } from '../composables/useShowcase'

const { architectureLayers, boundaryCards } = useShowcase()

const architectureStats = computed(() => [
  {
    title: '平台层级',
    value: String(architectureLayers.length),
    text: '从展示层到结果与工件层的整体架构层数。',
  },
  {
    title: '统一契约',
    value: '/api/platform/**',
    text: '前端优先消费统一平台接口，而不是散落的能力端点。',
  },
  {
    title: '联调策略',
    value: '分层',
    text: '公共页负责解释结构，应用页负责执行真实任务与追踪状态。',
  },
])
</script>
