<template>
  <section class="settings-guide" :class="{ compact }" aria-label="推荐设置与术语说明">
    <div><span>推荐设置</span><h4>{{ title }}</h4><p>{{ description }}</p></div>
    <details>
      <summary>为什么这些是高级设置？</summary>
      <dl><div v-for="[term, explanation] in plainLanguageTerms" :key="term"><dt>{{ term }}</dt><dd>{{ explanation }}</dd></div></dl>
    </details>
  </section>
</template>

<script setup>
import { plainLanguageTerms } from '../services/beginnerExperienceService.js'

defineProps({ title: String, description: String, compact: Boolean })
</script>

<style scoped>
.settings-guide{margin:0 0 24px;padding:18px 20px;border-left:3px solid var(--lz-accent);border-radius:0 var(--lz-radius-small) var(--lz-radius-small) 0;background:var(--lz-accent-soft)}.settings-guide span{color:var(--lz-accent-deep);font:700 .68rem var(--lz-mono);letter-spacing:.07em}.settings-guide h4{margin:7px 0 9px;font-size:1rem;line-height:var(--lz-title-leading)}.settings-guide p{margin:0;color:var(--lz-muted);font-size:.8rem;line-height:var(--lz-body-leading)}.settings-guide details{margin-top:13px;border-top:1px solid #cfe1d7}.settings-guide summary{padding-top:12px;color:var(--lz-accent-deep);cursor:pointer;font-weight:700;font-size:.8rem}.settings-guide dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:12px 0 0;background:var(--lz-line)}.settings-guide dl>div{padding:10px;background:#fff}.settings-guide dt{color:var(--lz-accent-deep);font:700 .7rem var(--lz-mono)}.settings-guide dd{margin:5px 0 0;color:var(--lz-muted);font-size:.74rem;line-height:1.6}@media(max-width:650px){.settings-guide dl{grid-template-columns:1fr}}
.settings-guide.compact{margin-bottom:18px;padding:14px 16px}.settings-guide.compact h4{font-size:.92rem}.settings-guide.compact details{display:none}
</style>
