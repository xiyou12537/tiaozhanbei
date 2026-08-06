<template>
  <div class="public-stage-page">
    <section class="public-stage-hero">
      <div class="public-stage-shell">
        <div class="public-stage-grid">
          <div class="public-stage-copy">
            <span class="public-stage-kicker">Overview</span>
            <h1>项目总览</h1>

            <div class="public-stage-actions">
              <router-link class="public-button" to="/app/screening">进入筛选工作台</router-link>
              <router-link class="public-button-ghost" to="/workflow">查看系统流程</router-link>
            </div>
          </div>

          <aside class="public-stage-aside">
            <span class="public-panel-kicker">Page Focus</span>
            <div class="public-stat-list">
              <article v-for="item in pageFocusCards" :key="item.title" class="public-stat-card">
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
            <span class="public-panel-kicker">Problem Framing</span>
            <h2>从问题定义到平台目标</h2>
          </div>
          <router-link class="public-inline-link" to="/architecture">查看系统架构</router-link>
        </div>

        <div class="public-grid-2">
          <article v-for="item in overviewCards" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Key Challenges</span>
            <h2>项目难点与工程挑战</h2>
          </div>
          <router-link class="public-inline-link" to="/highlights">查看技术亮点</router-link>
        </div>

        <div class="public-grid-2">
          <article v-for="item in challengeCards" :key="item.title" class="public-info-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </article>
        </div>
      </section>

      <section class="public-callout-card">
        <div>
          <span class="public-panel-kicker">Next Step</span>
          <strong>背景和动机在这里，真实任务从工作台开始</strong>
        </div>

        <div class="public-callout-actions">
          <router-link class="public-button" to="/app/screening">进入工作台</router-link>
          <router-link class="public-button-secondary" to="/results">查看结果示例</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useShowcase } from '../composables/useShowcase'

const { challengeCards, overviewCards } = useShowcase()

const pageFocusCards = computed(() => [
  {
    title: '项目定位',
    value: '平台化',
    text: '',
  },
  {
    title: '问题范围',
    value: '跨域',
    text: '',
  },
  {
    title: '入口职责',
    value: '导流',
    text: '',
  },
])
</script>
