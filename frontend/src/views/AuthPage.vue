<template>
  <div class="auth-page">
    <section class="auth-hero">
      <div class="auth-hero-inner">
        <div class="auth-copy">
          <span class="eyebrow">账号与工作区</span>
          <h1>进入分子量子<br><em>计算工作区</em></h1>
          <p>使用平台账号访问分子计算、任务记录与可审计的分布式模拟结果。</p>

          <div class="auth-schematic" aria-hidden="true">
            <header><span>Workflow 契约 V2</span><i></i></header>
            <div class="molecule-pair"><b>H</b><span></span><b>H</b></div>
            <div class="virtual-chip chip-one"><small>虚拟 QPU 01</small><strong>q0 — q2 — q1</strong></div>
            <div class="virtual-chip chip-two"><small>虚拟 QPU 02</small><strong>q0 — q1</strong></div>
          </div>

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
  min-height: calc(100dvh - 172px);
  background: #f2f3ef;
  color: #17201d;
}

.auth-hero {
  padding: 42px 0 64px;
}

.auth-hero-inner {
  width: min(1240px, calc(100% - 72px));
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(400px, 0.92fr);
  border: 1px solid #c5ccc4;
  background: #e7eae4;
}

.auth-copy {
  min-width: 0;
  padding: 48px;
  border-right: 1px solid #c5ccc4;
  display: flex;
  flex-direction: column;
}

.eyebrow {
  color: #66736b;
  font: 700 0.68rem ui-monospace, monospace;
  letter-spacing: 0;
}

.auth-copy h1 {
  margin: 22px 0 18px;
  max-width: 690px;
  font-size: 5.1rem;
  line-height: 0.94;
  letter-spacing: 0;
  font-weight: 800;
  text-wrap: balance;
}

.auth-copy h1 em {
  color: #5e7a4f;
  font-style: normal;
}

.auth-copy > p {
  max-width: 580px;
  margin: 0;
  color: #5f6b64;
  font-size: 0.9rem;
  line-height: 1.8;
  text-wrap: pretty;
}

.auth-schematic {
  min-height: 250px;
  margin-top: 36px;
  position: relative;
  overflow: hidden;
  border: 1px solid #bdc6bc;
  background-color: #f2f3ef;
  background-image: linear-gradient(#d8ddd6 1px, transparent 1px), linear-gradient(90deg, #d8ddd6 1px, transparent 1px);
  background-size: 32px 32px;
}

.auth-schematic header {
  height: 42px;
  padding: 0 14px;
  border-bottom: 1px solid #cbd1ca;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(242, 243, 239, 0.92);
}

.auth-schematic header span {
  color: #68766d;
  font: 700 0.62rem ui-monospace, monospace;
  letter-spacing: 0;
}

.auth-schematic header i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #b5f04c;
  box-shadow: 0 0 0 4px rgba(181, 240, 76, 0.16);
}

.molecule-pair {
  position: absolute;
  left: 36px;
  top: 91px;
  display: flex;
  align-items: center;
}

.molecule-pair b {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #17201d;
  color: #b5f04c;
  font: 700 0.9rem ui-monospace, monospace;
}

.molecule-pair span {
  width: 54px;
  height: 1px;
  background: #17201d;
}

.virtual-chip {
  min-width: 170px;
  padding: 13px 15px;
  position: absolute;
  right: 28px;
  border: 1px solid #17201d;
  background: #f7f8f4;
}

.virtual-chip small {
  display: block;
  color: #718078;
  font: 700 0.58rem ui-monospace, monospace;
}

.virtual-chip strong {
  display: block;
  margin-top: 8px;
  font: 700 0.76rem ui-monospace, monospace;
}

.chip-one {
  top: 79px;
}

.chip-two {
  top: 157px;
  border-color: #6f914f;
}

.auth-copy-actions {
  margin-top: 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.ghost-btn,
.text-link {
  min-height: 42px;
  padding: 0 18px;
  border: 1px solid #17201d;
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  font-size: 0.8rem;
  font-weight: 700;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.ghost-btn {
  background: #17201d;
  color: #f4f6f1;
}

.text-link {
  border-color: #b9c1b8;
  color: #445149;
}

.ghost-btn:hover,
.text-link:hover {
  transform: translateY(-1px);
}

.ghost-btn:hover {
  background: #26332d;
}

.text-link:hover {
  border-color: #6f914f;
  color: #527634;
}

.ghost-btn:focus-visible,
.text-link:focus-visible {
  outline: 2px solid #6f914f;
  outline-offset: 3px;
}

.auth-panel {
  min-width: 0;
}

@media (max-width: 980px) {
  .auth-hero-inner {
    grid-template-columns: 1fr;
  }

  .auth-copy {
    border-right: 0;
    border-bottom: 1px solid #c5ccc4;
  }
}

@media (max-width: 1180px) and (min-width: 721px) {
  .auth-copy h1 {
    font-size: 4.25rem;
  }
}

@media (max-width: 720px) {
  .auth-hero {
    padding: 24px 0 42px;
  }

  .auth-hero-inner {
    width: calc(100% - 28px);
  }

  .auth-copy {
    padding: 30px 24px;
  }

  .auth-copy h1 {
    font-size: 2.65rem;
  }

  .auth-schematic {
    min-height: 220px;
  }

  .molecule-pair {
    left: 22px;
    top: 78px;
  }

  .molecule-pair b {
    width: 40px;
    height: 40px;
  }

  .molecule-pair span {
    width: 28px;
  }

  .virtual-chip {
    min-width: 142px;
    right: 16px;
  }

  .chip-one {
    top: 70px;
  }

  .chip-two {
    top: 140px;
  }

  .auth-copy-actions {
    align-items: stretch;
    flex-direction: column;
  }

.auth-copy-actions a {
    justify-content: center;
  }
}
.auth-page{background:var(--lz-bg);color:var(--lz-text)}.auth-hero-inner{border-color:var(--lz-line);border-radius:var(--lz-radius);background:var(--lz-bg-soft);overflow:hidden}.auth-copy{border-color:var(--lz-line)}.eyebrow,.auth-schematic header span{color:var(--lz-accent-deep);letter-spacing:.07em}.auth-copy h1{line-height:var(--lz-title-leading);letter-spacing:-.035em}.auth-copy h1 em{color:var(--lz-accent)}.auth-copy>p{color:var(--lz-muted);line-height:var(--lz-body-leading)}.auth-schematic{border-color:var(--lz-line);background-color:var(--lz-bg);background-image:linear-gradient(var(--lz-line-soft) 1px,transparent 1px),linear-gradient(90deg,var(--lz-line-soft) 1px,transparent 1px)}.auth-schematic header{border-color:var(--lz-line);background:rgba(247,247,244,.94)}.auth-schematic header i{background:var(--lz-accent);box-shadow:0 0 0 4px rgba(36,92,74,.12)}.molecule-pair b,.ghost-btn{background:var(--lz-accent)}.molecule-pair b{color:#e7f3ec}.chip-two{border-color:var(--lz-accent)}.ghost-btn,.text-link{border-radius:var(--lz-radius-small)}.text-link{border-color:var(--lz-line-strong);color:var(--lz-muted)}.ghost-btn:hover{background:var(--lz-accent-hover)}.text-link:hover{border-color:var(--lz-accent);color:var(--lz-accent-deep)}
</style>
