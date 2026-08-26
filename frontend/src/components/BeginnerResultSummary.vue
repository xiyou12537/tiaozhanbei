<template>
  <section class="beginner-summary" :class="{ compact }" :data-testid="`${kind}-beginner-summary`" aria-labelledby="beginner-summary-title">
    <header>
      <span>先看结论</span>
      <h3 id="beginner-summary-title">这项任务现在意味着什么？</h3>
      <p>以下是对后端真实状态的通俗说明；不替代下方完整专业证据。</p>
    </header>
    <div class="summary-grid">
      <article><span>任务是否完成</span><strong>{{ summary.status }}</strong><p>{{ summary.statusReason }}</p></article>
      <article><span>最重要结果</span><strong>{{ summary.keyResult }}</strong></article>
      <article><span>可信度 / 复核原因</span><strong>{{ summary.confidence }}</strong><p>{{ summary.confidenceReason }}</p></article>
      <article><span>推荐下一步</span><strong>{{ summary.next }}</strong></article>
    </div>
    <details class="term-details">
      <summary>看不懂术语？展开通俗说明和完整证据入口</summary>
      <p>下方的 Hamiltonian、VQE、科学验证、部署验证、分区与路由均为原始专业证据，数值没有在此处改写。</p>
      <dl><div v-for="[term, explanation] in plainLanguageTerms" :key="term"><dt>{{ term }}</dt><dd>{{ explanation }}</dd></div></dl>
    </details>
  </section>
</template>

<script setup>
import { plainLanguageTerms } from '../services/beginnerExperienceService.js'

defineProps({
  kind: { type: String, required: true },
  summary: { type: Object, required: true },
  compact: Boolean,
})
</script>

<style scoped>
.beginner-summary{border:1px solid #c6ddd1;border-radius:var(--lz-radius);overflow:hidden;background:var(--lz-accent-soft)}.beginner-summary>header{padding:22px 24px;border-bottom:1px solid #cfe1d7}.beginner-summary header>span{color:var(--lz-accent-deep);font:700 .7rem var(--lz-mono);letter-spacing:.07em}.beginner-summary h3{margin:8px 0 10px;font-size:1.35rem;line-height:var(--lz-title-leading)}.beginner-summary header p,.beginner-summary article p,.term-details>p{margin:0;color:var(--lz-muted);font-size:.8rem;line-height:var(--lz-body-leading)}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#d3e3da}.summary-grid article{min-height:142px;padding:20px;background:var(--lz-panel);display:grid;align-content:start;gap:10px}.summary-grid span{color:var(--lz-muted);font-size:.7rem}.summary-grid strong{font-size:.92rem;line-height:1.5;overflow-wrap:anywhere}.term-details{margin:0;padding:18px 24px;background:#f8fbf9}.term-details summary{color:var(--lz-accent-deep);cursor:pointer;font-weight:700;font-size:.84rem}.term-details>p{margin-top:12px}.term-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:14px 0 0;background:var(--lz-line)}.term-details dl>div{padding:12px;background:#fff}.term-details dt{color:var(--lz-accent-deep);font:700 .72rem var(--lz-mono)}.term-details dd{margin:6px 0 0;color:var(--lz-muted);font-size:.76rem;line-height:1.65}@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.beginner-summary>header,.term-details{padding:18px}.summary-grid,.term-details dl{grid-template-columns:1fr}}
.beginner-summary.compact{border-color:var(--lz-line);background:var(--lz-bg-soft)}.beginner-summary.compact>header{padding:18px 20px;border-color:var(--lz-line)}.beginner-summary.compact h3{font-size:1.1rem}.beginner-summary.compact .summary-grid{background:var(--lz-line)}.beginner-summary.compact .summary-grid article{min-height:106px;padding:16px;background:#fff}.beginner-summary.compact .term-details{padding:14px 20px;background:#f7f8f5}.beginner-summary.compact .term-details dl{background:var(--lz-line)}
</style>
