<template>
  <span class="chemical-formula" :aria-label="labelText">
    <template v-for="(part, index) in parts" :key="`${part.value}-${index}`">
      <sub v-if="part.isSubscript">{{ part.value }}</sub>
      <span v-else>{{ part.value }}</span>
    </template>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  text: {
    type: [String, Number],
    required: true,
  },
})

const FORMULA_TOKEN_PATTERN = /([A-Z][a-z]?)(\d+|x)/g

const labelText = computed(() => String(props.text ?? ''))

const parts = computed(() => {
  const segments = []
  let cursor = 0
  const source = labelText.value

  for (const match of source.matchAll(FORMULA_TOKEN_PATTERN)) {
    const [fullText, elementSymbol, subscriptValue] = match
    const matchIndex = match.index ?? 0

    if (matchIndex > cursor) {
      segments.push({ value: source.slice(cursor, matchIndex), isSubscript: false })
    }

    segments.push({ value: elementSymbol, isSubscript: false })
    segments.push({ value: subscriptValue, isSubscript: true })
    cursor = matchIndex + fullText.length
  }

  if (cursor < source.length) {
    segments.push({ value: source.slice(cursor), isSubscript: false })
  }

  return segments.length ? segments : [{ value: source, isSubscript: false }]
})
</script>

<style scoped>
.chemical-formula {
  white-space: nowrap;
}

.chemical-formula sub {
  font-size: 0.58em;
  line-height: 0;
  vertical-align: sub;
}
</style>
