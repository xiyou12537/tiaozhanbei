<template>
  <div class="public-shell">
    <PublicSiteHeader />
    <main class="public-main">
      <router-view />
    </main>
    <HomeFooter />
  </div>
</template>

<script setup>
import PublicSiteHeader from '../components/PublicSiteHeader.vue'
import HomeFooter from '../components/home/HomeFooter.vue'
</script>

<style scoped>
.public-shell {
  min-height: 100vh;
  background: #040a14;
}

.public-main {
  min-height: calc(100vh - 186px);
}
</style>
