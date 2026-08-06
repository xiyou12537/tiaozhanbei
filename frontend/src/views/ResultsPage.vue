<template>
  <div class="public-stage-page">
    <section class="public-stage-hero">
      <div class="public-stage-shell">
        <div class="public-stage-grid">
          <div class="public-stage-copy">
            <span class="public-stage-kicker">Results</span>
            <h1>&#x7EFC;&#x5408;&#x7ED3;&#x679C;</h1>

            <div class="public-stage-actions">
              <router-link class="public-button" to="/app/results">&#x6253;&#x5F00;&#x5E94;&#x7528;&#x7ED3;&#x679C;</router-link>
              <router-link class="public-button-ghost" to="/app/screening">&#x8FD4;&#x56DE;&#x5DE5;&#x4F5C;&#x53F0;</router-link>
            </div>
          </div>

          <aside class="public-stage-aside">
            <span class="public-panel-kicker">Summary</span>
            <div class="public-stat-list">
              <article v-for="item in summaryCards" :key="item.label" class="public-stat-card">
                <span>{{ item.label }}</span>
                <strong><ChemicalFormula :text="item.value" /></strong>
                <small>{{ item.note }}</small>
              </article>
            </div>
          </aside>
        </div>
      </div>
    </section>

    <div class="public-stage-shell public-stage-stack">
      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Leaderboard</span>
            <h2>&#x5019;&#x9009;&#x6392;&#x5E8F;</h2>
          </div>
        </div>

        <div class="public-grid-3">
          <article v-for="item in candidates" :key="item.name" class="public-metric-card">
            <span><ChemicalFormula :text="item.name" /></span>
            <strong>{{ item.score }}</strong>
          </article>
        </div>
      </section>

      <section class="public-section-panel">
        <div class="public-section-head">
          <div>
            <span class="public-panel-kicker">Metrics</span>
            <h2>&#x5173;&#x952E;&#x6307;&#x6807;</h2>
          </div>
        </div>

        <div class="public-grid-3">
          <article v-for="item in metrics" :key="item.label" class="public-metric-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import ChemicalFormula from '../components/ChemicalFormula.vue'

const summaryCards = [
  { label: 'Candidate', value: 'Li2S6', note: 'recommended' },
  { label: 'FinalScore', value: '88.6', note: 'weighted' },
  { label: 'Topology', value: 'linear-3', note: 'selected' },
]

const candidates = [
  { name: 'Li2S6', score: '88.6' },
  { name: 'Li2S4', score: '83.9' },
  { name: 'Li2S8', score: '81.1' },
]

const metrics = [
  { label: 'ChemScore', value: '91.4' },
  { label: 'DeployScore', value: '85.8' },
  { label: 'qubit_count', value: '8' },
  { label: 'partition_count', value: '3' },
  { label: 'teleportations', value: '2' },
  { label: 'fidelity_score', value: '0.93' },
]
</script>
