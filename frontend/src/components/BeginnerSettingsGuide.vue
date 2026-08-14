<template>
  <section class="settings-guide" aria-label="推荐设置与术语说明">
    <div><span>推荐设置</span><h4>{{ title }}</h4><p>{{ description }}</p></div>
    <details>
      <summary>为什么这些是高级设置？</summary>
      <dl><div v-for="[term, explanation] in plainLanguageTerms" :key="term"><dt>{{ term }}</dt><dd>{{ explanation }}</dd></div></dl>
    </details>
  </section>
</template>

<script setup>
import { plainLanguageTerms } from '../services/beginnerExperienceService.js'

defineProps({ title: String, description: String })
</script>

<style scoped>
.settings-guide{margin:0 0 24px;padding:18px 20px;border-left:3px solid #6f963f;background:#f1f6ed}.settings-guide span{color:#5b7f3c;font:700 .66rem ui-monospace,monospace;letter-spacing:.1em}.settings-guide h4{margin:7px 0;font-size:1rem}.settings-guide p{margin:0;color:#5d6a61;font-size:.78rem;line-height:1.6}.settings-guide details{margin-top:13px;border-top:1px solid #ccdbc3}.settings-guide summary{padding-top:12px;color:#42662f;cursor:pointer;font-weight:700;font-size:.78rem}.settings-guide dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;margin:12px 0 0;background:#d1ddc9}.settings-guide dl>div{padding:10px;background:#fff}.settings-guide dt{color:#41622e;font:700 .7rem ui-monospace,monospace}.settings-guide dd{margin:5px 0 0;color:#5b685f;font-size:.72rem;line-height:1.5}@media(max-width:650px){.settings-guide dl{grid-template-columns:1fr}}
</style>
