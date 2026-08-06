<template>
  <header class="home-header">
    <div class="header-inner">
      <BrandLogo />

      <nav class="header-nav" aria-label="主导航">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ active: item.to === '/' && route.path === '/' }"
        >
          {{ item.label }}
        </router-link>
      </nav>

      <div class="header-actions">
        <button class="status-button" type="button">12</button>
        <button class="ghost-button" type="button">通知</button>
        <router-link class="workbench-button" to="/app/screening">工作台</router-link>
      </div>
    </div>
  </header>
</template>

<script setup>
import { useRoute } from 'vue-router'
import BrandLogo from './BrandLogo.vue'

const route = useRoute()

const navItems = [
  { to: '/', label: '首页' },
  { to: '/workflow', label: '洞察' },
  { to: '/results', label: '结果' },
  { to: '/app/knowledge', label: '知识库' },
  { to: '/overview', label: '项目' },
]
</script>

<style scoped>
.home-header {
  position: sticky;
  top: 0;
  z-index: 40;
  border-bottom: 1px solid rgba(120, 200, 255, 0.13);
  background: rgba(4, 10, 20, 0.72);
  backdrop-filter: blur(22px);
}

.header-inner {
  width: min(1360px, calc(100% - 88px));
  min-height: 92px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(250px, auto) 1fr auto;
  gap: 34px;
  align-items: center;
}

.header-nav,
.header-actions {
  display: flex;
  align-items: center;
}

.header-nav {
  justify-content: center;
  gap: 42px;
}

.nav-link {
  position: relative;
  color: rgba(244, 248, 251, 0.66);
  font-size: 0.94rem;
  font-weight: 600;
  text-decoration: none;
}

.nav-link::after {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -14px;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, #34d6ff, #f2c35b);
  opacity: 0;
  transform: scaleX(0.35);
  transition: opacity 0.2s ease, transform 0.2s ease;
  content: "";
}

.nav-link:hover,
.nav-link.active {
  color: #f4f8fb;
}

.nav-link:hover::after,
.nav-link.active::after {
  opacity: 1;
  transform: scaleX(1);
}

.header-actions {
  justify-content: flex-end;
  gap: 16px;
}

.status-button,
.ghost-button,
.workbench-button {
  min-width: 72px;
  min-height: 48px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #f4f8fb;
  font-size: 0.92rem;
  font-weight: 700;
  text-decoration: none;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.status-button,
.ghost-button {
  border: 1px solid rgba(120, 200, 255, 0.15);
  background: rgba(8, 20, 36, 0.46);
  cursor: pointer;
}

.status-button:hover,
.ghost-button:hover {
  border-color: rgba(52, 214, 255, 0.36);
  background: rgba(8, 20, 36, 0.72);
  transform: translateY(-1px);
}

.workbench-button {
  border: 1px solid rgba(30, 140, 255, 0.7);
  background: linear-gradient(135deg, #1e8cff, #0b6de8);
  box-shadow: 0 14px 32px rgba(30, 140, 255, 0.22);
}

.workbench-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 38px rgba(30, 140, 255, 0.28);
}

@media (max-width: 1100px) {
  .header-inner {
    width: min(1360px, calc(100% - 40px));
    grid-template-columns: 1fr auto;
    padding: 14px 0;
  }

  .header-nav {
    grid-column: 1 / -1;
    grid-row: 2;
    justify-content: flex-start;
    gap: 24px;
    overflow-x: auto;
  }
}

@media (max-width: 680px) {
  .header-inner {
    grid-template-columns: 1fr;
  }

  .header-actions {
    justify-content: flex-start;
  }
}
</style>
