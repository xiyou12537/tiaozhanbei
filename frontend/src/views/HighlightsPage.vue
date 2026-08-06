<template>
  <div class="public-stage-page">
    <section class="public-stage-hero">
      <div class="public-stage-shell">
        <div class="public-stage-grid">
          <div class="public-stage-copy">
            <span class="public-stage-kicker">Highlights</span>
            <h1>技术亮点</h1>

            <div class="public-stage-actions">
              <router-link class="public-button" to="/app/screening">进入工作台</router-link>
              <router-link class="public-button-ghost" to="/app/capability">查看编译能力页</router-link>
            </div>
          </div>

          <aside class="public-stage-aside">
            <span class="public-panel-kicker">Pitch Snapshot</span>
            <div class="public-stat-list">
              <article v-for="item in pitchCards" :key="item.title" class="public-stat-card">
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
            <span class="public-panel-kicker">Project Highlights</span>
            <h2>差异化能力</h2>
          </div>
          <router-link class="public-inline-link" to="/overview">返回项目总览</router-link>
        </div>

        <div class="public-grid-2">
          <article v-for="item in highlightGroups" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="public-callout-card">
        <div>
          <span class="public-panel-kicker">Next Step</span>
          <strong>亮点页负责概括价值，真实性仍要回到系统页面证明</strong>
        </div>

        <div class="public-callout-actions">
          <router-link class="public-button" to="/app/screening">进入工作台</router-link>
          <router-link class="public-button-secondary" to="/app/results">打开结果页</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useShowcase } from '../composables/useShowcase'

const { highlightGroups } = useShowcase()

const pitchCards = computed(() => [
  {
    title: '场景表达',
    value: '系统化',
    text: '不是单页汇报，而是直接组织成可进入、可联调、可追踪的平台。',
  },
  {
    title: '工程状态',
    value: '联调中',
    text: '工作流、结果页、知识页和编译能力页已经形成完整前端骨架。',
  },
  {
    title: '证明方式',
    value: '页面 + 接口',
    text: '既能展示页面结构，也能通过真实接口与任务状态证明系统可运行。',
  },
])
</script>
