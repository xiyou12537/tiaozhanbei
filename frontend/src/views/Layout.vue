<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <router-link to="/" class="brand">
        <span class="brand-mark" aria-hidden="true">
          <span class="orbit-ring ring-a"></span>
          <span class="orbit-ring ring-b"></span>
          <span class="orbit-core"></span>
          <span class="orbit-node node-a"></span>
          <span class="orbit-node node-b"></span>
          <span class="orbit-node node-c"></span>
        </span>
        <span v-if="!sidebarCollapsed" class="brand-copy">
          <strong>&#x91CF;&#x667A;&#x786B;&#x5149;</strong>
          <small>Li-S Quantum Lab</small>
        </span>
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
            <strong v-html="item.title"></strong>
            <small v-html="item.desc"></small>
          </span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div v-if="!sidebarCollapsed" class="user-block">
          <span class="avatar">{{ identityInitial }}</span>
          <span class="user-meta">
            <strong>{{ identityLabel }}</strong>
            <small v-html="identityRoleHtml"></small>
          </span>
        </div>
        <button class="icon-btn" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
          <el-icon :size="16"><component :is="sidebarCollapsed ? 'Expand' : 'Fold'" /></el-icon>
        </button>
        <router-link v-if="!isLoggedIn" class="icon-btn" to="/auth?tab=login">
          <el-icon :size="16"><User /></el-icon>
        </router-link>
        <button v-else class="icon-btn danger" type="button" @click="handleLogout">
          <el-icon :size="16"><SwitchButton /></el-icon>
        </button>
      </div>
    </aside>

    <div class="main-area">
      <header class="top-bar">
        <div class="page-copy">
          <span class="page-kicker">Research Console</span>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div v-if="showTopWorkflowContext" class="top-right">
          <div class="status-pill">
            <span class="status-dot" :class="topWorkflowStatus"></span>
            <span v-html="workflowLabelHtml"></span>
          </div>
          <div v-if="topWorkflowId" class="task-pill">
            <span>{{ topIdLabel }}</span>
            <strong>{{ topWorkflowId.slice(0, 8) }}</strong>
          </div>
        </div>
      </header>

      <main class="page-content">
        <router-view />
      </main>

      <ChatWidget v-if="showFloatingChat" />
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SwitchButton, User } from '@element-plus/icons-vue'
import { useAuth } from '../composables/useAuth'
import { useScreeningWorkflow } from '../composables/useScreeningWorkflow'
import { useStructureWorkflow } from '../composables/use-structure-workflow'
import { useWorkflow } from '../composables/useWorkflow'
import ChatWidget from '../components/ChatWidget.vue'

const router = useRouter()
const route = useRoute()
const sidebarCollapsed = ref(false)
const { isLoggedIn, username, logout } = useAuth()
const { workflowState: shared, clearPolling } = useWorkflow()
const { screeningState } = useScreeningWorkflow()
const { structureState } = useStructureWorkflow()

provide('shared', shared)

const pageTitle = computed(() => route.meta?.title || 'Console')
const identityLabel = computed(() => (isLoggedIn.value ? username.value : 'Guest'))
const identityInitial = computed(() => identityLabel.value.charAt(0).toUpperCase())
const identityRoleHtml = computed(() =>
  isLoggedIn.value ? '&#x7814;&#x7A76;&#x7528;&#x6237;' : '&#x672A;&#x767B;&#x5F55;'
)
const isScreeningRoute = computed(() => ['/app/screening', '/app/results'].includes(route.path))
const isStructureRoute = computed(() =>
  route.path === '/app/structure-workbench' || route.path.startsWith('/app/structure-workflows/')
)
const showTopWorkflowContext = computed(() => !(
  route.path === '/app/structure-workbench'
  || route.path.startsWith('/app/research-benchmarks')
  || route.path.startsWith('/app/structure-workflows/')
))
const showFloatingChat = computed(() => !['/app/screening', '/app/results', '/app/structure-workbench', '/app/workbench', '/app/knowledge'].includes(route.path))

const workflowLabelMap = {
  idle: '&#x5F85;&#x542F;&#x52A8;',
  created: '&#x5DF2;&#x521B;&#x5EFA;',
  validated: '&#x5DF2;&#x6821;&#x9A8C;',
  screening: '&#x5019;&#x9009;&#x7B5B;&#x9009;',
  chem_modeling: '&#x5316;&#x5B66;&#x5EFA;&#x6A21;',
  quantum_encoding: '&#x91CF;&#x5B50;&#x7F16;&#x7801;',
  distributed_compiling: '&#x5206;&#x5E03;&#x5F0F;&#x7F16;&#x8BD1;',
  simulation_evaluating: '&#x4EFF;&#x771F;&#x8BC4;&#x4F30;',
  scoring: '&#x7EFC;&#x5408;&#x8BC4;&#x5206;',
  aggregating: '&#x7ED3;&#x679C;&#x805A;&#x5408;',
  running: '&#x8FD0;&#x884C;&#x4E2D;',
  partial_completed: '&#x90E8;&#x5206;&#x5B8C;&#x6210;',
  completed: '&#x5DF2;&#x5B8C;&#x6210;',
  cancelled: '&#x5DF2;&#x53D6;&#x6D88;',
  failed: '&#x5931;&#x8D25;',
  active_site_pending: '&#x5F85;&#x786E;&#x8BA4;&#x6D3B;&#x6027;&#x4F4D;&#x70B9;',
  active_site_confirmed: '&#x6D3B;&#x6027;&#x4F4D;&#x70B9;&#x5DF2;&#x786E;&#x8BA4;',
  adsorption_models_generated: '&#x521D;&#x59CB;&#x6784;&#x578B;&#x5DF2;&#x751F;&#x6210;',
  geometry_optimized: '&#x51E0;&#x4F55;&#x5DF2;&#x51C6;&#x5907;',
  literature_reproduction_input_selected: '&#x5DF2;&#x9009;&#x5B9A;&#x6587;&#x732E;&#x590D;&#x73B0;&#x8F93;&#x5165;',
  literature_reproduction_geometry_ready: '&#x6587;&#x732E;&#x4F18;&#x5316;&#x51E0;&#x4F55;&#x5DF2;&#x5C31;&#x7EEA;',
  quantum_region_built: '&#x91CF;&#x5B50;&#x533A;&#x5DF2;&#x5EFA;&#x7ACB;',
  electronic_structure_confirmed: '&#x7535;&#x5B50;&#x7ED3;&#x6784;&#x5DF2;&#x786E;&#x8BA4;',
  active_space_confirmed: '&#x6D3B;&#x6027;&#x7A7A;&#x95F4;&#x5DF2;&#x786E;&#x8BA4;',
  needs_model_review: '&#x9700;&#x8981;&#x8865;&#x5145;&#x79D1;&#x7814;&#x5EFA;&#x6A21;&#x4FE1;&#x606F;',
  validation_failed: '&#x7ED3;&#x6784;&#x6821;&#x9A8C;&#x5931;&#x8D25;',
}

const topWorkflowStatus = computed(() => {
  if (isScreeningRoute.value) return screeningState.workflowStatus
  if (isStructureRoute.value) return structureState.workflowStatus
  return shared.workflowStatus
})
const topWorkflowId = computed(() => {
  if (isScreeningRoute.value) return screeningState.screeningWorkflowId
  if (isStructureRoute.value) return structureState.workflowId
  return shared.taskId
})
const topIdLabel = computed(() => (isScreeningRoute.value || isStructureRoute.value ? 'Workflow' : 'Task'))
const workflowLabelHtml = computed(() => workflowLabelMap[topWorkflowStatus.value] || workflowLabelMap.idle)

const navItems = [
  {
    path: '/app/screening',
    title: '&#x7B5B;&#x9009;&#x5DE5;&#x4F5C;&#x53F0;',
    desc: '&#x591A;&#x6750;&#x6599;&#x3001;&#x7C97;&#x7B5B;&#x3001;&#x6392;&#x884C;',
    icon: 'DataBoard',
  },
  {
    path: '/app/structure-workbench',
    title: '&#x5316;&#x5B66;&#x7B5B;&#x9009;&#x4E0E;&#x8BA1;&#x7B97;',
    desc: '&#x7ED3;&#x6784;&#x3001;&#x91CF;&#x5B50;&#x7EBF;&#x8DEF;&#x3001;&#x82AF;&#x7247;&#x6267;&#x884C;',
    icon: 'Connection',
  },
  {
    path: '/app/research-benchmarks',
    title: '&#x516C;&#x5F00;&#x7ED3;&#x6784;&#x6848;&#x4F8B;',
    desc: '&#x4ECE;&#x516C;&#x5F00;&#x6570;&#x636E;&#x9009;&#x62E9;&#x8F93;&#x5165;',
    icon: 'CollectionTag',
  },
  {
    path: '/app/results',
    title: '&#x7ED3;&#x679C;',
    desc: '&#x8BC4;&#x5206;&#x3001;&#x6307;&#x6807;&#x3001;&#x5DE5;&#x4EF6;',
    icon: 'DataAnalysis',
  },
  {
    path: '/app/knowledge',
    title: '&#x77E5;&#x8BC6;&#x5E93;',
    desc: '&#x6587;&#x6863;&#x3001;&#x5F15;&#x7528;&#x3001;&#x95EE;&#x7B54;',
    icon: 'Collection',
  },
  {
    path: '/app/history',
    title: '&#x5386;&#x53F2;',
    desc: '&#x5F52;&#x6863;&#x4E0E;&#x56DE;&#x770B;',
    icon: 'Clock',
  },
]

function isActive(path) {
  return route.path === path
}

function handleLogout() {
  logout()
  router.push('/')
}

onUnmounted(() => {
  clearPolling()
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  background:
    radial-gradient(circle at 18% 4%, rgba(107, 216, 255, 0.1), transparent 30%),
    linear-gradient(180deg, #020912 0%, #061523 100%);
}

.sidebar {
  width: 292px;
  min-width: 292px;
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  border-right: 1px solid var(--lz-line);
  background:
    linear-gradient(180deg, rgba(9, 22, 36, 0.9), rgba(5, 13, 23, 0.96)),
    radial-gradient(circle at top, rgba(52, 211, 194, 0.14), transparent 36%);
  transition: width 0.2s ease, min-width 0.2s ease;
}

.sidebar.collapsed {
  width: 84px;
  min-width: 84px;
}

.brand,
.nav-item {
  color: var(--lz-text);
  text-decoration: none;
}

.brand {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 46px;
  height: 46px;
  position: relative;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 48% 52%, rgba(52, 214, 255, 0.26), transparent 36%),
    radial-gradient(circle at 28% 22%, rgba(242, 195, 91, 0.24), transparent 26%),
    rgba(4, 10, 20, 0.82);
  box-shadow:
    0 0 0 1px rgba(120, 200, 255, 0.18),
    0 0 26px rgba(30, 140, 255, 0.26),
    inset 0 0 18px rgba(52, 214, 255, 0.18);
}

.orbit-ring,
.orbit-core,
.orbit-node {
  position: absolute;
  display: block;
}

.orbit-ring {
  inset: 8px;
  border: 1px solid rgba(52, 214, 255, 0.42);
  border-radius: 50%;
}

.ring-a {
  transform: rotate(-18deg) scaleX(0.72);
}

.ring-b {
  border-color: rgba(242, 195, 91, 0.46);
  transform: rotate(34deg) scaleX(0.66);
}

.orbit-core {
  left: 50%;
  top: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--lz-cyan);
  box-shadow: 0 0 14px rgba(52, 214, 255, 0.9);
  transform: translate(-50%, -50%);
}

.orbit-node {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: linear-gradient(135deg, #fff4b8, var(--lz-gold) 58%, #7a4a10);
  box-shadow: 0 0 12px rgba(242, 195, 91, 0.76);
}

.node-a {
  left: 13px;
  top: 11px;
}

.node-b {
  right: 10px;
  top: 18px;
}

.node-c {
  left: 18px;
  bottom: 10px;
}

.brand-copy,
.nav-body,
.user-meta {
  min-width: 0;
  display: grid;
}

.brand-copy strong {
  font-family: var(--lz-display);
  font-size: 1.05rem;
}

.brand-copy small,
.nav-body small,
.user-meta small {
  color: var(--lz-muted);
  font-size: 0.72rem;
}

.nav-group {
  display: grid;
  gap: 8px;
}

.nav-item {
  min-height: 64px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: var(--lz-radius);
  display: flex;
  align-items: center;
  gap: 12px;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.nav-item:hover {
  border-color: var(--lz-line);
  background: rgba(255, 255, 255, 0.045);
  transform: translateY(-1px);
}

.nav-item.active {
  border-color: var(--lz-line-strong);
  background:
    linear-gradient(135deg, rgba(52, 211, 194, 0.14), rgba(22, 119, 255, 0.1)),
    rgba(255, 255, 255, 0.04);
}

.nav-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--lz-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
  color: var(--lz-cyan);
}

.nav-body strong {
  color: var(--lz-text);
  font-size: 0.92rem;
}

.sidebar-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-block {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: var(--lz-radius);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(107, 216, 255, 0.12);
  color: var(--lz-cyan);
  font-weight: 800;
}

.user-meta strong {
  color: var(--lz-text);
  font-size: 0.86rem;
}

.icon-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--lz-radius);
  border: 1px solid var(--lz-line);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.04);
  color: var(--lz-text);
  cursor: pointer;
  text-decoration: none;
}

.icon-btn.danger {
  color: #ffb4a7;
}

.main-area {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.top-bar {
  min-height: 84px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--lz-line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  background: rgba(3, 10, 18, 0.72);
  backdrop-filter: blur(18px);
}

.page-kicker {
  color: var(--lz-cyan);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-copy h1 {
  margin: 5px 0 0;
  color: var(--lz-text);
  font-family: var(--lz-display);
  font-size: 1.34rem;
  letter-spacing: 0;
}

.top-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.status-pill,
.task-pill {
  min-height: 38px;
  padding: 0 13px;
  border: 1px solid var(--lz-line);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(235, 244, 255, 0.84);
  font-size: 0.8rem;
  font-weight: 700;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #9aa8ba;
}

.status-dot.completed,
.status-dot.partial_completed {
  background: #27d17f;
}

.status-dot.failed {
  background: #ff705f;
}

.status-dot.validation_failed {
  background: #ff705f;
}

.status-dot.needs_model_review,
.status-dot.partial_result {
  background: #f6b84a;
}

.status-dot.running,
.status-dot.created,
.status-dot.screening,
.status-dot.chem_modeling,
.status-dot.quantum_encoding,
.status-dot.distributed_compiling,
.status-dot.simulation_evaluating,
.status-dot.scoring,
.status-dot.aggregating {
  background: var(--lz-gold);
}

.status-dot.active_site_pending,
.status-dot.active_site_confirmed,
.status-dot.adsorption_models_generated,
.status-dot.geometry_optimized,
.status-dot.quantum_region_built,
.status-dot.electronic_structure_confirmed,
.status-dot.active_space_confirmed {
  background: var(--lz-gold);
}

.page-content {
  flex: 1;
  padding: 24px;
}

@media (max-width: 1100px) {
  .sidebar {
    width: 84px;
    min-width: 84px;
  }

  .brand-copy,
  .nav-body,
  .user-block {
    display: none;
  }
}

@media (max-width: 720px) {
  .app-shell {
    display: block;
  }

  .sidebar {
    width: 100%;
    min-width: 0;
    flex-direction: row;
    align-items: center;
    overflow-x: auto;
  }

  .nav-group {
    display: flex;
  }

  .sidebar-footer {
    margin-top: 0;
    margin-left: auto;
  }

  .top-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .top-bar,
  .page-content {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
