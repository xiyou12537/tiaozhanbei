<template>
  <section class="circuit-legend" aria-label="粒子数守恒 VQE 门类型">
    <header><span>PARTICLE-CONSERVING CIRCUIT</span><strong>{{ ansatz || 'legacy / 未记录' }}</strong></header>
    <p>HF 初态、参数化电子激发、Pauli 演化、芯片内 SWAP 与跨 QPU CX 分别着色。</p>
    <div class="gate-list"><span v-for="gate in gates" :key="`${gate.label}-${gate.group}`" :class="gate.tone">{{ gate.label }}<small>{{ label(gate.group) }}</small></span></div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { circuitOperationMeta } from '../services/scientificValidationService.js'
const props = defineProps({ ansatz: String, qasm: String, routedPlan: Array })
const gates = computed(() => {
  const seen = new Set()
  const sources = []
  for (const item of props.routedPlan || []) sources.push(circuitOperationMeta(item.operation, item.scope))
  const qasmDirectives = new Set(['openqasm', 'include', 'qreg', 'creg', 'gate', 'measure', 'barrier'])
  for (const line of String(props.qasm || '').split('\n')) {
    const match = line.trim().match(/^([a-z][a-z0-9_]*)\b/i)
    if (match && !qasmDirectives.has(match[1].toLowerCase())) sources.push(circuitOperationMeta(match[1]))
  }
  return sources.filter(gate => gate.label !== '—' && !seen.has(`${gate.label}-${gate.group}`) && (seen.add(`${gate.label}-${gate.group}`) || true))
})
function label(group) { return ({ hf_initial_state: 'HF 初态制备', parameterized_excitation: '参数化电子激发', pauli_evolution: '纠缠 / Pauli 演化', routing_swap: '路由插入 SWAP', inter_qpu_cx: '跨 QPU CX', legacy_parameterized_gate: '旧版参数门', unknown_gate: '未知门（降级显示）' })[group] || group }
</script>

<style scoped>
.circuit-legend{padding:16px;border:1px solid #d3d9d2;background:#f7f8f5}.circuit-legend header{display:flex;gap:14px;justify-content:space-between;align-items:baseline}.circuit-legend header span{color:#667e50;font:700 .63rem ui-monospace,monospace;letter-spacing:.08em}.circuit-legend header strong{font:.72rem ui-monospace,monospace}.circuit-legend p{margin:9px 0;color:#667269;font-size:.74rem}.gate-list{display:flex;flex-wrap:wrap;gap:7px}.gate-list>span{padding:6px 8px;border:1px solid;color:#263128;font:700 .72rem ui-monospace,monospace}.gate-list small{margin-left:6px;font:600 .58rem sans-serif}.initial{border-color:#6f8b65!important;background:#e8f0e4}.parameter{border-color:#8c7d48!important;background:#f5efd9}.entanglement,.basis{border-color:#4d7869!important;background:#e5efeb}.routing{border-color:#a66245!important;background:#f8e9e1}.communication{border-color:#785d8a!important;background:#eee8f3}.legacy,.unknown{border-color:#9ca49d!important;background:#eff1ee}</style>
