<template>
  <div class="home-page">
    <HeroSection />
    <main class="home-content">
      <WorkflowSection />
      <MaterialRecommendationSection />
      <DistributedQuantumSection />
      <ResultSection />
    </main>
  </div>
</template>

<script setup>
import HeroSection from '../components/home/HeroSection.vue'
import WorkflowSection from '../components/home/WorkflowSection.vue'
import MaterialRecommendationSection from '../components/home/MaterialRecommendationSection.vue'
import DistributedQuantumSection from '../components/home/DistributedQuantumSection.vue'
import ResultSection from '../components/home/ResultSection.vue'
</script>

<style scoped>
.home-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at 50% 26%, rgba(30, 140, 255, 0.14), transparent 34%),
    linear-gradient(180deg, #040a14 0%, #06101a 48%, #040a14 100%);
  color: #f4f8fb;
}

.home-content {
  width: min(1360px, calc(100% - 88px));
  margin: -18px auto 0;
  padding: 0 0 28px;
  display: grid;
  gap: 32px;
}

.home-card {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(120, 200, 255, 0.14);
  border-radius: 8px;
  background:
    radial-gradient(circle at 55% 0%, rgba(30, 140, 255, 0.12), transparent 40%),
    rgba(8, 20, 36, 0.72);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.26);
  backdrop-filter: blur(18px);
}

.home-card::after {
  position: absolute;
  inset: 0;
  border: 1px solid rgba(244, 248, 251, 0.04);
  border-radius: inherit;
  pointer-events: none;
  content: "";
}

:deep(.home-card h2) {
  position: relative;
  z-index: 2;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  color: #f4f8fb;
  font-size: 1.72rem;
  font-weight: 700;
  line-height: 1.2;
}

:deep(.home-card h2 span) {
  width: 4px;
  height: 28px;
  border-radius: 999px;
  background: linear-gradient(180deg, #34d6ff, #1e8cff);
  box-shadow: 0 0 14px rgba(52, 214, 255, 0.62);
}

@media (max-width: 980px) {
  .home-content {
    width: min(1360px, calc(100% - 40px));
  }
}
</style>
