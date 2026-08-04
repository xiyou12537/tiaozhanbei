<template>
  <section class="home-card result-section">
    <h2><span></span>推荐结果</h2>
    <div class="result-summary">
      <div class="trophy-stage" aria-hidden="true">
        <span class="trophy-ring"></span>
        <svg viewBox="0 0 96 96" class="trophy-icon">
          <defs>
            <linearGradient id="trophyGold" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#fff3b1" />
              <stop offset="45%" stop-color="#f2c35b" />
              <stop offset="100%" stop-color="#9a5f14" />
            </linearGradient>
          </defs>
          <path d="M30 18h36v16c0 16-8 26-18 26S30 50 30 34V18Z" fill="url(#trophyGold)" />
          <path d="M30 25H18c0 14 6 22 17 24M66 25h12c0 14-6 22-17 24" fill="none" stroke="#f2c35b" stroke-width="6" stroke-linecap="round" />
          <path d="M48 60v14M33 78h30M39 74h18" fill="none" stroke="#f2c35b" stroke-width="6" stroke-linecap="round" />
          <path d="m48 28 4 8 9 1-7 6 2 9-8-5-8 5 2-9-7-6 9-1z" fill="#fff7d0" />
        </svg>
      </div>

      <div class="candidate-block">
        <small>Recommended Candidate</small>
        <strong><ChemicalFormula text="Co-N-C / Li2S6" /></strong>
        <router-link to="/app/results">查看优化结果 <span>→</span></router-link>
      </div>

      <div v-for="item in resultMetrics" :key="item.label" class="result-metric">
        <small>{{ item.label }}</small>
        <strong :class="{ recommended: item.value === 'Recommended' }">{{ item.value }}</strong>
        <em v-if="item.note">{{ item.note }}</em>
      </div>
    </div>
  </section>
</template>

<script setup>
import ChemicalFormula from '../ChemicalFormula.vue'

const resultMetrics = [
  { label: 'Final Score', value: '91.4 / 100' },
  { label: 'Adsorption Energy', value: '0.78 eV', note: 'Low' },
  { label: 'Topology', value: 'Ring-3' },
  { label: 'Decision', value: 'Recommended' },
]
</script>

<style scoped>
.result-section {
  padding: 38px 42px 40px;
  background:
    radial-gradient(circle at 18% 54%, rgba(242, 195, 91, 0.12), transparent 22%),
    radial-gradient(circle at 72% 50%, rgba(30, 140, 255, 0.13), transparent 34%),
    linear-gradient(135deg, rgba(8, 20, 36, 0.86), rgba(4, 10, 20, 0.78));
}

.result-summary {
  margin-top: 32px;
  display: grid;
  grid-template-columns: 170px minmax(220px, 1.2fr) repeat(4, minmax(140px, 1fr));
  align-items: center;
}

.trophy-stage {
  position: relative;
  width: 132px;
  height: 132px;
  display: grid;
  place-items: center;
}

.trophy-ring {
  position: absolute;
  inset: 0;
  border: 1px solid rgba(30, 140, 255, 0.7);
  border-radius: 50%;
  box-shadow: inset 0 0 28px rgba(30, 140, 255, 0.2), 0 0 28px rgba(30, 140, 255, 0.18);
}

.trophy-ring::before,
.trophy-ring::after {
  position: absolute;
  inset: 14px;
  border: 1px solid rgba(52, 214, 255, 0.22);
  border-radius: 50%;
  content: "";
}

.trophy-ring::after {
  inset: 28px;
  border-color: rgba(242, 195, 91, 0.24);
}

.trophy-icon {
  position: relative;
  width: 82px;
  filter: drop-shadow(0 0 16px rgba(242, 195, 91, 0.56));
}

.candidate-block,
.result-metric {
  min-height: 112px;
  padding: 8px 32px;
  border-left: 1px solid rgba(120, 200, 255, 0.14);
  display: grid;
  align-content: center;
  gap: 10px;
}

.candidate-block small,
.result-metric small {
  color: #93a8bd;
  font-size: 0.78rem;
}

.candidate-block strong {
  color: #f4f8fb;
  font-size: 1.8rem;
  font-weight: 600;
}

.candidate-block a {
  width: fit-content;
  min-height: 40px;
  padding: 0 20px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #f4f8fb;
  background: linear-gradient(135deg, rgba(30, 140, 255, 0.88), rgba(11, 109, 232, 0.72));
  text-decoration: none;
  font-size: 0.84rem;
  font-weight: 700;
}

.result-metric strong {
  color: #f4f8fb;
  font-size: 1.85rem;
  font-weight: 600;
  line-height: 1;
}

.result-metric strong.recommended {
  color: #38f3c2;
  font-size: 1.5rem;
}

.result-metric em {
  color: #93a8bd;
  font-size: 0.82rem;
  font-style: normal;
}

@media (max-width: 1160px) {
  .result-summary {
    grid-template-columns: 160px 1fr 1fr;
    gap: 18px 0;
  }
}

@media (max-width: 760px) {
  .result-summary {
    grid-template-columns: 1fr;
  }

  .candidate-block,
  .result-metric {
    border-left: 0;
    border-top: 1px solid rgba(120, 200, 255, 0.14);
    padding-left: 0;
  }
}
</style>
