<template>
  <section class="home-card material-section">
    <h2><span></span>材料候选推荐</h2>
    <div class="material-layout">
      <article class="featured-material">
        <span class="recommend-badge">推荐候选</span>
        <div class="material-surface" aria-hidden="true">
          <span v-for="index in 72" :key="index"></span>
        </div>
        <div class="material-copy">
          <strong><ChemicalFormula text="Li2S6" /></strong>
          <small>Polysulfide</small>
          <div class="material-metrics">
            <span>
              <em>稳定性 (eV)</em>
              <b>0.82</b>
            </span>
            <span>
              <em>电导率</em>
              <b>High</b>
            </span>
            <span>
              <em>量子态</em>
              <b>Selected</b>
            </span>
          </div>
        </div>
        <div class="hologram">
          <MoleculeProjection />
        </div>
      </article>

      <div class="side-materials">
        <article v-for="item in sideMaterials" :key="item.name" class="side-card">
          <div class="side-surface" aria-hidden="true"></div>
          <div class="side-copy">
            <strong><ChemicalFormula :text="item.name" /></strong>
            <small>{{ item.type }}</small>
            <div class="side-metrics">
              <span>
                <em>稳定性 (eV)</em>
                <b>{{ item.energy }}</b>
              </span>
              <span>
                <em>稳定性</em>
                <b>{{ item.stability }}</b>
              </span>
            </div>
          </div>
          <component :is="item.visual" />
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import MoleculeProjection from './visuals/MoleculeProjection.vue'
import LatticeVisual from './visuals/LatticeVisual.vue'
import NanotubeVisual from './visuals/NanotubeVisual.vue'
import ChemicalFormula from '../ChemicalFormula.vue'

const sideMaterials = [
  { name: 'MoS2', type: 'Layered', energy: '0.74', stability: 'Medium', visual: LatticeVisual },
  { name: 'VG-CNT', type: 'Covalent CNT', energy: '0.69', stability: 'Medium', visual: NanotubeVisual },
]
</script>

<style scoped>
.material-section {
  padding: 38px 38px 36px;
}

.material-layout {
  margin-top: 34px;
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(340px, 1fr);
  gap: 24px;
}

.featured-material,
.side-card {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(120, 200, 255, 0.14);
  border-radius: 10px;
  background:
    radial-gradient(circle at 78% 36%, rgba(242, 195, 91, 0.18), transparent 26%),
    radial-gradient(circle at 70% 68%, rgba(30, 140, 255, 0.22), transparent 34%),
    radial-gradient(circle at 70% 54%, rgba(30, 140, 255, 0.2), transparent 36%),
    linear-gradient(135deg, rgba(8, 20, 36, 0.86), rgba(6, 16, 26, 0.72));
}

.featured-material {
  min-height: 430px;
  border-color: rgba(217, 166, 59, 0.42);
  box-shadow: inset 0 0 0 1px rgba(242, 195, 91, 0.08), 0 22px 60px rgba(0, 0, 0, 0.24);
}

.featured-material::before,
.side-card::before {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 62% 52%, rgba(242, 195, 91, 0.16), transparent 24%),
    linear-gradient(90deg, rgba(52, 214, 255, 0.08) 1px, transparent 1px),
    linear-gradient(0deg, rgba(52, 214, 255, 0.05) 1px, transparent 1px);
  background-size: 56px 56px;
  opacity: 0.42;
  mix-blend-mode: screen;
  content: "";
}

.recommend-badge {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 3;
  min-width: 130px;
  height: 52px;
  padding: 0 22px;
  border-radius: 0 0 10px 0;
  display: inline-flex;
  align-items: center;
  color: #fff7d8;
  background: linear-gradient(135deg, rgba(217, 166, 59, 0.52), rgba(92, 56, 12, 0.52));
  font-weight: 700;
}

.material-surface {
  position: absolute;
  right: -4%;
  bottom: -8%;
  z-index: 1;
  width: 72%;
  height: 48%;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px 18px;
  opacity: 0.56;
  transform: perspective(680px) rotateX(62deg) rotateZ(-9deg);
}

.material-surface::before,
.material-surface::after,
.side-surface::before,
.side-surface::after {
  position: absolute;
  content: "";
}

.material-surface::before {
  inset: -14px;
  background:
    linear-gradient(135deg, transparent 0 48%, rgba(52, 214, 255, 0.32) 49%, transparent 50%),
    linear-gradient(45deg, transparent 0 48%, rgba(52, 214, 255, 0.2) 49%, transparent 50%);
  background-size: 34px 34px;
}

.material-surface::after {
  left: 42%;
  top: 42%;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(52, 214, 255, 0.56), rgba(30, 140, 255, 0.16) 34%, transparent 66%);
  filter: blur(1px);
}

.material-surface span {
  position: relative;
  z-index: 1;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #1e8cff;
  box-shadow: 0 0 14px rgba(30, 140, 255, 0.9);
}

.material-surface span:nth-child(5n) {
  background: #f2c35b;
  box-shadow: 0 0 16px rgba(242, 195, 91, 0.72);
}

.material-copy {
  position: relative;
  z-index: 2;
  width: 260px;
  padding: 102px 0 0 38px;
}

.material-copy strong,
.side-copy strong {
  display: block;
  color: #f4f8fb;
  font-size: 3.2rem;
  font-weight: 600;
  line-height: 1;
}

.material-copy small,
.side-copy small {
  display: block;
  margin-top: 16px;
  color: #93a8bd;
  font-size: 1.18rem;
}

.material-metrics {
  margin-top: 36px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px 34px;
}

.material-metrics span,
.side-metrics span {
  display: grid;
  gap: 8px;
}

em {
  color: #93a8bd;
  font-size: 0.86rem;
  font-style: normal;
}

b {
  color: #f4f8fb;
  font-size: 1.2rem;
  font-weight: 600;
}

.hologram {
  position: absolute;
  inset: 0 0 0 236px;
  z-index: 1;
}

.side-materials {
  display: grid;
  gap: 24px;
}

.side-card {
  min-height: 203px;
  display: grid;
  grid-template-columns: minmax(170px, 0.8fr) minmax(170px, 1fr);
  gap: 18px;
  align-items: center;
  padding: 30px;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.side-surface {
  position: absolute;
  right: 14px;
  bottom: 12px;
  width: 48%;
  height: 54%;
  opacity: 0.38;
  transform: perspective(480px) rotateX(58deg) rotateZ(-11deg);
}

.side-surface::before {
  inset: 0;
  background:
    linear-gradient(135deg, transparent 0 48%, rgba(52, 214, 255, 0.34) 49%, transparent 50%),
    linear-gradient(45deg, transparent 0 48%, rgba(52, 214, 255, 0.22) 49%, transparent 50%);
  background-size: 24px 24px;
}

.side-surface::after {
  left: 42%;
  top: 42%;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(242, 195, 91, 0.4), transparent 64%);
}

.side-card:hover {
  border-color: rgba(52, 214, 255, 0.35);
  transform: translateY(-2px);
}

.side-copy {
  position: relative;
  z-index: 2;
}

.side-copy strong {
  font-size: 2.1rem;
}

.side-copy small {
  margin-top: 10px;
  font-size: 0.92rem;
}

.side-metrics {
  margin-top: 24px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

@media (max-width: 1120px) {
  .material-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .featured-material {
    min-height: 620px;
  }

  .material-copy {
    width: auto;
    padding-right: 26px;
  }

  .hologram {
    inset: 280px 0 0 0;
  }

  .side-card {
    grid-template-columns: 1fr;
  }
}
</style>
