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
.beginner-summary{border:1px solid #9eb58d;background:#edf4e8}.beginner-summary>header{padding:20px 22px;border-bottom:1px solid #c9d8c0}.beginner-summary header>span{color:#4b7430;font:700 .67rem ui-monospace,monospace;letter-spacing:.12em}.beginner-summary h3{margin:7px 0;font-size:1.35rem}.beginner-summary header p,.beginner-summary article p,.term-details>p{margin:0;color:#52634f;font-size:.78rem;line-height:1.6}.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#c9d8c0}.summary-grid article{min-height:142px;padding:18px;background:#f8fbf5;display:grid;align-content:start;gap:9px}.summary-grid span{color:#688060;font-size:.68rem}.summary-grid strong{font-size:.9rem;line-height:1.45;overflow-wrap:anywhere}.term-details{margin:0;padding:17px 22px;background:#f4f8f0}.term-details summary{color:#3f692c;cursor:pointer;font-weight:700;font-size:.82rem}.term-details>p{margin-top:12px}.term-details dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:14px 0 0;background:#d2dfca}.term-details dl>div{padding:12px;background:#fff}.term-details dt{color:#3e6430;font:700 .72rem ui-monospace,monospace}.term-details dd{margin:6px 0 0;color:#5a675e;font-size:.74rem;line-height:1.55}@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.beginner-summary>header,.term-details{padding:18px}.summary-grid,.term-details dl{grid-template-columns:1fr}}
.beginner-summary.compact{border-color:var(--lz-line);background:#f9faf7}.beginner-summary.compact>header{padding:18px 20px;border-color:var(--lz-line)}.beginner-summary.compact h3{font-size:1.1rem}.beginner-summary.compact .summary-grid{background:var(--lz-line)}.beginner-summary.compact .summary-grid article{min-height:106px;padding:15px;background:#fff}.beginner-summary.compact .term-details{padding:14px 20px;background:#f7f8f4}.beginner-summary.compact .term-details dl{background:var(--lz-line)}
</style>
