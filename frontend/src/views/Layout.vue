<template>
  <div class="platform-shell">
    <aside class="platform-sidebar" :class="{ compact: sidebarCollapsed }">
      <router-link class="platform-brand" to="/">
        <span class="brand-glyph" aria-hidden="true"><i></i><i></i><b></b></span>
        <span v-if="!sidebarCollapsed" class="brand-copy">
          <strong>分子量子分布式计算平台</strong>
          <small>MOLECULAR COMPUTE MESH</small>
        </span>
      </router-link>

      <div v-if="!sidebarCollapsed" class="nav-caption">工作空间</div>
      <nav class="platform-nav" aria-label="主导航">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: isActive(item.path) }">
          <span class="nav-index">{{ item.index }}</span>
          <span v-if="!sidebarCollapsed" class="nav-copy"><strong>{{ item.title }}</strong><small>{{ item.desc }}</small></span>
        </router-link>
      </nav>

      <section v-if="!sidebarCollapsed" class="simulator-note">
        <span class="status-light"></span>
        <div><strong>逻辑执行环境</strong><p>模拟器 · 非真实 QPU</p></div>
      </section>

      <footer class="sidebar-account">
        <span class="account-avatar">{{ identityInitial }}</span>
        <span v-if="!sidebarCollapsed" class="account-copy"><strong>{{ identityLabel }}</strong><small>研究工作区</small></span>
        <button class="sidebar-action" type="button" :aria-label="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="sidebarCollapsed = !sidebarCollapsed">
          <el-icon><component :is="sidebarCollapsed ? 'Expand' : 'Fold'" /></el-icon>
        </button>
        <button v-if="isLoggedIn && !sidebarCollapsed" class="sidebar-action logout" type="button" aria-label="退出登录" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </footer>
    </aside>

    <div class="platform-main">
      <header class="platform-topbar">
        <div><span>{{ route.meta?.eyebrow }}</span><h1>{{ route.meta?.title }}</h1></div>
        <div class="topbar-contract">
          <span>API CONTRACT</span><strong>Workflow v2</strong><i></i>
        </div>
      </header>
      <main class="platform-content"><router-view /></main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SwitchButton } from '@element-plus/icons-vue'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const { isLoggedIn, username, logout } = useAuth()
const identityLabel = computed(() => isLoggedIn.value ? username.value : '访客')
const identityInitial = computed(() => identityLabel.value.charAt(0).toUpperCase())

const navItems = [
  { index: '01', path: '/app/molecules', title: '计算一个分子', desc: '了解固定分子的计算结果' },
  { index: '02', path: '/app/molecule-workflows', title: '查看我的任务', desc: '查看状态、质量与结果' },
  { index: '03', path: '/app/molecular-studies/new', title: '比较计算方案', desc: '比较不同分区和连接方案' },
  { index: '04', path: '/app/molecular-bond-scans/new', title: '观察键长趋势', desc: 'LiH 距离变化与能量趋势' },
  { index: '05', path: '/app/simulation-capabilities', title: '了解计算边界', desc: '模拟能力与执行语义' },
  { index: '06', path: '/app/copilot', title: '让 Copilot 帮我选', desc: '用日常语言生成受控草稿' },
]

function isActive(path) {
  if (path === '/app/molecule-workflows') return route.path.startsWith('/app/molecule-workflows')
  if (path === '/app/molecular-studies/new') return route.path.startsWith('/app/molecular-studies')
  if (path === '/app/molecular-bond-scans/new') return route.path.startsWith('/app/molecular-bond-scans')
  return route.path === path
}

function handleLogout() {
  logout()
  router.push('/')
}
</script>

<style scoped>
.platform-shell { min-height: 100vh; display: flex; background: #f2f3ef; color: #17201d; }
.platform-sidebar { width: 286px; min-width: 286px; min-height: 100vh; padding: 26px 18px 18px; display: flex; flex-direction: column; background: #101815; color: #eef2ed; transition: width .2s, min-width .2s; }
.platform-sidebar.compact { width: 82px; min-width: 82px; }
.platform-brand { min-height: 58px; padding: 0 7px; display: flex; align-items: center; gap: 13px; color: inherit; text-decoration: none; }
.brand-glyph { width: 42px; height: 42px; position: relative; flex: 0 0 42px; border: 1px solid #89a69a; border-radius: 50%; }
.brand-glyph i { position: absolute; inset: 10px 5px; border: 1px solid #b5f04c; border-radius: 50%; transform: rotate(35deg); }
.brand-glyph i:nth-child(2) { transform: rotate(-35deg); }
.brand-glyph b { position: absolute; left: 17px; top: 17px; width: 7px; height: 7px; border-radius: 50%; background: #b5f04c; }
.brand-copy { min-width: 0; display: grid; gap: 4px; }
.brand-copy strong { max-width: 184px; font-size: .92rem; line-height: 1.35; }
.brand-copy small, .account-copy small { color: #839188; font-size: .62rem; letter-spacing: .11em; }
.nav-caption { margin: 52px 10px 14px; color: #66736b; font-size: .68rem; letter-spacing: .16em; }
.platform-nav { display: grid; gap: 5px; }
.platform-nav a { min-height: 66px; padding: 10px 12px; border: 1px solid transparent; display: flex; align-items: center; gap: 14px; color: #a9b3ad; text-decoration: none; transition: .18s ease; }
.platform-nav a:hover { color: #fff; border-color: #2b3933; }
.platform-nav a.active { color: #fff; border-color: #3c4e46; background: #1a2521; }
.nav-index { width: 30px; color: #b5f04c; font: 600 .68rem ui-monospace, monospace; }
.nav-copy { min-width: 0; display: grid; gap: 5px; }
.nav-copy strong { font-size: .88rem; }
.nav-copy small { color: #738078; font-size: .71rem; }
.simulator-note { margin-top: auto; padding: 17px 14px; border: 1px solid #34423c; display: flex; gap: 11px; align-items: flex-start; }
.status-light { width: 8px; height: 8px; margin-top: 4px; border-radius: 50%; background: #b5f04c; box-shadow: 0 0 0 4px rgba(181,240,76,.09); }
.simulator-note strong { font-size: .75rem; }
.simulator-note p { margin: 6px 0 0; color: #8d9992; font-size: .7rem; }
.sidebar-account { margin-top: 18px; padding-top: 18px; border-top: 1px solid #29352f; display: flex; align-items: center; gap: 9px; }
.account-avatar { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; background: #dce9df; color: #18221e; font-weight: 800; font-size: .78rem; }
.account-copy { min-width: 0; flex: 1; display: grid; gap: 3px; }
.account-copy strong { overflow: hidden; font-size: .78rem; text-overflow: ellipsis; }
.sidebar-action { width: 34px; height: 34px; border: 1px solid #34423c; display: grid; place-items: center; background: transparent; color: #9ca8a1; cursor: pointer; }
.sidebar-action.logout { color: #ee9f8a; }
.platform-main { min-width: 0; flex: 1; }
.platform-topbar { min-height: 92px; padding: 18px clamp(22px, 4vw, 54px); border-bottom: 1px solid #d7dbd4; display: flex; align-items: center; justify-content: space-between; background: rgba(247,248,244,.88); backdrop-filter: blur(14px); }
.platform-topbar span { color: #758079; font-size: .66rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.platform-topbar h1 { margin: 5px 0 0; font-size: 1.28rem; letter-spacing: -.02em; }
.topbar-contract { display: grid; grid-template-columns: auto auto 8px; gap: 9px; align-items: center; }
.topbar-contract strong { font: 700 .72rem ui-monospace, monospace; }
.topbar-contract i { width: 8px; height: 8px; border-radius: 50%; background: #6ca52e; }
.platform-content { padding: 36px clamp(22px, 4vw, 54px) 70px; }
@media (max-width: 760px) { .platform-sidebar { width: 82px; min-width: 82px; } .brand-copy, .nav-caption, .nav-copy, .simulator-note, .account-copy, .logout { display: none; } .platform-topbar { min-height: 76px; } .topbar-contract { display: none; } .platform-content { padding: 24px 18px 50px; } }
</style>
