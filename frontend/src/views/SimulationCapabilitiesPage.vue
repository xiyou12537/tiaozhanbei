<template>
  <div class="capability-page">
    <header class="capability-hero">
      <div><span class="page-kicker">SERVER-SOURCED CONTRACT</span><h2>模拟能力说明</h2><p>页面只展示服务端当前声明的能力，不把前端预设当作计算边界。</p></div>
      <div class="boundary-badges"><el-tag>模拟器</el-tag><el-tag type="info">虚拟节点逻辑分布式模拟</el-tag><el-tag type="warning">非真实 QPU</el-tag></div>
    </header>

    <el-alert v-if="error" type="error" :closable="false" show-icon title="能力接口暂不可用">
      <p>{{ error }}</p><el-button size="small" :loading="loading" @click="loadCapabilities">重试</el-button>
    </el-alert>

    <section v-loading="loading" class="capability-contract">
      <div class="contract-lead"><span>CONTRACT</span><strong>{{ capabilities?.contract_version || '—' }}</strong><p>GET /api/molecule-workflows/capabilities</p></div>
      <div class="contract-grid">
        <article><span>支持元素</span><strong>{{ joinValues(capabilities?.supported_elements) }}</strong></article>
        <article><span>支持基组</span><strong>{{ joinValues(capabilities?.supported_basis_sets) }}</strong></article>
        <article><span>最大原子数</span><strong>{{ value(capabilities?.max_atom_count) }}</strong></article>
        <article><span>最大映射 Qubits</span><strong>{{ value(capabilities?.max_mapped_qubits) }}</strong></article>
        <article><span>分区数量</span><strong>{{ joinValues(capabilities?.partition_counts) }}</strong></article>
        <article><span>分区策略</span><strong>{{ joinValues(capabilities?.partition_strategies) }}</strong></article>
        <article><span>初始布局</span><strong>{{ joinValues(capabilities?.initial_layout_methods) }}</strong></article>
        <article><span>路由方法</span><strong>{{ joinValues(capabilities?.routing_methods) }}</strong></article>
      </div>
    </section>

    <section class="topology-explanation">
      <header><span class="page-kicker">TOPOLOGY SEMANTICS</span><h3>两类拓扑，两个作用域</h3></header>
      <div class="topology-cards">
        <article><span>01 / INTER-QPU</span><h4>分区间虚拟 QPU 拓扑</h4><p>描述分区所在虚拟节点之间是否相连，用于映射代价和跨分区通信；不代表芯片内部物理连线。</p><strong>{{ joinValues(capabilities?.inter_qpu_topologies) }}</strong></article>
        <article><span>02 / INTRA-CHIP</span><h4>芯片内部物理耦合拓扑</h4><p>每颗虚拟 QPU 独立配置物理量子比特及耦合边，用于 logical-to-physical 布局和 SWAP 路由。</p><strong>{{ joinValues(capabilities?.physical_coupling_maps) }}</strong></article>
      </div>
    </section>

    <section class="execution-boundary"><div><span class="page-kicker">EXECUTION MODE</span><h3>{{ joinValues(capabilities?.execution_modes) }}</h3></div><p>该模式是虚拟节点逻辑分布式模拟。即使 Workflow 执行完成，也不得解释为真实量子芯片执行；is_real_qpu=false 时始终标记“非真实 QPU”。</p></section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getMoleculeWorkflowCapabilities } from '../services/moleculeWorkflowService'

const capabilities = ref(null)
const loading = ref(false)
const error = ref('')
const value = input => input === null || input === undefined || input === '' ? '—' : String(input)
const joinValues = input => Array.isArray(input) && input.length ? input.join(' · ') : '—'

async function loadCapabilities() {
  loading.value = true
  error.value = ''
  try { capabilities.value = await getMoleculeWorkflowCapabilities() }
  catch (requestError) { error.value = requestError?.response?.status === 401 ? '登录状态已失效，请重新登录。' : '未能读取服务端能力声明，请稍后重试。' }
  finally { loading.value = false }
}

onMounted(loadCapabilities)
</script>

<style scoped>
.capability-page{display:grid;gap:24px}.capability-hero{min-height:190px;padding:34px;border:1px solid #c9cec7;display:flex;align-items:flex-end;justify-content:space-between;gap:30px;background:#e8ebe5}.page-kicker{color:#69766e;font:700 .68rem ui-monospace,monospace;letter-spacing:.12em}.capability-hero h2{margin:14px 0 10px;font-size:clamp(2rem,4vw,4.2rem);line-height:.95;letter-spacing:-.06em}.capability-hero p{margin:0;color:#657169}.boundary-badges{display:flex;flex-wrap:wrap;gap:8px}.capability-contract{display:grid;grid-template-columns:280px 1fr;border:1px solid #c9cec7;background:#fff}.contract-lead{padding:30px;border-right:1px solid #d7dbd4;display:grid;align-content:start;gap:12px;background:#17201d;color:#fff}.contract-lead span{color:#b5f04c;font:700 .65rem ui-monospace,monospace}.contract-lead strong{font-size:4rem;line-height:1}.contract-lead p{color:#829087;font:500 .66rem ui-monospace,monospace;overflow-wrap:anywhere}.contract-grid{display:grid;grid-template-columns:repeat(4,1fr)}.contract-grid article{min-height:130px;padding:24px;border-right:1px solid #e1e4df;border-bottom:1px solid #e1e4df;display:grid;align-content:space-between}.contract-grid span{color:#79837d;font-size:.72rem}.contract-grid strong{font:700 .78rem ui-monospace,monospace;overflow-wrap:anywhere}.topology-explanation{padding:36px;border:1px solid #c9cec7;background:#fff}.topology-explanation h3{margin:10px 0 28px;font-size:2rem}.topology-cards{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#cdd2cb}.topology-cards article{min-height:260px;padding:30px;background:#f5f6f2}.topology-cards article>span{color:#73994e;font:700 .67rem ui-monospace,monospace}.topology-cards h4{margin:24px 0 14px;font-size:1.12rem}.topology-cards p{max-width:560px;color:#626d66;line-height:1.75;font-size:.82rem}.topology-cards strong{display:block;margin-top:38px;font:700 .72rem ui-monospace,monospace}.execution-boundary{padding:34px;display:grid;grid-template-columns:.8fr 1.2fr;gap:40px;background:#17201d;color:#f3f5f0}.execution-boundary h3{margin-top:12px;color:#b5f04c;font:700 1.3rem ui-monospace,monospace}.execution-boundary p{margin:0;color:#a7b1aa;line-height:1.8;font-size:.84rem}@media(max-width:1000px){.contract-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.capability-hero{align-items:flex-start;flex-direction:column}.capability-contract{grid-template-columns:1fr}.contract-lead{border-right:0}.topology-cards,.execution-boundary{grid-template-columns:1fr}.topology-explanation{padding:22px}}
</style>
