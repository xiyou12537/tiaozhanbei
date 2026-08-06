<template>
  <section class="home-card workflow-section">
    <h2><span></span>筛选流程概览</h2>
    <div class="workflow-track">
      <article v-for="(step, index) in steps" :key="step.title" class="workflow-step">
        <div class="workflow-icon" v-html="step.icon"></div>
        <strong>{{ step.title }}</strong>
        <span v-if="index < steps.length - 1" class="flow-arrow">→</span>
      </article>
    </div>
  </section>
</template>

<script setup>
const steps = [
  {
    title: '材料探索',
    icon: '<svg viewBox="0 0 48 48"><path d="M24 5 40 14v20L24 43 8 34V14z"/><path d="M24 5v18m0 20V23M8 14l16 9 16-9M8 34l16-11 16 11"/></svg>',
  },
  {
    title: '分子建模与特征计算',
    icon: '<svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="5"/><circle cx="13" cy="12" r="4"/><circle cx="36" cy="13" r="4"/><circle cx="12" cy="35" r="4"/><circle cx="36" cy="34" r="4"/><path d="M17 15l4 5m7-1 5-4M18 32l4-5m7 1 5 4"/></svg>',
  },
  {
    title: 'QASM / Hamiltonian',
    icon: '<svg viewBox="0 0 48 48"><path d="M18 15 9 24l9 9M30 15l9 9-9 9M27 10 21 38"/></svg>',
  },
  {
    title: '分布式切分',
    icon: '<svg viewBox="0 0 48 48"><rect x="9" y="9" width="11" height="11"/><rect x="28" y="9" width="11" height="11"/><rect x="9" y="28" width="11" height="11"/><rect x="28" y="28" width="11" height="11"/><path d="M20 14h8M20 33h8M14 20v8M33 20v8"/></svg>',
  },
  {
    title: '量子计算求解',
    icon: '<svg viewBox="0 0 48 48"><circle cx="15" cy="14" r="4"/><circle cx="34" cy="14" r="4"/><circle cx="24" cy="34" r="5"/><path d="M18 16l4 13m10-12-6 12M15 18c5 9 14 9 19 0"/></svg>',
  },
  {
    title: '结果评估与推荐',
    icon: '<svg viewBox="0 0 48 48"><path d="M9 38h30M12 33l8-10 7 6 10-16"/><path d="M34 13h3v3"/></svg>',
  },
]
</script>

<style scoped>
.workflow-section {
  padding: 38px 42px 40px;
  background:
    radial-gradient(circle at 86% 18%, rgba(242, 195, 91, 0.1), transparent 22%),
    radial-gradient(circle at 62% 52%, rgba(30, 140, 255, 0.16), transparent 34%),
    linear-gradient(135deg, rgba(8, 20, 36, 0.88), rgba(4, 10, 20, 0.78));
}

.workflow-track {
  margin-top: 34px;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 20px;
}

.workflow-step {
  position: relative;
  min-height: 154px;
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 14px;
  color: #f4f8fb;
  text-align: center;
}

.workflow-icon {
  width: 96px;
  height: 96px;
  border: 1px solid rgba(52, 214, 255, 0.32);
  border-radius: 10px;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 50% 50%, rgba(52, 214, 255, 0.16), transparent 58%),
    rgba(8, 20, 36, 0.72);
  box-shadow: inset 0 0 26px rgba(30, 140, 255, 0.14);
  transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.workflow-step:hover .workflow-icon {
  border-color: rgba(52, 214, 255, 0.68);
  transform: translateY(-3px);
  box-shadow: 0 0 28px rgba(30, 140, 255, 0.18), inset 0 0 34px rgba(30, 140, 255, 0.2);
}

:deep(svg) {
  width: 48px;
  height: 48px;
  fill: none;
  stroke: #eaf6ff;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.workflow-step strong {
  max-width: 112px;
  font-size: 0.98rem;
  font-weight: 600;
  line-height: 1.55;
}

.flow-arrow {
  position: absolute;
  right: -19px;
  top: 45%;
  color: #1e8cff;
  font-size: 2rem;
  text-shadow: 0 0 18px rgba(30, 140, 255, 0.8);
}

@media (max-width: 1100px) {
  .workflow-track {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .flow-arrow {
    display: none;
  }
}

@media (max-width: 680px) {
  .workflow-track {
    grid-template-columns: 1fr;
  }
}
</style>
