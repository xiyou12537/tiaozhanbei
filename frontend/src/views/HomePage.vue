<template>
  <div class="intro-page" :class="{ embedded: isEmbedded }">
    <header v-if="!isEmbedded" class="public-header">
      <div class="header-inner">
        <div class="brand">
          <div class="brand-mark">LZ</div>
          <div class="brand-copy">
            <span class="brand-name">量智硫光</span>
            <span class="brand-sub">锂硫电池催化材料筛选平台</span>
          </div>
        </div>
        <div class="header-actions">
          <button v-if="!isLoggedIn" class="text-btn" @click="openAuth('login')">登录</button>
          <button v-if="!isLoggedIn" class="primary-btn" @click="openAuth('register')">进入工作台</button>
          <router-link v-else class="primary-btn" to="/app/workbench">进入工作台</router-link>
        </div>
      </div>
    </header>

    <section class="section hero">
      <div class="section-inner hero-grid">
        <div class="hero-main">
          <span class="eyebrow">项目介绍</span>
          <h1>量智硫光</h1>
          <p class="hero-text">
            这个系统的目标不是单纯做一个量子线路工具，而是围绕锂硫电池催化材料筛选，
            把候选材料、化学建模、量子问题构造、分布式量子编译、模拟评估和综合推荐串成一条完整工作流。
          </p>
          <div class="hero-actions">
            <router-link v-if="isLoggedIn" to="/app/workbench" class="primary-btn">开始候选材料筛选</router-link>
            <button v-else class="primary-btn" @click="openAuth('register')">注册并进入工作台</button>
            <router-link v-if="isLoggedIn" to="/app/preview" class="secondary-btn">查看系统蓝图</router-link>
          </div>
        </div>

        <div class="hero-side">
          <div class="summary-card">
            <span class="summary-label">当前原型已接通</span>
            <strong>分布式编译子域</strong>
            <p>认证、QASM 上传、分区、映射、历史、导出、AI 会话已经可运行；其余阶段先通过统一界面占位，不让前端提前绑定不存在的领域接口。</p>
          </div>
        </div>
      </div>
    </section>

    <section class="section muted">
      <div class="section-inner">
        <div class="section-title-row">
          <div>
            <span class="section-kicker">Background</span>
            <h2>这个项目在解决什么问题</h2>
          </div>
        </div>
        <div class="card-grid">
          <div class="info-card" v-for="item in backgroundCards" :key="item.title">
            <h3>{{ item.title }}</h3>
            <p>{{ item.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-inner">
        <div class="section-title-row">
          <div>
            <span class="section-kicker">Motivation</span>
            <h2>为什么要做成平台，而不是几个孤立工具</h2>
          </div>
        </div>
        <div class="card-grid">
          <div class="info-card" v-for="item in motivationCards" :key="item.title">
            <h3>{{ item.title }}</h3>
            <p>{{ item.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="section muted">
      <div class="section-inner">
        <div class="section-title-row">
          <div>
            <span class="section-kicker">Challenges</span>
            <h2>核心难点</h2>
          </div>
        </div>
        <div class="challenge-list">
          <div class="challenge-row" v-for="item in challengeCards" :key="item.title">
            <strong>{{ item.title }}</strong>
            <p>{{ item.text }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-inner">
        <div class="section-title-row">
          <div>
            <span class="section-kicker">Pipeline</span>
            <h2>系统主流程</h2>
          </div>
        </div>
        <div class="pipeline">
          <div v-for="(item, index) in pipelineSteps" :key="item.title" class="pipeline-step">
            <div class="step-index">{{ index + 1 }}</div>
            <div class="step-body">
              <strong>{{ item.title }}</strong>
              <p>{{ item.text }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="section muted">
      <div class="section-inner two-column">
        <div>
          <div class="section-title-row compact">
            <div>
              <span class="section-kicker">Basics</span>
              <h2>相关基础知识</h2>
            </div>
          </div>
          <div class="knowledge-list">
            <div v-for="item in basicsCards" :key="item.title" class="knowledge-card">
              <strong>{{ item.title }}</strong>
              <p>{{ item.text }}</p>
            </div>
          </div>
        </div>

        <div>
          <div class="section-title-row compact">
            <div>
              <span class="section-kicker">How To Use</span>
              <h2>进入系统后做什么</h2>
            </div>
          </div>
          <div class="usage-card">
            <div class="usage-row" v-for="(item, index) in usageSteps" :key="item.title">
              <span class="usage-index">{{ index + 1 }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.text }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <AuthModal
      v-if="!isEmbedded"
      :visible="showAuthModal"
      :initialTab="authModalTab"
      @close="showAuthModal = false"
      @success="onAuthSuccess"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthModal from '../components/AuthModal.vue'

const route = useRoute()
const router = useRouter()
const isEmbedded = computed(() => route.path.startsWith('/app'))
const isLoggedIn = ref(!!localStorage.getItem('token'))
const showAuthModal = ref(false)
const authModalTab = ref('login')

const backgroundCards = [
  {
    title: '背景',
    text: '锂硫电池催化材料筛选涉及化学结构、反应中间体、量子求解和部署代价，数据和计算链路长，单点工具无法承载完整研究流程。',
  },
  {
    title: '目标',
    text: '把候选材料输入一直推进到推荐输出，让实验过程可回溯、可复用、可比较，而不是每个阶段各做各的。',
  },
  {
    title: '当前定位',
    text: '现在的原型优先打通分布式量子编译子域，后续再把候选材料、化学建模、评分与展示契约逐步接进来。',
  },
]

const motivationCards = [
  {
    title: '不让前端拼下游服务',
    text: '前端应该只面对统一工作流和结果视图，而不是自己理解化学、量子、编译服务的内部数据结构。',
  },
  {
    title: '不让状态散落在各处',
    text: '一条实验任务要明确知道自己现在在哪个阶段、失败在哪、重试过几次、最终留下了哪些工件。',
  },
  {
    title: '不让结果只停在算法输出',
    text: '最终需要的是可解释的候选材料推荐，而不是只得到一份分区 JSON 或一张映射图。',
  },
]

const challengeCards = [
  {
    title: '多阶段链路长',
    text: '候选筛选、化学建模、量子编码、分布式编译、模拟评估、综合评分彼此依赖，单阶段成功不代表整条链路可用。',
  },
  {
    title: '异步任务多',
    text: '长耗时任务需要异步调度与状态机管理，否则前端会被迫承担任务轮询、失败重试和结果拼装。',
  },
  {
    title: '工件类型复杂',
    text: 'QASM、积分集、Hamiltonian、编译结果、报告文件都属于中间工件，需要统一索引与追踪。',
  },
  {
    title: '推荐结果要可解释',
    text: '最终不能只给一个分数，还需要说清楚为什么推荐某个候选材料、某种部署拓扑和某个结果视图。',
  },
]

const pipelineSteps = [
  { title: '候选材料输入', text: '选择候选材料、活性位模板和实验配置。' },
  { title: '化学建模', text: '构建微模型、电子结构与费米子问题输入。' },
  { title: '量子问题构造', text: '生成哈密顿量、初态、ansatz 和 QASM 工件。' },
  { title: '分布式量子编译', text: '完成量子线路划分、芯片映射与部署代价统计。' },
  { title: '模拟评估与评分', text: '做结果校验、保真度分析和综合推荐评分。' },
  { title: '推荐输出', text: '生成前端可读的统一结果视图和报告。' },
]

const basicsCards = [
  {
    title: '什么是候选材料筛选',
    text: '就是从多个可能的催化材料或活性位方案中，找出既有化学潜力、又适合后续量子求解与部署的组合。',
  },
  {
    title: '什么是分布式量子编译',
    text: '当一条量子线路无法由单个量子芯片承载时，需要把它切分并映射到多个芯片上协同执行。',
  },
  {
    title: '为什么要评分',
    text: '化学性能和部署代价往往互相牵制，平台需要把多个维度统一成最终可比较的推荐结果。',
  },
]

const usageSteps = [
  {
    title: '先进入工作台',
    text: '工作台负责真正的候选材料筛选与实验任务组织，不在首页放业务操作。',
  },
  {
    title: '选择候选材料与实验模板',
    text: '先明确想研究的候选体系，再决定要走完整链路还是先做分布式编译子域验证。',
  },
  {
    title: '进入编译能力页执行当前原型',
    text: '当前能直接跑的是 QASM 上传、分区、映射和结果导出，这部分已经接通。',
  },
]

function openAuth(tab) {
  authModalTab.value = tab
  showAuthModal.value = true
}

function onAuthSuccess() {
  isLoggedIn.value = true
  showAuthModal.value = false
  router.push('/app/workbench')
}

watch(
  () => route.query.auth,
  (value) => {
    if (value === 'login' || value === 'register') {
      openAuth(value)
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.intro-page {
  background: #f6f7fb;
  color: #111827;
}

.intro-page.embedded {
  background: transparent;
}

.public-header {
  position: sticky;
  top: 0;
  z-index: 12;
  background: rgba(246, 247, 251, 0.96);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #e8ebf1;
}

.header-inner,
.section-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 24px;
}

.header-inner {
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2ec5a7, #4e7cff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.brand-copy {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-size: 1rem;
  font-weight: 700;
}

.brand-sub {
  color: #667085;
  font-size: 0.74rem;
}

.header-actions,
.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.primary-btn,
.secondary-btn,
.text-btn {
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1px solid transparent;
  font-size: 0.86rem;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.primary-btn {
  background: linear-gradient(135deg, #2ec5a7, #4e7cff);
  color: #fff;
}

.secondary-btn {
  background: #fff;
  border-color: #d9e3f5;
  color: #2456b8;
}

.text-btn {
  background: transparent;
  color: #475467;
}

.section {
  padding: 28px 0;
}

.section.muted {
  background: #fbfcfe;
  border-top: 1px solid #edf0f5;
  border-bottom: 1px solid #edf0f5;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
  gap: 18px;
}

.hero-main,
.summary-card,
.info-card,
.challenge-row,
.knowledge-card,
.usage-card {
  background: #fff;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
}

.hero-main,
.summary-card {
  padding: 24px;
}

.eyebrow,
.section-kicker {
  color: #0f766e;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.hero-main h1 {
  margin-top: 10px;
  font-size: 2rem;
}

.hero-text {
  margin-top: 16px;
  color: #475467;
  font-size: 0.92rem;
  line-height: 1.8;
}

.hero-actions {
  margin-top: 18px;
}

.summary-label {
  color: #667085;
  font-size: 0.75rem;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.12rem;
}

.summary-card p,
.info-card p,
.challenge-row p,
.knowledge-card p,
.usage-row p,
.step-body p {
  margin-top: 8px;
  color: #475467;
  font-size: 0.84rem;
  line-height: 1.7;
}

.section-title-row {
  margin-bottom: 16px;
}

.section-title-row h2 {
  margin-top: 6px;
  font-size: 1.3rem;
}

.compact {
  margin-bottom: 12px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.info-card {
  padding: 18px;
}

.info-card h3,
.challenge-row strong,
.knowledge-card strong,
.usage-row strong,
.step-body strong {
  font-size: 0.92rem;
  color: #101828;
}

.challenge-list,
.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.challenge-row,
.knowledge-card {
  padding: 18px;
}

.pipeline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.pipeline-step {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background: #fff;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
  padding: 18px;
}

.step-index,
.usage-index {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: #eef6ff;
  color: #2456b8;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78rem;
  font-weight: 700;
  flex-shrink: 0;
}

.two-column {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.usage-card {
  padding: 10px;
}

.usage-row {
  display: flex;
  gap: 12px;
  padding: 14px;
}

.usage-row + .usage-row {
  border-top: 1px solid #edf0f5;
}

@media (max-width: 1080px) {
  .hero-grid,
  .card-grid,
  .pipeline,
  .two-column {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .header-inner,
  .section-inner {
    padding: 0 16px;
  }

  .header-inner {
    height: auto;
    padding-top: 12px;
    padding-bottom: 12px;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .hero-main h1 {
    font-size: 1.7rem;
  }
}
</style>
