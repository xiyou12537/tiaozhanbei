<template>
  <div class="platform-shell">
    <aside class="platform-sidebar" :class="{ compact: sidebarCollapsed }">
      <router-link class="platform-brand" to="/app">
        <span class="brand-glyph" aria-hidden="true"><i></i><i></i><b></b></span>
        <span v-if="!sidebarCollapsed" class="brand-copy">
          <strong>分子计算工作台</strong>
          <small>MOLECULAR COMPUTE</small>
        </span>
      </router-link>

      <div v-if="!sidebarCollapsed" class="nav-caption">工作空间</div>
      <nav class="platform-nav" aria-label="主导航">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path" :aria-label="item.title" :class="{ active: isActive(item.path) }">
          <span class="nav-index">{{ item.index }}</span>
          <span v-if="!sidebarCollapsed" class="nav-copy"><strong>{{ item.title }}</strong></span>
        </router-link>
      </nav>

      <section v-if="!sidebarCollapsed" class="simulator-note">
        <span class="status-light"></span>
        <div><strong>逻辑执行环境</strong><p>logical_virtual_qpu 模拟</p></div>
      </section>

      <footer class="sidebar-account">
        <span class="account-avatar">{{ identityInitial }}</span>
        <span v-if="!sidebarCollapsed" class="account-copy"><strong>{{ identityLabel }}</strong><small>研究工作区</small></span>
        <button ref="navigationToggle" class="sidebar-action" type="button" :aria-label="navigationControlLabel" :aria-expanded="navigationExpanded" @click="toggleNavigation">
          <el-icon><component :is="navigationControlIcon" /></el-icon>
        </button>
        <button v-if="isLoggedIn && !sidebarCollapsed" class="sidebar-action logout" type="button" aria-label="退出登录" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
        </button>
      </footer>
    </aside>

    <div v-if="mobileMenuOpen" class="mobile-nav-scrim" aria-hidden="true" @click="closeMobileMenu"></div>
    <aside v-if="mobileMenuOpen" class="mobile-nav-drawer" role="dialog" aria-modal="true" aria-labelledby="mobile-nav-title" @keydown.esc="closeMobileMenu">
      <header class="mobile-nav-head">
        <div><span>WORKSPACE</span><strong id="mobile-nav-title">导航菜单</strong></div>
        <button ref="mobileDrawerClose" class="mobile-drawer-close" type="button" aria-label="关闭导航菜单" @click="closeMobileMenu">
          <el-icon><Close /></el-icon>
        </button>
      </header>
      <nav class="mobile-drawer-links" aria-label="移动端主导航">
        <router-link v-for="item in navItems" :key="item.path" :to="item.path" :aria-label="item.title" :aria-current="isActive(item.path) ? 'page' : null" :class="{ active: isActive(item.path) }" @click="closeMobileMenu">
          <span>{{ item.index }}</span><strong>{{ item.title }}</strong>
        </router-link>
      </nav>
      <footer class="mobile-drawer-account">
        <div><span class="account-avatar">{{ identityInitial }}</span><span><strong>{{ identityLabel }}</strong><small>研究工作区</small></span></div>
        <button v-if="isLoggedIn" type="button" @click="handleLogout"><el-icon><SwitchButton /></el-icon>退出登录</button>
      </footer>
    </aside>

    <div class="platform-main">
      <header class="platform-topbar">
        <div><span>工作台 / {{ route.meta?.eyebrow }}</span><h1>{{ route.meta?.title }}</h1></div>
        <div class="topbar-contract">
          <span>SIMULATION</span><strong>逻辑模拟</strong><i></i>
        </div>
      </header>
      <main class="platform-content"><router-view /></main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SwitchButton } from '@element-plus/icons-vue'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const isMobile = ref(false)
const mobileMenuOpen = ref(false)
const mobileDrawerClose = ref(null)
const navigationToggle = ref(null)
let previousBodyOverflow = ''
const { isLoggedIn, username, logout } = useAuth()
const identityLabel = computed(() => isLoggedIn.value ? username.value : '访客')
const identityInitial = computed(() => identityLabel.value.charAt(0).toUpperCase())
const navigationControlLabel = computed(() => isMobile.value
  ? (mobileMenuOpen.value ? '关闭导航菜单' : '打开导航菜单')
  : (sidebarCollapsed.value ? '展开侧栏' : '收起侧栏'))
const navigationExpanded = computed(() => String(isMobile.value ? mobileMenuOpen.value : !sidebarCollapsed.value))
const navigationControlIcon = computed(() => isMobile.value
  ? (mobileMenuOpen.value ? 'Close' : 'Menu')
  : (sidebarCollapsed.value ? 'Expand' : 'Fold'))

const navItems = [
  { index: '01', path: '/app', title: '工作台' },
  { index: '02', path: '/app/molecules', title: '新建分子计算' },
  { index: '03', path: '/app/molecule-workflows', title: '计算任务' },
  { index: '04', path: '/app/molecular-studies/new', title: '方案比较' },
  { index: '05', path: '/app/molecular-bond-scans/new', title: '键长扫描' },
  { index: '06', path: '/app/copilot', title: 'Molecular Copilot' },
  { index: '07', path: '/app/simulation-capabilities', title: '计算边界' },
]

function isActive(path) {
  if (path === '/app') return route.path === '/app'
  if (path === '/app/molecule-workflows') return route.path.startsWith('/app/molecule-workflows')
  if (path === '/app/molecular-studies/new') return route.path.startsWith('/app/molecular-studies')
  if (path === '/app/molecular-bond-scans/new') return route.path.startsWith('/app/molecular-bond-scans')
  return route.path === path
}

function updateViewportMode() {
  isMobile.value = globalThis.matchMedia?.('(max-width: 760px)').matches ?? false
  if (!isMobile.value) mobileMenuOpen.value = false
}

function toggleNavigation() {
  if (isMobile.value) {
    mobileMenuOpen.value = !mobileMenuOpen.value
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function closeMobileMenu() {
  mobileMenuOpen.value = false
}

function handleLogout() {
  closeMobileMenu()
  logout()
  router.push('/')
}

watch(mobileMenuOpen, async open => {
  if (open) {
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    mobileDrawerClose.value?.focus()
    return
  }
  document.body.style.overflow = previousBodyOverflow
  await nextTick()
  navigationToggle.value?.focus()
})

onMounted(() => {
  updateViewportMode()
  globalThis.addEventListener('resize', updateViewportMode)
})

onBeforeUnmount(() => {
  globalThis.removeEventListener('resize', updateViewportMode)
  document.body.style.overflow = previousBodyOverflow
})
</script>

<style scoped>
.platform-shell { min-height: 100vh; display: flex; background: var(--lz-bg); color: var(--lz-text); }
.platform-sidebar { width: 250px; min-width: 250px; min-height: 100vh; padding: 22px 14px 16px; display: flex; flex-direction: column; background: #15201b; color: #eef2ed; transition: width .2s, min-width .2s; }
.platform-sidebar.compact { width: 82px; min-width: 82px; }
.platform-brand { min-height: 54px; padding: 0 7px; display: flex; align-items: center; gap: 12px; color: inherit; text-decoration: none; }
.brand-glyph { width: 42px; height: 42px; position: relative; flex: 0 0 42px; border: 1px solid #89a69a; border-radius: 50%; }
.brand-glyph i { position: absolute; inset: 10px 5px; border: 1px solid #b5f04c; border-radius: 50%; transform: rotate(35deg); }
.brand-glyph i:nth-child(2) { transform: rotate(-35deg); }
.brand-glyph b { position: absolute; left: 17px; top: 17px; width: 7px; height: 7px; border-radius: 50%; background: #b5f04c; }
.brand-copy { min-width: 0; display: grid; gap: 4px; }
.brand-copy strong { max-width: 174px; font-size: .9rem; line-height: 1.35; }
.brand-copy small, .account-copy small { color: #839188; font-size: .62rem; letter-spacing: .11em; }
.nav-caption { margin: 38px 10px 11px; color: #718078; font-size: .64rem; letter-spacing: .16em; }
.platform-nav { display: grid; gap: 3px; }
.platform-nav a { min-height: 46px; padding: 9px 12px; border: 1px solid transparent; display: flex; align-items: center; gap: 12px; color: #b2bbb5; text-decoration: none; transition: .18s ease; }
.platform-nav a:hover { color: #fff; border-color: #2b3933; }
.platform-nav a.active { color: #fff; border-color: #3c4e46; background: #1a2521; }
.nav-index { width: 30px; color: #b5f04c; font: 600 .68rem ui-monospace, monospace; }
.nav-copy { min-width: 0; display: grid; }
.nav-copy strong { font-size: .88rem; }
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
.platform-topbar { min-height: 78px; padding: 15px clamp(22px, 4vw, 54px); border-bottom: 1px solid var(--lz-line); display: flex; align-items: center; justify-content: space-between; background: rgba(250,250,247,.92); backdrop-filter: blur(14px); }
.platform-topbar span { color: #758079; font-size: .66rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.platform-topbar h1 { margin: 4px 0 0; font-size: 1.12rem; letter-spacing: -.02em; }
.topbar-contract { display: grid; grid-template-columns: auto auto 8px; gap: 9px; align-items: center; }
.topbar-contract strong { font: 700 .72rem ui-monospace, monospace; }
.topbar-contract i { width: 8px; height: 8px; border-radius: 50%; background: #6ca52e; }
.platform-content { min-width:0; padding: 28px clamp(22px, 4vw, 54px) 70px; }
.mobile-nav-scrim,.mobile-nav-drawer{display:none}
@media (max-width: 760px) { .platform-sidebar { width: 82px; min-width: 82px; } .brand-copy, .nav-caption, .nav-copy, .simulator-note, .account-copy, .logout { display: none; } .platform-nav a{justify-content:center;padding:9px 6px}.nav-index{width:auto}.platform-topbar { min-height: 72px; } .topbar-contract { display: none; } .platform-content { padding: 18px 14px 44px; } .mobile-nav-scrim{display:block;position:fixed;z-index:20;inset:0;background:rgba(12,20,16,.42)}.mobile-nav-drawer{width:min(308px,calc(100vw - 82px));max-width:calc(100vw - 82px);min-height:100vh;padding:18px 14px 16px;position:fixed;z-index:21;top:0;bottom:0;left:82px;display:flex;flex-direction:column;overflow-y:auto;background:#15201b;color:#eef2ed;box-shadow:12px 0 28px rgba(12,20,16,.18)}.mobile-nav-head{padding:4px 4px 16px;border-bottom:1px solid #34423c;display:flex;align-items:center;justify-content:space-between;gap:12px}.mobile-nav-head>div{display:grid;gap:5px}.mobile-nav-head span{color:#829087;font:700 .62rem ui-monospace,monospace;letter-spacing:.13em}.mobile-nav-head strong{font-size:1rem}.mobile-drawer-close{width:36px;height:36px;border:1px solid #405048;display:grid;place-items:center;background:transparent;color:#eef2ed;cursor:pointer}.mobile-drawer-links{margin-top:14px;display:grid;gap:4px}.mobile-drawer-links a{min-height:47px;padding:10px;border:1px solid transparent;display:flex;align-items:center;gap:12px;color:#c7cec9;text-decoration:none}.mobile-drawer-links a.active{border-color:#4b6056;background:#1c2c24;color:#fff}.mobile-drawer-links a:focus-visible,.mobile-drawer-links a:hover{border-color:#53685d}.mobile-drawer-links span{width:26px;color:#b5f04c;font:700 .66rem ui-monospace,monospace}.mobile-drawer-links strong{font-size:.86rem}.mobile-drawer-account{margin-top:auto;padding-top:16px;border-top:1px solid #34423c;display:grid;gap:14px}.mobile-drawer-account>div{display:flex;align-items:center;gap:10px}.mobile-drawer-account>div>span:last-child{display:grid;gap:3px}.mobile-drawer-account small{color:#89958e;font-size:.68rem}.mobile-drawer-account button{min-height:38px;border:1px solid #4b5b52;display:flex;align-items:center;justify-content:center;gap:8px;background:transparent;color:#f0a18e;font-weight:700;cursor:pointer} }
</style>
