<template>
  <div class="platform-home">
    <section class="home-hero">
      <div class="hero-copy">
        <span class="hero-kicker">MOLECULAR WORKFLOW / 04</span>
        <h1 class="hero-title"><span class="hero-title-line">分子量子</span><em class="hero-title-line">分布式计算平台</em></h1>
        <p>从分子结构，到可验证的协同计算。</p>
        <div class="hero-actions">
          <router-link class="primary-action" to="/app/molecules">开始计算 <span aria-hidden="true">↗</span></router-link>
          <a class="secondary-action" href="#process">看见完整过程 <span aria-hidden="true">↓</span></a>
        </div>
        <p class="hero-disclaimer">逻辑分布式模拟，非真实 QPU。</p>
      </div>
      <div class="hero-cluster" aria-hidden="true" data-testid="hero-lih-cluster">
        <i v-for="atom in clusterAtoms" :key="atom.id" :class="['hero-atom', atom.element.toLowerCase()]" :style="{ left: `${atom.x}%`, top: `${atom.y}%` }"></i>
        <span v-for="edge in clusterEdges" :key="edge.id" class="hero-edge" :style="edge.style"></span>
      </div>
      <div class="hero-meta" aria-hidden="true"><span>(LiH)₄ / MOLECULAR ORIGIN</span><span>SCROLL-BOUND COMPUTATION</span></div>
    </section>

    <MoleculeNarrativeCanvas />

    <section class="home-bridge" aria-label="继续使用平台">
      <div><span class="bridge-kicker">CONTINUE THE WORKFLOW</span><h2>把下一组原子<br /><em>交给平台。</em></h2></div>
      <div class="bridge-actions"><router-link class="bridge-primary" to="/app/molecules">新建计算 <span aria-hidden="true">↗</span></router-link><router-link class="bridge-secondary" to="/app/molecule-workflows">计算任务 <span aria-hidden="true">↗</span></router-link></div>
    </section>
  </div>
</template>

<script setup>
import MoleculeNarrativeCanvas from '../components/home/MoleculeNarrativeCanvas.vue'

const clusterAtoms = [
  { id: 'li-1', element: 'Li', x: 31, y: 42 }, { id: 'li-2', element: 'Li', x: 59, y: 29 },
  { id: 'li-3', element: 'Li', x: 41, y: 72 }, { id: 'li-4', element: 'Li', x: 70, y: 58 },
  { id: 'h-1', element: 'H', x: 46, y: 27 }, { id: 'h-2', element: 'H', x: 73, y: 42 },
  { id: 'h-3', element: 'H', x: 28, y: 59 }, { id: 'h-4', element: 'H', x: 55, y: 77 },
]
const clusterEdges = [
  { id: 'a', style: { left: '31%', top: '42%', width: '38%', transform: 'rotate(-18deg)' } },
  { id: 'b', style: { left: '32%', top: '58%', width: '36%', transform: 'rotate(22deg)' } },
  { id: 'c', style: { left: '46%', top: '28%', width: '28%', transform: 'rotate(49deg)' } },
]
</script>

<style scoped>
.platform-home { min-height: 100vh; overflow: clip; background: #f2f3ef; color: #17201d; }.home-hero { min-height: calc(100svh - 134px); padding: 10vh clamp(24px, 7vw, 110px) 7vh; position: relative; display: flex; align-items: center; }.hero-copy { max-width: 930px; position: relative; z-index: 1; }.hero-kicker, .bridge-kicker { color: #6f914f; font: 700 .64rem ui-monospace, monospace; letter-spacing: .12em; }.hero-title { margin: 26px 0 25px; font-size: clamp(4.5rem, 7.7vw, 7.8rem); line-height: .91; letter-spacing: 0; font-weight: 800; }.hero-title-line { display: block; white-space: nowrap; }.hero-title em { color: #5e7a4f; font-style: normal; }.hero-copy > p { margin: 0; color: #56655b; font-size: clamp(1rem, 1.4vw, 1.24rem); line-height: 1.7; }.hero-actions { margin-top: 36px; display: flex; gap: 12px; flex-wrap: wrap; }.hero-actions a { min-height: 48px; padding: 0 19px; border: 1px solid #17201d; display: inline-flex; align-items: center; gap: 20px; color: #17201d; text-decoration: none; font-size: .8rem; font-weight: 700; transition: transform .2s ease, background .2s ease, color .2s ease; }.hero-actions a:hover { transform: translateY(-2px); }.hero-actions .primary-action { background: #17201d; color: #f4f6f1; }.hero-actions .primary-action:hover { background: #2c3c32; }.hero-actions .secondary-action { border-color: #b9c3b9; color: #4d5d53; }.hero-actions .secondary-action:hover { border-color: #6f914f; color: #527634; }.hero-disclaimer { margin-top: 42px !important; color: #6c7a70 !important; font: 700 .68rem ui-monospace, monospace !important; letter-spacing: .03em; }
.hero-cluster { width: min(31vw, 420px); aspect-ratio: 1; position: absolute; right: clamp(24px, 6vw, 96px); top: 16%; opacity: .94; }.hero-atom { width: clamp(34px, 4vw, 58px); aspect-ratio: 1; position: absolute; z-index: 1; border: 1px solid #789072; border-radius: 50%; background: #b8c1ba; box-shadow: 0 0 0 8px rgba(184,193,186,.12); transform: translate(-50%, -50%); }.hero-atom.h { width: clamp(20px, 2.45vw, 34px); border-color: #c8cec5; background: #f6f7f1; box-shadow: 0 0 0 6px rgba(246,247,241,.45); }.hero-edge { height: 1px; position: absolute; z-index: 0; background: #6f914f; opacity: .65; transform-origin: left; }.hero-meta { position: absolute; right: clamp(24px, 7vw, 110px); bottom: 4vh; display: flex; flex-direction: column; align-items: flex-end; gap: 7px; color: #829087; font: .58rem ui-monospace, monospace; letter-spacing: .1em; }
.home-bridge { padding: 17vh clamp(24px, 7vw, 110px) 19vh; display: flex; align-items: end; justify-content: space-between; gap: 50px; border-top: 1px solid #c9cec7; background: #f2f3ef; }.home-bridge h2 { margin: 22px 0 0; font-size: clamp(2.7rem, 6vw, 6.8rem); line-height: .9; letter-spacing: 0; font-weight: 800; }.home-bridge h2 em { color: #5e7a4f; font-style: normal; }.bridge-actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }.bridge-actions a { min-height: 46px; padding: 0 18px; border: 1px solid #17201d; display: inline-flex; align-items: center; gap: 20px; color: #17201d; font-size: .78rem; font-weight: 700; text-decoration: none; }.bridge-primary { background: #17201d; color: #f4f6f1 !important; }.bridge-secondary { border-color: #b9c3b9 !important; color: #4d5d53 !important; }
@media (max-width: 900px) { .hero-cluster { right: 4vw; opacity: .62; }.hero-title { font-size: clamp(3.7rem, 8.2vw, 5.7rem); } }
@media (max-width: 620px) { .home-hero { min-height: calc(100svh - 132px); padding: 8vh 24px 9vh; align-items: flex-start; }.hero-copy { max-width: 100%; }.hero-title { margin: 22px 0 22px; font-size: clamp(2.55rem, 10.8vw, 3.6rem); line-height: .94; }.hero-actions { margin-top: 28px; }.hero-disclaimer { margin-top: 32px !important; }.hero-cluster { width: 164px; right: 16px; top: auto; bottom: 16px; opacity: .78; }.hero-meta { display: none; }.home-bridge { align-items: flex-start; flex-direction: column; padding: 13vh 24px 16vh; }.bridge-actions { justify-content: flex-start; } }
@media (prefers-reduced-motion: reduce) { .hero-actions a { transition: none; } }
</style>
