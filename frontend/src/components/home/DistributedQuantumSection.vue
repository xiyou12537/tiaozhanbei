<template>
  <section class="home-card distributed-section">
    <div class="distributed-copy">
      <h2><span></span>分布式量子计算</h2>
      <p>
        将量子电路任务分布在多个节点并行计算，<br />
        通过量子纠缠网络与量子态融合，突破资源限制，<br />
        形成可扩展的分布式量子计算架构。
      </p>
      <router-link class="outline-action" to="/app/capability">了解分布式方案 <span>→</span></router-link>
    </div>

    <div class="quantum-network" aria-label="分布式量子计算架构示意">
      <img :src="architectureImage" alt="分布式量子计算架构示意" />
      <div class="architecture-frame" aria-hidden="true"></div>
    </div>

    <aside class="metric-panel">
      <div v-for="metric in metrics" :key="metric.label" class="quantum-metric">
        <span class="metric-icon" aria-hidden="true">
          <i></i>
        </span>
        <span>
          <small>{{ metric.label }}</small>
          <strong>{{ metric.value }}</strong>
        </span>
      </div>
    </aside>
  </section>
</template>

<script setup>
import architectureImage from '../../assets/home/distributed-quantum-architecture.png'

const metrics = [
  { label: 'Qubits', value: '8' },
  { label: 'Partitions', value: '3' },
  { label: 'Fidelity', value: '0.94' },
  { label: 'Link Fidelity', value: '0.97' },
  { label: 'Latency', value: '12.6 ms' },
]
</script>

<style scoped>
.distributed-section {
  position: relative;
  min-height: 470px;
  padding: 42px 34px;
  display: grid;
  grid-template-columns: minmax(260px, 0.82fr) minmax(480px, 1.75fr) minmax(190px, 0.55fr);
  gap: 28px;
  overflow: hidden;
}

.distributed-section::before {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 62% 48%, rgba(30, 140, 255, 0.18), transparent 28%),
    radial-gradient(circle at 86% 18%, rgba(52, 214, 255, 0.08), transparent 24%),
    linear-gradient(90deg, transparent, rgba(30, 140, 255, 0.08), transparent);
  opacity: 0.86;
  content: "";
  pointer-events: none;
}

.distributed-copy,
.metric-panel,
.quantum-network {
  position: relative;
  z-index: 2;
}

.distributed-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.distributed-copy p {
  margin: 30px 0 0;
  color: #93a8bd;
  font-size: 0.98rem;
  line-height: 2.1;
}

.outline-action {
  width: fit-content;
  min-height: 48px;
  margin-top: 28px;
  padding: 0 22px;
  border: 1px solid rgba(120, 200, 255, 0.18);
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #f4f8fb;
  background: rgba(8, 20, 36, 0.48);
  text-decoration: none;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.outline-action:hover {
  border-color: rgba(52, 214, 255, 0.44);
  transform: translateY(-1px);
}

.quantum-network {
  min-height: 388px;
  overflow: hidden;
  border: 1px solid rgba(120, 200, 255, 0.13);
  border-radius: 12px;
  background: rgba(4, 10, 20, 0.62);
  box-shadow: inset 0 0 0 1px rgba(244, 248, 251, 0.04), 0 20px 54px rgba(0, 0, 0, 0.24);
}

.quantum-network img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 55% 50%;
  filter: saturate(1.03) contrast(1.04);
}

.architecture-frame {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(4, 10, 20, 0.18), transparent 24%, transparent 74%, rgba(4, 10, 20, 0.18)),
    radial-gradient(circle at 50% 52%, transparent 0 46%, rgba(4, 10, 20, 0.16) 76%);
  pointer-events: none;
}

.metric-panel {
  align-self: center;
  padding: 22px;
  border: 1px solid rgba(120, 200, 255, 0.14);
  border-radius: 10px;
  background: rgba(8, 20, 36, 0.58);
  backdrop-filter: blur(18px);
}

.quantum-metric {
  min-height: 62px;
  display: grid;
  grid-template-columns: 38px 1fr;
  gap: 14px;
  align-items: center;
}

.quantum-metric + .quantum-metric {
  margin-top: 12px;
}

.metric-icon {
  width: 34px;
  height: 34px;
  border: 1px solid rgba(120, 200, 255, 0.16);
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(4, 10, 20, 0.62);
}

.metric-icon i {
  width: 12px;
  height: 12px;
  border: 1px solid rgba(52, 214, 255, 0.8);
  border-radius: 50%;
  box-shadow: 0 0 12px rgba(52, 214, 255, 0.5);
}

.quantum-metric small {
  display: block;
  color: #93a8bd;
  font-size: 0.78rem;
}

.quantum-metric strong {
  display: block;
  margin-top: 4px;
  color: #f4f8fb;
  font-size: 1.34rem;
  font-weight: 600;
  line-height: 1;
}

@media (max-width: 1180px) {
  .distributed-section {
    grid-template-columns: 1fr;
  }

  .quantum-network {
    min-height: 460px;
  }

  .metric-panel {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 12px;
  }

  .quantum-metric + .quantum-metric {
    margin-top: 0;
  }
}

@media (max-width: 760px) {
  .metric-panel {
    grid-template-columns: 1fr;
  }

  .quantum-network {
    min-height: 320px;
  }
}
</style>
