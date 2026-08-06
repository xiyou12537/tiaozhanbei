<template>
  <div class="auth-page">
    <section class="auth-hero">
      <div class="auth-hero-inner">
        <div class="auth-copy">
          <span class="eyebrow">Account Access</span>
          <h1>进入分子量子分布式计算平台</h1>
<div class="auth-copy-actions">
            <router-link class="ghost-btn" to="/">返回首页</router-link>
            <router-link class="text-link" to="/app/simulation-capabilities">查看模拟能力</router-link>
          </div>
        </div>

        <AuthFormCard
          class="auth-panel"
          :initialTab="activeTab"
          @tab-change="handleTabChange"
          @success="handleSuccess"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthFormCard from '../components/AuthFormCard.vue'

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => (route.query.tab === 'register' ? 'register' : 'login'))

function handleTabChange(tab) {
  router.replace({
    path: '/auth',
    query: {
      ...route.query,
      tab,
    },
  })
}

function handleSuccess(payload) {
  if (payload?.mode !== 'login') return
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/app/molecules'
  router.push(redirect)
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(55, 125, 255, 0.18), transparent 30%),
    radial-gradient(circle at 85% 20%, rgba(24, 186, 169, 0.16), transparent 28%),
    linear-gradient(180deg, #041321 0%, #051626 100%);
}

.auth-hero {
  padding: 56px 0 72px;
}

.auth-hero-inner {
  width: min(1200px, calc(100% - 48px));
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(360px, 0.98fr);
  gap: 24px;
  align-items: center;
}

.auth-copy {
  padding: 28px 0;
  color: #f8fbff;
}

.eyebrow {
  color: #67d5ca;
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 700;
}

.auth-copy h1 {
  margin-top: 12px;
  font-size: clamp(2.5rem, 4.6vw, 4rem);
  line-height: 1.06;
  letter-spacing: 0;
}

.auth-copy p {
  margin-top: 18px;
  max-width: 640px;
  color: rgba(223, 232, 243, 0.8);
  line-height: 1.82;
  font-size: 0.98rem;
}

.auth-copy-grid {
  margin-top: 28px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.copy-card {
  padding: 18px;
  border-radius: 8px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
}

.copy-card strong {
  display: block;
  color: #f8fbff;
  font-size: 0.94rem;
}

.copy-card span {
  display: block;
  margin-top: 10px;
  color: rgba(223, 232, 243, 0.74);
  line-height: 1.7;
  font-size: 0.84rem;
}

.auth-copy-actions {
  margin-top: 26px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.ghost-btn,
.text-link {
  min-height: 42px;
  padding: 0 18px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 600;
}

.ghost-btn {
  border: 1px solid rgba(166, 204, 247, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #f8fbff;
}

.text-link {
  color: #67d5ca;
}

.auth-panel {
  align-self: stretch;
}

@media (max-width: 1100px) {
  .auth-hero-inner,
  .auth-copy-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .auth-hero {
    padding-top: 32px;
  }

  .auth-hero-inner {
    width: min(1200px, calc(100% - 32px));
  }
}
</style>
