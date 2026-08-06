<template>
  <section class="hero-section">
    <img class="hero-reference-image" :src="heroImage" alt="量智硫光分子晶格主视觉" />
    <div class="particle-field" aria-hidden="true">
      <span
        v-for="particle in particles"
        :key="particle.left + '-' + particle.top"
        :style="{
          left: `${particle.left}%`,
          top: `${particle.top}%`,
          animationDelay: `${particle.delay}s`,
        }"
        :class="{ gold: particle.gold }"
      ></span>
    </div>
    <HeroMolecule />

    <div class="hero-inner">
      <div class="hero-copy">
        <h1>
          量子计算驱动的<br />
          锂硫材料筛选平台
        </h1>
        <p>
          结合分布式量子计算与材料数据库，精准预测锂硫电池材料，
          加速材料发现，推动能源科技升级。
        </p>
        <div class="hero-actions">
          <router-link class="primary-action" to="/app/screening">进入工作台 <span>→</span></router-link>
          <router-link class="secondary-action" to="/results">查看演示案例</router-link>
        </div>
        <div class="hero-metrics" aria-label="平台指标">
          <div v-for="metric in metrics" :key="metric.label" class="metric-item">
            <strong>{{ metric.value }}</strong>
            <span>{{ metric.label }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import heroImage from '../../assets/chemistry-hero.png'
import HeroMolecule from './HeroMolecule.vue'

const metrics = [
  { value: '12', label: 'Candidates' },
  { value: '8', label: 'Qubits' },
  { value: '3', label: 'Partitions' },
  { value: '0.94', label: 'Fidelity' },
]

const particles = [
  { left: 12, top: 18, delay: 0.2 },
  { left: 28, top: 36, delay: 0.7 },
  { left: 53, top: 17, delay: 1.1, gold: true },
  { left: 72, top: 12, delay: 0.4 },
  { left: 85, top: 30, delay: 1.6 },
  { left: 63, top: 62, delay: 2.1, gold: true },
  { left: 44, top: 78, delay: 0.9 },
  { left: 18, top: 69, delay: 1.8 },
  { left: 36, top: 12, delay: 2.4 },
  { left: 78, top: 72, delay: 0.6 },
  { left: 91, top: 48, delay: 1.3, gold: true },
  { left: 7, top: 42, delay: 2.7 },
  { left: 59, top: 84, delay: 1.9 },
  { left: 69, top: 43, delay: 0.3 },
  { left: 48, top: 52, delay: 2.2, gold: true },
  { left: 31, top: 86, delay: 1.4 },
]
</script>

<style scoped>
.hero-section {
  position: relative;
  min-height: 720px;
  overflow: hidden;
  background:
    radial-gradient(circle at 68% 24%, rgba(30, 140, 255, 0.2), transparent 33%),
    radial-gradient(circle at 88% 42%, rgba(52, 214, 255, 0.14), transparent 29%),
    radial-gradient(circle at 16% 12%, rgba(217, 166, 59, 0.1), transparent 24%),
    linear-gradient(180deg, #040a14 0%, #06101a 56%, #040a14 100%);
}

.hero-section::before,
.hero-section::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: "";
}

.hero-section::before {
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.028) 1px, transparent 1px),
    linear-gradient(0deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 76px 76px;
  mask-image: linear-gradient(180deg, transparent 0%, #000 14%, #000 76%, transparent 100%);
  opacity: 0.55;
}

.hero-section::after {
  background:
    linear-gradient(90deg, #040a14 0%, rgba(4, 10, 20, 0.84) 34%, rgba(4, 10, 20, 0.2) 66%, rgba(4, 10, 20, 0.78) 100%),
    linear-gradient(180deg, rgba(4, 10, 20, 0.06) 0%, #040a14 100%);
}

.hero-reference-image {
  position: absolute;
  inset: 0 0 0 auto;
  width: min(980px, 68vw);
  height: 100%;
  object-fit: cover;
  object-position: 66% 48%;
  opacity: 0.74;
  filter: saturate(1.08) contrast(1.06);
  pointer-events: none;
  mask-image: linear-gradient(90deg, transparent 0%, #000 18%, #000 82%, transparent 100%);
}

.particle-field {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.particle-field span {
  position: absolute;
  width: 2px;
  height: 2px;
  border-radius: 50%;
  background: rgba(52, 214, 255, 0.68);
  box-shadow: 0 0 10px rgba(52, 214, 255, 0.8);
  animation: starBlink 4s ease-in-out infinite;
}

.particle-field span.gold {
  background: rgba(242, 195, 91, 0.65);
  box-shadow: 0 0 10px rgba(242, 195, 91, 0.7);
}

.hero-inner {
  position: relative;
  z-index: 3;
  width: min(1360px, calc(100% - 88px));
  min-height: 720px;
  margin: 0 auto;
  display: flex;
  align-items: center;
}

.hero-copy {
  width: min(620px, 48vw);
  padding: 72px 0 88px;
  animation: heroRise 0.8s ease both;
}

.hero-copy h1 {
  margin: 0;
  color: #f4f8fb;
  font-size: clamp(3.8rem, 5vw, 5.6rem);
  font-weight: 700;
  line-height: 1.16;
  letter-spacing: -0.03em;
}

.hero-copy p {
  max-width: 610px;
  margin: 28px 0 0;
  color: #93a8bd;
  font-size: 1.04rem;
  line-height: 2;
}

.hero-actions {
  margin-top: 42px;
  display: flex;
  gap: 20px;
  align-items: center;
}

.primary-action,
.secondary-action {
  min-height: 58px;
  padding: 0 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #f4f8fb;
  font-weight: 700;
  text-decoration: none;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.primary-action {
  background: linear-gradient(135deg, #1e8cff, #0b6de8);
  box-shadow: 0 18px 42px rgba(30, 140, 255, 0.28);
}

.secondary-action {
  border: 1px solid rgba(242, 195, 91, 0.28);
  background: rgba(8, 20, 36, 0.54);
  backdrop-filter: blur(16px);
}

.primary-action:hover,
.secondary-action:hover {
  transform: translateY(-2px);
}

.secondary-action:hover {
  border-color: rgba(242, 195, 91, 0.46);
  background: rgba(8, 20, 36, 0.76);
}

.hero-metrics {
  width: min(560px, 100%);
  margin-top: 50px;
  padding-top: 26px;
  border-top: 1px solid rgba(120, 200, 255, 0.16);
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.metric-item {
  min-height: 72px;
  display: grid;
  gap: 8px;
  align-content: start;
}

.metric-item + .metric-item {
  border-left: 1px solid rgba(120, 200, 255, 0.12);
  padding-left: 34px;
}

.metric-item strong {
  color: #f4f8fb;
  font-size: 2.45rem;
  font-weight: 600;
  line-height: 1;
}

.metric-item span {
  color: #93a8bd;
  font-size: 0.9rem;
}

@keyframes heroRise {
  from {
    opacity: 0;
    transform: translateY(24px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes starBlink {
  0%,
  100% {
    opacity: 0.24;
    transform: scale(0.75);
  }

  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

@media (max-width: 960px) {
  .hero-inner {
    width: min(1360px, calc(100% - 40px));
    align-items: flex-start;
  }

  .hero-copy {
    width: 100%;
    padding-top: 82px;
  }
}

@media (max-width: 680px) {
  .hero-section,
  .hero-inner {
    min-height: 780px;
  }

  .hero-actions,
  .hero-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    flex-wrap: wrap;
  }

  .metric-item + .metric-item {
    padding-left: 18px;
  }
}
</style>
