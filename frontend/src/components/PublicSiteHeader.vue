<template>
  <header class="public-header">
    <router-link class="public-brand" to="/"><span>MQ</span><strong>分子量子分布式计算平台</strong></router-link>
    <nav><router-link to="/app/molecules">新建分子计算</router-link><router-link to="/app/molecule-workflows">计算任务</router-link><router-link to="/app/simulation-capabilities">模拟能力说明</router-link></nav>
    <router-link class="account-link" to="/auth?tab=login">进入平台 ↗</router-link>
  </header>
</template>

<style scoped>
.public-header{height:76px;padding:0 clamp(22px,4vw,58px);border-bottom:1px solid var(--lz-line);display:grid;grid-template-columns:1fr auto 1fr;align-items:center;background:var(--lz-bg);color:var(--lz-text)}.public-brand{display:flex;align-items:center;gap:12px;color:inherit;text-decoration:none}.public-brand span{width:34px;height:34px;display:grid;place-items:center;border-radius:50%;background:var(--lz-accent);color:#e7f3ec;font:800 .7rem var(--lz-mono)}.public-brand strong{font-size:.82rem}.public-header nav{display:flex;gap:36px}.public-header nav a,.account-link{color:var(--lz-muted);text-decoration:none;font-size:.76rem;font-weight:600}.account-link{justify-self:end;color:var(--lz-text)}@media(max-width:850px){.public-header{grid-template-columns:1fr auto}.public-header nav{display:none}.public-brand strong{font-size:.72rem}}
</style>
