<template>
  <div class="platform-home">
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">MOLECULE → HAMILTONIAN → DISTRIBUTED SIMULATION</span>
        <h1>分子量子<br><em>分布式计算平台</em></h1>
        <p>从固定分子几何出发，生成量子 Hamiltonian 与 VQE 线路，在可审计的虚拟 QPU 拓扑和芯片耦合约束下完成路由与逻辑分布式模拟。</p>
        <div class="hero-actions">
          <router-link class="primary-action" to="/app/molecules">新建分子计算 <span>↗</span></router-link>
          <router-link class="secondary-action" to="/app/simulation-capabilities">查看模拟能力</router-link>
        </div>
      </div>
      <div class="hero-diagram" aria-label="计算流程示意">
        <div class="diagram-grid"></div>
        <span class="molecule-node node-a">H</span><span class="molecule-node node-b">H</span><i class="bond"></i>
        <div class="flow-label"><strong>9</strong><span>个可追踪阶段</span></div>
        <div class="qpu qpu-a"><small>VIRTUAL QPU 01</small><b>q0 — q2 — q1</b></div>
        <div class="qpu qpu-b"><small>VIRTUAL QPU 02</small><b>q0 — q1</b></div>
        <svg viewBox="0 0 640 440" aria-hidden="true"><path d="M155 178 C255 132 330 185 388 245"/><path d="M388 245 C450 292 490 270 526 218"/></svg>
      </div>
    </section>

    <section class="workflow-strip">
      <article v-for="(step, index) in workflow" :key="step.title">
        <span>{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ step.title }}</strong><p>{{ step.text }}</p></div>
      </article>
    </section>

    <section class="home-proof">
      <div><span class="eyebrow">EXECUTION BOUNDARY</span><h2>结果可查看，边界不含混</h2></div>
      <div class="proof-grid">
        <article><strong>模拟器</strong><p>固定显示执行后端类型，不暗示物理芯片执行。</p></article>
        <article><strong>非真实 QPU</strong><p>以服务端 is_real_qpu 为唯一判断依据。</p></article>
        <article><strong>路由证据</strong><p>分开呈现分区间拓扑、芯片内耦合、SWAP 路径和布局变化。</p></article>
      </div>
    </section>
  </div>
</template>

<script setup>
const workflow = [
  { title: '分子结构', text: '固定几何、电荷、自旋与基组' },
  { title: '量子线路', text: 'Hamiltonian、VQE 与 QASM' },
  { title: '分区路由', text: '虚拟拓扑、芯片耦合与 SWAP' },
  { title: '能量质量', text: '分布式能量、误差与复核状态' },
]
</script>

<style scoped>
.platform-home { min-height: 100vh; background: #f2f3ef; color: #16201c; }
.hero { width: min(1380px, calc(100% - 72px)); min-height: 690px; margin: 0 auto; padding: 90px 0 64px; display: grid; grid-template-columns: .9fr 1.1fr; gap: 70px; align-items: center; }
.eyebrow { color: #66716a; font: 700 .7rem ui-monospace, monospace; letter-spacing: .13em; }
.hero h1 { margin: 24px 0; font-size: clamp(3.2rem, 6vw, 6.7rem); line-height: .92; letter-spacing: -.075em; font-weight: 800; }
.hero h1 em { color: #5e7a4f; font-style: normal; }
.hero-copy > p { max-width: 620px; color: #5e6963; font-size: 1rem; line-height: 1.9; }
.hero-actions { margin-top: 34px; display: flex; gap: 12px; }
.hero-actions a { min-height: 50px; padding: 0 20px; border: 1px solid #1b2721; display: inline-flex; align-items: center; gap: 24px; color: #17201c; text-decoration: none; font-size: .84rem; font-weight: 700; }
.hero-actions .primary-action { background: #17201c; color: #f5f7f2; }
.hero-diagram { height: 520px; position: relative; overflow: hidden; border: 1px solid #bcc4bb; background: #e7eae3; }
.diagram-grid { position: absolute; inset: 0; opacity: .42; background-image: linear-gradient(#c3cac2 1px, transparent 1px), linear-gradient(90deg,#c3cac2 1px,transparent 1px); background-size: 42px 42px; }
.molecule-node { width: 74px; height: 74px; position: absolute; top: 115px; z-index: 2; border-radius: 50%; display: grid; place-items: center; background: #17201c; color: #b5f04c; font: 700 1.2rem ui-monospace, monospace; }
.node-a { left: 80px; }.node-b { left: 225px; }.bond { width: 90px; height: 2px; position: absolute; left: 147px; top: 151px; background: #17201c; }
.flow-label { position: absolute; left: 76px; bottom: 70px; display: flex; align-items: baseline; gap: 10px; }.flow-label strong { font-size: 4rem; line-height: 1; }.flow-label span { color: #59655e; font-size: .78rem; }
.qpu { min-width: 190px; padding: 17px 20px; position: absolute; z-index: 2; border: 1px solid #17201c; background: #f2f3ef; }.qpu small { display: block; color: #718078; font: 700 .62rem ui-monospace,monospace; }.qpu b { display: block; margin-top: 11px; font: 700 .84rem ui-monospace,monospace; }.qpu-a { right: 58px; top: 225px; }.qpu-b { right: 88px; top: 330px; border-color: #668846; }
.hero-diagram svg { position: absolute; inset: 0; width: 100%; height: 100%; }.hero-diagram path { fill: none; stroke: #668846; stroke-width: 2; stroke-dasharray: 5 5; }
.workflow-strip { display: grid; grid-template-columns: repeat(4,1fr); border-top: 1px solid #cbd0c9; border-bottom: 1px solid #cbd0c9; }
.workflow-strip article { min-height: 170px; padding: 34px clamp(20px,3vw,46px); border-right: 1px solid #cbd0c9; display: flex; gap: 24px; }.workflow-strip article:last-child { border-right: 0; }.workflow-strip article > span { color: #70984a; font: 700 .72rem ui-monospace,monospace; }.workflow-strip strong { font-size: .92rem; }.workflow-strip p { margin: 14px 0 0; color: #69746e; font-size: .78rem; line-height: 1.65; }
.home-proof { width: min(1240px,calc(100% - 72px)); margin: 0 auto; padding: 110px 0 130px; display: grid; grid-template-columns: .7fr 1.3fr; gap: 80px; }.home-proof h2 { max-width: 420px; margin: 16px 0 0; font-size: clamp(2rem,4vw,4.4rem); line-height: 1; letter-spacing: -.06em; }.proof-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 1px; background: #bdc5bd; }.proof-grid article { min-height: 230px; padding: 30px; background: #f2f3ef; }.proof-grid strong { font-size: 1rem; }.proof-grid p { margin: 75px 0 0; color: #66716b; font-size: .8rem; line-height: 1.7; }
@media(max-width:980px){.hero,.home-proof{grid-template-columns:1fr}.hero{padding-top:60px}.workflow-strip{grid-template-columns:repeat(2,1fr)}.proof-grid{grid-template-columns:1fr}.proof-grid article{min-height:150px}.proof-grid p{margin-top:35px}} @media(max-width:640px){.hero,.home-proof{width:calc(100% - 36px)}.hero-diagram{height:430px}.workflow-strip{grid-template-columns:1fr}.hero-actions{align-items:stretch;flex-direction:column}.hero h1{font-size:3.2rem}}
</style>
