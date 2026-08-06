<template>
  <footer class="home-footer">
    <div class="footer-inner">
      <BrandLogo compact />
      <nav class="footer-nav" aria-label="页脚导航">
        <router-link v-for="item in links" :key="item.to" :to="item.to">{{ item.label }}</router-link>
      </nav>
      <p>© 2024 量智硫光. 保留所有权利。</p>
    </div>
  </footer>
</template>

<script setup>
import BrandLogo from './BrandLogo.vue'

const links = [
  { to: '/workflow', label: '洞察' },
  { to: '/results', label: '结果' },
  { to: '/app/knowledge', label: '知识库' },
  { to: '/overview', label: '项目' },
  { to: '/app/screening', label: '工作台' },
]
</script>

<style scoped>
.home-footer {
  border-top: 1px solid rgba(120, 200, 255, 0.12);
  background: rgba(4, 10, 20, 0.94);
}

.footer-inner {
  width: min(1360px, calc(100% - 88px));
  min-height: 94px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 30px;
  align-items: center;
}

.footer-nav {
  display: flex;
  justify-content: center;
  gap: 54px;
}

.footer-nav a {
  color: #607489;
  font-size: 0.9rem;
  text-decoration: none;
  transition: color 0.2s ease;
}

.footer-nav a:hover {
  color: #f4f8fb;
}

p {
  margin: 0;
  color: #607489;
  font-size: 0.88rem;
}

@media (max-width: 980px) {
  .footer-inner {
    width: min(1360px, calc(100% - 40px));
    grid-template-columns: 1fr;
    padding: 24px 0;
  }

  .footer-nav {
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: 18px;
  }
}
</style>
