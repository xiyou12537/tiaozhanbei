<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <router-link to="/" class="brand">
        <div class="brand-mark">LZ</div>
        <div v-if="!sidebarCollapsed" class="brand-copy">
          <span class="brand-name">量智硫光</span>
          <span class="brand-sub">Lithium Sulfur Quantum Platform</span>
        </div>
      </router-link>

      <nav class="nav-group">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <span class="nav-icon">
            <el-icon :size="18"><component :is="item.icon" /></el-icon>
          </span>
          <span v-if="!sidebarCollapsed" class="nav-body">
            <span class="nav-title">{{ item.title }}</span>
            <span class="nav-desc">{{ item.desc }}</span>
          </span>
        </router-link>
      </nav>

      <div v-if="!sidebarCollapsed" class="coverage-card">
        <span class="coverage-label">当前接通能力</span>
        <strong>分布式编译子域</strong>
        <p>认证、QASM 上传、分区、映射、历史、导出、AI 会话</p>
      </div>

      <div class="sidebar-footer">
        <div v-if="!sidebarCollapsed" class="user-block">
          <div class="avatar">{{ username.charAt(0).toUpperCase() }}</div>
          <div class="user-meta">
            <span class="user-name">{{ username }}</span>
            <span class="user-role">平台研究用户</span>
          </div>
        </div>
        <button class="icon-btn" @click="sidebarCollapsed = !sidebarCollapsed">
          <el-icon :size="16"><component :is="sidebarCollapsed ? 'Expand' : 'Fold'" /></el-icon>
        </button>
        <button class="icon-btn danger" @click="handleLogout">
          <el-icon :size="16"><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <div class="main-area">
      <header class="top-bar">
        <div class="top-left">
          <div class="page-copy">
            <span class="page-kicker">统一编排视图</span>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>
        <div class="top-right">
          <div class="status-pill">
            <span class="status-dot" :class="shared.workflowStatus"></span>
            <span>{{ workflowLabel }}</span>
          </div>
          <div v-if="shared.taskId" class="task-pill">
            <span>Task</span>
            <strong>{{ shared.taskId.slice(0, 8) }}</strong>
          </div>
        </div>
      </header>

      <main class="page-content">
        <router-view />
      </main>

      <ChatWidget />
    </div>
  </div>
</template>

<script setup>
import { computed, provide, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChatWidget from '../components/ChatWidget.vue'

const router = useRouter()
const route = useRoute()
const sidebarCollapsed = ref(false)

function createStageRuns() {
  return {
    created: 'pending',
    validated: 'pending',
    screening: 'planned',
    chem_modeling: 'planned',
    quantum_encoding: 'planned',
    distributed_compiling: 'pending',
    simulation_evaluating: 'planned',
    scoring: 'planned',
    aggregating: 'pending',
    completed: 'pending',
  }
}

const shared = reactive({
  circuit: null,
  taskId: null,
  partitionResult: null,
  edgeCosts: null,
  targetEdges: [],
  mapping: null,
  topoComparisons: null,
  workflowStatus: 'idle',
  currentStage: 'created',
  stageRuns: createStageRuns(),
  stageNotes: [],
  lastError: '',
})

provide('shared', shared)

const user = JSON.parse(localStorage.getItem('user') || '{}')
const username = computed(() => user.username || '用户')
const pageTitle = computed(() => route.meta?.title || '平台')

const workflowLabel = computed(() => {
  const labelMap = {
    idle: '等待创建实验',
    created: '任务已创建',
    validated: '输入已校验',
    running: '分布式编译运行中',
    partial_completed: '子域结果已生成',
    completed: '当前链路已完成',
    failed: '任务失败',
  }
  return labelMap[shared.workflowStatus] || '等待创建实验'
})

const navItems = [
  { path: '/app/workbench', title: '实验工作台', desc: '统一状态与结果视图', icon: 'DataBoard' },
  { path: '/app/capability', title: '编译能力页', desc: 'QASM 上传、分区、映射', icon: 'Cpu' },
  { path: '/app/overview', title: '项目介绍', desc: '背景、动机、难点与基础知识', icon: 'Reading' },
  { path: '/app/preview', title: '系统蓝图', desc: '最终产品形态预览', icon: 'Monitor' },
  { path: '/app/history', title: '历史记录', desc: '历史任务与结果回看', icon: 'Clock' },
  { path: '/app/chat', title: 'AI 助手', desc: '问答与会话辅助', icon: 'ChatDotRound' },
]

function isActive(path) {
  return route.path === path
}

function handleLogout() {
  localStorage.clear()
  router.push('/')
}
</script>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: #f6f7fb;
}

.sidebar {
  width: 280px;
  min-width: 280px;
  background: #ffffff;
  border-right: 1px solid #e6e9f0;
  padding: 18px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: width 0.2s ease, min-width 0.2s ease;
}

.sidebar.collapsed {
  width: 84px;
  min-width: 84px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
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
  font-size: 0.92rem;
  font-weight: 700;
  flex-shrink: 0;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  color: #152033;
  font-size: 1rem;
  font-weight: 700;
}

.brand-sub {
  color: #7d8799;
  font-size: 0.68rem;
  line-height: 1.4;
}

.nav-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  text-decoration: none;
  color: #556070;
  border: 1px solid transparent;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.nav-item:hover {
  background: #f7fbff;
  border-color: #dce8ff;
  color: #152033;
}

.nav-item.active {
  background: #eef6ff;
  border-color: #cfe0ff;
  color: #153a77;
}

.sidebar.collapsed .nav-item {
  justify-content: center;
}

.nav-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #f2f4f8;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.nav-title {
  font-size: 0.88rem;
  font-weight: 600;
}

.nav-desc {
  color: #7d8799;
  font-size: 0.72rem;
  line-height: 1.4;
}

.coverage-card {
  margin-top: auto;
  background: linear-gradient(180deg, #f4fbf9, #f7f8ff);
  border: 1px solid #dcebe6;
  border-radius: 12px;
  padding: 14px;
  color: #334155;
}

.coverage-card strong {
  display: block;
  margin: 4px 0 6px;
  color: #16324f;
  font-size: 0.92rem;
}

.coverage-card p {
  font-size: 0.75rem;
  line-height: 1.6;
  color: #667085;
}

.coverage-label {
  display: inline-flex;
  font-size: 0.7rem;
  color: #0f766e;
  font-weight: 600;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}

.user-block {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #e8f3ff;
  color: #2456b8;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  color: #1f2937;
  font-size: 0.85rem;
  font-weight: 600;
}

.user-role {
  color: #7d8799;
  font-size: 0.7rem;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: 1px solid #dbe2ee;
  border-radius: 10px;
  background: #fff;
  color: #556070;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn.danger:hover {
  color: #b42318;
  border-color: #f0c7c2;
  background: #fff6f5;
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.top-bar {
  height: 72px;
  min-height: 72px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #e6e9f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 8;
}

.page-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.page-copy h1 {
  font-size: 1.1rem;
  color: #111827;
  line-height: 1.2;
}

.page-kicker {
  color: #6b7280;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-pill,
.task-pill {
  height: 36px;
  border-radius: 999px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
  color: #475467;
  font-size: 0.78rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #98a2b3;
}

.status-dot.running {
  background: #f59e0b;
}

.status-dot.completed,
.status-dot.partial_completed {
  background: #12b76a;
}

.status-dot.failed {
  background: #f04438;
}

.status-dot.validated,
.status-dot.created {
  background: #4e7cff;
}

.task-pill strong {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.78rem;
}

.page-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

@media (max-width: 1100px) {
  .sidebar {
    width: 92px;
    min-width: 92px;
  }

  .brand-copy,
  .nav-body,
  .coverage-card,
  .user-block {
    display: none;
  }

  .nav-item {
    justify-content: center;
  }
}

@media (max-width: 720px) {
  .top-bar {
    height: auto;
    padding: 14px 16px;
    align-items: flex-start;
    gap: 12px;
    flex-direction: column;
  }

  .page-content {
    padding: 16px;
  }
}
</style>
