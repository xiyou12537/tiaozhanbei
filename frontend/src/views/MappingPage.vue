<template>
  <div class="mapping-page">
    <!-- 无分区数据时：引导提示 -->
    <div v-if="!shared.partitionResult" class="guide-banner">
      <div class="guide-icon">
        <el-icon :size="28"><WarningFilled /></el-icon>
      </div>
      <div class="guide-body">
        <h4>需要先完成电路分区</h4>
        <p>芯片映射功能依赖分区计算结果，请先在「电路分区」页面完成分区计算后再使用此功能。</p>
      </div>
      <el-button type="primary" @click="$router.push('/app/partition')">
        <el-icon><Grid /></el-icon>
        前往电路分区
      </el-button>
    </div>

    <!-- 主要内容：左右两列 -->
    <div class="mapping-grid" v-else>
      <!-- ===== 左列：拓扑设计 + 映射结果 ===== -->
      <div class="left-column">
        <!-- 拓扑设计 -->
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Edit /></el-icon></span>
            <span class="panel-title">芯片拓扑设计</span>
          </div>
          <div class="panel-body">
            <!-- 类型选择 -->
            <div class="topo-field">
              <label class="field-label">拓扑类型</label>
              <el-select v-model="topoType" style="width:100%" @change="onTopoTypeChange">
                <el-option v-for="t in topoTypes" :key="t.value" :value="t.value" :label="t.label" />
              </el-select>
            </div>

            <!-- 参数 -->
            <div class="topo-params" v-if="topoType !== 'custom'">
              <div class="param-row" v-if="['ring','star','linear','fully'].includes(topoType)">
                <label class="field-label">芯片数量</label>
                <el-input-number v-model="paramN" :min="2" :max="12" @change="generateTopo" controls-position="right" style="width:100%" />
              </div>
              <template v-if="topoType === 'grid'">
                <div class="param-row">
                  <label class="field-label">行 × 列</label>
                  <div class="param-inline">
                    <el-input-number v-model="paramR" :min="2" :max="5" @change="generateTopo" controls-position="right" size="small" />
                    <span class="param-sep">×</span>
                    <el-input-number v-model="paramC" :min="2" :max="5" @change="generateTopo" controls-position="right" size="small" />
                  </div>
                </div>
              </template>
            </div>

            <!-- 自定义连线 -->
            <div v-if="topoType === 'custom'" class="custom-matrix">
              <div class="custom-controls">
                <label class="field-label">芯片数</label>
                <el-input-number v-model="customN" :min="2" :max="8" size="small" @change="initCustomGrid" controls-position="right" />
                <span class="hint-text">点击格子连线 / 断线</span>
              </div>
              <div class="adj-matrix">
                <div class="adj-row adj-header">
                  <div class="adj-label"></div>
                  <div v-for="j in customN - 1" :key="'h' + j" class="adj-col-label">T{{ j + 1 }}</div>
                </div>
                <div v-for="i in customN - 1" :key="'r' + i" class="adj-row">
                  <div class="adj-row-label">T{{ i }}</div>
                  <div
                    v-for="j in customN - 1"
                    :key="'c' + i + '-' + j"
                    class="adj-cell"
                    :class="{ active: hasEdge(i - 1, j), disabled: j < i }"
                    @click="j >= i && toggleEdge(i - 1, j)"
                  >
                    <span v-if="j >= i && hasEdge(i - 1, j)">●</span>
                  </div>
                </div>
              </div>
              <p class="edge-list" v-if="customEdgesList.length">
                已连接：{{ customEdgesList.map(e => `T${e[0] + 1}-T${e[1] + 1}`).join(', ') }}
              </p>
            </div>

            <!-- 操作按钮 -->
            <div class="topo-actions">
              <el-button type="primary" @click="handleRun" :loading="mappingLoading" class="action-btn">
                <el-icon v-if="!mappingLoading"><CaretRight /></el-icon>
                计算最优映射
              </el-button>
              <el-button @click="handleQuickCompare" :disabled="!shared.taskId" class="action-btn secondary">
                <el-icon><Sort /></el-icon>
                一键对比常用拓扑
              </el-button>
            </div>

            <!-- 拓扑预览 -->
            <div class="topo-preview" v-if="targetEdges.length">
              <div class="preview-label">拓扑预览</div>
              <div ref="targetGraphRef" class="preview-graph"></div>
            </div>
          </div>
        </div>

        <!-- 映射结果 -->
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Finished /></el-icon></span>
            <span class="panel-title">映射结果</span>
            <el-tag v-if="shared.mapping?.valid" type="success" size="small" effect="light">已计算</el-tag>
          </div>
          <div class="panel-body" v-if="shared.mapping?.valid">
            <div class="cost-row">
              <div class="cost-item">
                <span class="cost-value">{{ shared.mapping.total_epr_cost ?? 0 }}</span>
                <span class="cost-label">EPR 代价</span>
              </div>
              <div class="cost-item">
                <span class="cost-value">{{ Math.round(shared.mapping.subgraph_cost ?? 0) }}</span>
                <span class="cost-label">子图代价</span>
              </div>
            </div>
            <el-table
              v-if="shared.mapping.mapping"
              :data="Object.entries(shared.mapping.mapping).sort()"
              size="small"
              stripe
              class="mapping-table"
            >
              <el-table-column label="芯片" width="80">
                <template #default="scope">
                  <el-tag size="small" type="success">{{ scope.row[0] }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="分区">
                <template #default="scope">
                  <el-tag size="small">{{ scope.row[1] }}</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="panel-body panel-placeholder" v-else>
            <p class="placeholder-text">设计拓扑后点击"计算最优映射"</p>
          </div>
        </div>
      </div>

      <!-- ===== 右列：可视化 ===== -->
      <div class="right-column">
        <!-- 映射可视化 -->
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Share /></el-icon></span>
            <span class="panel-title">映射可视化</span>
            <span class="panel-hint">绿色 = 已映射，灰色 = 未映射</span>
          </div>
          <div class="panel-body graph-body" v-if="shared.mapping?.valid && shared.edgeCosts">
            <div ref="overlayRef" class="graph-container"></div>
          </div>
          <div class="panel-body panel-placeholder" v-else>
            <div class="placeholder-icon">
              <el-icon :size="36"><Share /></el-icon>
            </div>
            <p class="placeholder-text">完成映射计算后，<br>可视化结果将在此渲染</p>
          </div>
        </div>

        <!-- 拓扑对比 -->
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><TrendCharts /></el-icon></span>
            <span class="panel-title">拓扑代价对比</span>
          </div>
          <div class="panel-body chart-body" v-if="shared.topoComparisons?.length > 1">
            <div ref="chartRef" class="chart-container"></div>
          </div>
          <div class="panel-body panel-placeholder" v-else>
            <p class="placeholder-text">点击"一键对比常用拓扑"查看对比结果</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import * as echarts from 'echarts'
import * as api from '../api'

const shared = inject('shared')

// ── 拓扑类型 ──
const topoTypes = [
  { value: 'ring', label: '环形 (Ring)' },
  { value: 'star', label: '星形 (Star)' },
  { value: 'linear', label: '线形 (Linear)' },
  { value: 'fully', label: '全连接 (Fully Connected)' },
  { value: 'grid', label: '网格 (Grid)' },
  { value: 'custom', label: '自定义连线' },
]

const topoType = ref('ring')
const paramN = ref(3)
const paramR = ref(2)
const paramC = ref(2)
const targetEdges = ref([])
const mappingLoading = ref(false)

// 自定义连线
const customN = ref(4)
const customEdgesList = ref([])

const targetGraphRef = ref(null)
const overlayRef = ref(null)
const chartRef = ref(null)
let targetNet = null
let overlayNet = null
let chart = null
let isMounted = true

// ── 参数化生成拓扑 ──
function generateTopo() {
  const edges = []
  const n = paramN.value
  switch (topoType.value) {
    case 'ring':
      for (let i = 0; i < n; i++) edges.push([i, (i + 1) % n])
      break
    case 'star':
      for (let i = 1; i < n; i++) edges.push([0, i])
      break
    case 'linear':
      for (let i = 0; i < n - 1; i++) edges.push([i, i + 1])
      break
    case 'fully':
      for (let i = 0; i < n; i++)
        for (let j = i + 1; j < n; j++) edges.push([i, j])
      break
    case 'grid': {
      const [r, c] = [paramR.value, paramC.value]
      for (let i = 0; i < r; i++)
        for (let j = 0; j < c; j++) {
          const id = i * c + j
          if (j < c - 1) edges.push([id, id + 1])
          if (i < r - 1) edges.push([id, id + c])
        }
      break
    }
    case 'custom':
      edges.push(...customEdgesList.value)
      break
  }
  targetEdges.value = edges.map(([s, t]) => ({ source: s, target: t }))
  shared.targetEdges = targetEdges.value
  nextTick(renderTargetGraph)
}

function onTopoTypeChange() {
  if (topoType.value === 'custom') initCustomGrid()
  else generateTopo()
}

// ── 自定义连线 ──
function initCustomGrid() {
  customEdgesList.value = []
  generateTopo()
}

function toggleEdge(a, b) {
  const existing = customEdgesList.value.findIndex(
    e => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a)
  )
  if (existing >= 0) customEdgesList.value.splice(existing, 1)
  else customEdgesList.value.push([a, b])
  generateTopo()
}

function hasEdge(a, b) {
  return customEdgesList.value.some(
    e => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a)
  )
}

// ── 映射计算 ──
async function handleRun() {
  if (!targetEdges.value.length) {
    ElMessage.warning('请先设计拓扑')
    return
  }
  mappingLoading.value = true
  shared.lastError = ''
  shared.currentStage = 'aggregating'
  shared.workflowStatus = 'running'
  shared.stageRuns = {
    ...shared.stageRuns,
    aggregating: 'running',
    completed: 'pending',
  }
  try {
    const { data } = await api.findMapping(shared.taskId, targetEdges.value)
    if (!isMounted) return
    shared.mapping = data
    if (data.valid) {
      shared.workflowStatus = 'completed'
      shared.currentStage = 'completed'
      shared.stageRuns = {
        ...shared.stageRuns,
        aggregating: 'success',
        completed: 'success',
      }
      ElMessage.success('映射计算完成')
    } else {
      shared.workflowStatus = 'failed'
      shared.currentStage = 'aggregating'
      shared.stageRuns = {
        ...shared.stageRuns,
        aggregating: 'failed',
        completed: 'pending',
      }
      shared.lastError = '未找到有效映射方案'
      ElMessage.warning('未找到有效映射方案')
    }
    await nextTick()
    renderOverlay()
  } catch (e) {
    shared.workflowStatus = 'failed'
    shared.currentStage = 'aggregating'
    shared.stageRuns = {
      ...shared.stageRuns,
      aggregating: 'failed',
      completed: 'pending',
    }
    shared.lastError = e.response?.data?.detail || e.message
    ElMessage.error('映射计算失败')
  } finally {
    mappingLoading.value = false
  }
  if (isMounted) await comparePresets()
}

async function handleQuickCompare() {
  await comparePresets()
}

const topoLabelMap = { ring: '环形', star: '星形', linear: '线形', fully: '全连接' }
const topoCompareNames = ref([])

async function comparePresets() {
  if (!shared.taskId) return
  const comp = {}
  const presets = {
    ring: { N: shared.partitionResult.num_partitions },
    star: { N: shared.partitionResult.num_partitions },
    linear: { N: shared.partitionResult.num_partitions },
  }
  const order = []
  for (const [name, cfg] of Object.entries(presets)) {
    const n = Math.min(cfg.N, 6)
    const edges = []
    if (name === 'ring')
      for (let i = 0; i < n; i++) edges.push({ source: i, target: (i + 1) % n })
    else if (name === 'star')
      for (let i = 1; i < n; i++) edges.push({ source: 0, target: i })
    else if (name === 'linear')
      for (let i = 0; i < n - 1; i++) edges.push({ source: i, target: i + 1 })
    const label = topoLabelMap[name]
    comp[label] = edges
    order.push(label)
  }
  comp['当前拓扑'] = targetEdges.value
  order.push('当前拓扑')
  topoCompareNames.value = order
  try {
    const { data } = await api.compareTopologies(shared.taskId, comp)
    shared.topoComparisons = data.comparisons
    await nextTick()
    renderChart()
  } catch {
    shared.topoComparisons = null
  }
}

// ── 可视化 ──
function destroyNet(net) {
  if (net) {
    try { net.destroy() } catch {}
  }
}

function renderTargetGraph() {
  try {
    if (!isMounted || !targetGraphRef.value || !targetEdges.value.length) return
    const chips = [
      ...new Set(targetEdges.value.flatMap(e => [e.source, e.target])),
    ].sort()
    const nodes = chips.map(c => ({
      id: `T${c + 1}`,
      label: `芯片${c + 1}`,
      size: 22,
      font: { size: 13 },
      color: { background: '#91cc75', border: '#333' },
    }))
    const edges = targetEdges.value.map(e => ({
      from: `T${e.source + 1}`,
      to: `T${e.target + 1}`,
      color: '#666',
      width: 2,
    }))
    destroyNet(targetNet)
    targetNet = null
    if (targetGraphRef.value) {
      targetNet = new Network(
        targetGraphRef.value,
        { nodes: new DataSet(nodes), edges: new DataSet(edges) },
        {
          physics: { solver: 'barnesHut', stabilization: { iterations: 40 } },
          edges: { smooth: { type: 'continuous' } },
        }
      )
    }
  } catch (e) {
    console.warn('renderTargetGraph:', e)
  }
}

function renderOverlay() {
  try {
    if (
      !isMounted ||
      !overlayRef.value ||
      !shared.edgeCosts ||
      !shared.mapping?.valid
    )
      return
    const costs = shared.edgeCosts
    const mapping = shared.mapping.mapping
    const allParts = new Set()
    Object.keys(costs).forEach(k => {
      const [a, b] = k.split('-')
      if (a) allParts.add(a)
      if (b) allParts.add(b)
    })
    const mappedParts = new Set(Object.values(mapping))
    const mappedEdges = new Set()
    targetEdges.value.forEach(e => {
      const p1 = mapping[`T${e.source + 1}`]
      const p2 = mapping[`T${e.target + 1}`]
      if (p1 && p2) {
        mappedEdges.add(`${p1}-${p2}`)
        mappedEdges.add(`${p2}-${p1}`)
      }
    })
    const nodes = [...allParts].map(pid => ({
      id: pid,
      label: pid + (mappedParts.has(pid) ? ' ✓' : ''),
      size: mappedParts.has(pid) ? 28 : 20,
      font: { size: 13 },
      color: mappedParts.has(pid)
        ? { background: '#52c41a', border: '#237804' }
        : { background: '#d9d9d9', border: '#999' },
    }))
    const visEdges = Object.entries(costs).map(([key, w]) => {
      const [from, to] = key.split('-')
      const m = mappedEdges.has(key)
      return {
        from,
        to,
        label: String(w),
        width: m ? 4 : Math.max(1, Math.min(6, w / 8)),
        font: { size: 12, strokeWidth: 2, strokeColor: '#fff' },
        color: m
          ? { color: '#52c41a', highlight: '#73d13d' }
          : { color: '#ccc', highlight: '#aaa' },
      }
    })
    destroyNet(overlayNet)
    overlayNet = null
    if (overlayRef.value) {
      overlayNet = new Network(
        overlayRef.value,
        { nodes: new DataSet(nodes), edges: new DataSet(visEdges) },
        {
          physics: { solver: 'forceAtlas2Based', stabilization: { iterations: 60 } },
          edges: { smooth: { type: 'continuous' } },
        }
      )
    }
  } catch (e) {
    console.warn('renderOverlay:', e)
  }
}

function renderChart() {
  try {
    if (!isMounted || !chartRef.value || !shared.topoComparisons?.length) return
    if (!chart) chart = echarts.init(chartRef.value)
    const valid = shared.topoComparisons.filter(c => c.valid)
    const names =
      topoCompareNames.value.length === valid.length
        ? topoCompareNames.value
        : valid.map((_, i) => `拓扑${i + 1}`)
    const colors = [
      '#36cfc9', '#597ef7', '#ffc53d', '#ff7a45',
      '#73d13d', '#ff85c0', '#9254de',
    ]
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: {
        type: 'category',
        data: names,
        axisLabel: {
          rotate: names.length > 4 ? 30 : 0,
          fontSize: 11,
          interval: 0,
        },
      },
      yAxis: {
        type: 'value',
        name: 'EPR 代价',
        nameTextStyle: { fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          data: valid.map(c => c.total_epr_cost),
          barMaxWidth: 50,
          itemStyle: {
            color: p => colors[p.dataIndex % colors.length],
            borderRadius: [4, 4, 0, 0],
          },
          label: { show: true, position: 'top', fontSize: 10 },
        },
      ],
      grid: {
        top: 25,
        right: 20,
        bottom: names.length > 4 ? 50 : 35,
        left: 70,
      },
    })
  } catch (e) {
    console.warn('renderChart:', e)
  }
}

// ── 生命周期 ──
onMounted(() => {
  isMounted = true
  generateTopo()
  if (shared.mapping?.valid) nextTick(renderOverlay)
  if (shared.topoComparisons?.length) nextTick(renderChart)
})

onUnmounted(() => {
  isMounted = false
  destroyNet(targetNet)
  targetNet = null
  destroyNet(overlayNet)
  overlayNet = null
  if (chart) {
    try { chart.dispose() } catch {}
    chart = null
  }
  if (targetGraphRef.value) targetGraphRef.value.innerHTML = ''
  if (overlayRef.value) overlayRef.value.innerHTML = ''
  if (chartRef.value) chartRef.value.innerHTML = ''
})
</script>

<style scoped>
/* ===== Page Layout ===== */
.mapping-page {
  max-width: 1500px;
}

/* ===== Guide Banner (no partition data) ===== */
.guide-banner {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 28px 32px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e8ecf1;
  margin-top: 40px;
}

.guide-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: #fff7e6;
  color: #fa8c16;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.guide-body {
  flex: 1;
}

.guide-body h4 {
  font-size: 1rem;
  color: #1a1a2e;
  margin: 0 0 4px;
}

.guide-body p {
  font-size: 0.82rem;
  color: #888;
  margin: 0;
}

/* ===== Mapping Grid ===== */
.mapping-grid {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 16px;
  align-items: start;
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Panel Card ===== */
.panel-card {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e8ecf1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.panel-card:hover {
  border-color: #d0d8e0;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  background: #fafbfc;
  border-bottom: 1px solid #f0f2f5;
  font-weight: 600;
  font-size: 0.9rem;
  color: #1a1a2e;
  flex-shrink: 0;
}

.panel-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #f0f2f5;
  color: #597ef7;
  flex-shrink: 0;
}

.panel-title {
  flex: 1;
}

.panel-hint {
  font-size: 0.7rem;
  font-weight: 400;
  color: #999;
}

.panel-body {
  padding: 18px;
  flex: 1;
}

.panel-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

.placeholder-icon {
  color: #d0d5dd;
  margin-bottom: 10px;
}

.placeholder-text {
  font-size: 0.82rem;
  color: #aaa;
  text-align: center;
}

/* ===== Form Elements ===== */
.topo-field {
  margin-bottom: 14px;
}

.field-label {
  display: block;
  font-size: 0.75rem;
  color: #666;
  margin-bottom: 4px;
  font-weight: 500;
}

.topo-params .param-row {
  margin-bottom: 12px;
}

.param-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-sep {
  color: #999;
  font-weight: 500;
}

/* ===== Custom Matrix ===== */
.custom-matrix {
  margin-bottom: 14px;
}

.custom-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.hint-text {
  font-size: 0.7rem;
  color: #aaa;
}

.adj-matrix {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 4px;
}

.adj-row {
  display: flex;
  align-items: center;
  gap: 2px;
}

.adj-label,
.adj-col-label,
.adj-row-label {
  font-size: 0.7rem;
  color: #888;
  text-align: center;
}

.adj-col-label {
  width: 32px;
}

.adj-row-label {
  width: 24px;
  text-align: right;
  padding-right: 4px;
}

.adj-header .adj-label {
  width: 28px;
}

.adj-cell {
  width: 32px;
  height: 32px;
  border: 1px solid #ddd;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 0.8rem;
  transition: 0.15s;
  background: #fafafa;
  user-select: none;
}

.adj-cell:hover:not(.disabled) {
  background: #e6f7ff;
  border-color: #91d5ff;
}

.adj-cell.active {
  background: #36cfc9;
  border-color: #08979c;
  color: #fff;
  font-weight: bold;
}

.adj-cell.disabled {
  background: #f5f5f5;
  border-color: #eee;
  cursor: default;
  color: transparent;
}

.edge-list {
  font-size: 0.7rem;
  color: #aaa;
  margin-top: 4px;
}

/* ===== Topo Actions ===== */
.topo-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.action-btn {
  width: 100%;
  border-radius: 8px;
  font-weight: 500;
}

.action-btn.secondary {
  border-color: #d9d9d9;
  color: #666;
}

/* ===== Topo Preview ===== */
.topo-preview {
  border-top: 1px solid #f0f2f5;
  padding-top: 14px;
}

.preview-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.preview-graph {
  height: 180px;
  border: 1px solid #f0f2f5;
  border-radius: 6px;
  background: #fafbfc;
}

/* ===== Mapping Result ===== */
.cost-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.cost-item {
  text-align: center;
  padding: 14px 8px;
  background: linear-gradient(135deg, #fafbfc, #f5f7fa);
  border-radius: 8px;
  border: 1px solid #e8ecf1;
}

.cost-value {
  display: block;
  font-size: 1.3rem;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.cost-label {
  display: block;
  font-size: 0.7rem;
  color: #999;
  margin-top: 2px;
}

.mapping-table {
  margin-top: 8px;
}

/* ===== Graph Containers ===== */
.graph-body {
  padding: 10px;
}

.graph-container {
  width: 100%;
  height: 420px;
  border: 1px solid #f0f2f5;
  border-radius: 6px;
  background: #fafbfc;
}

.chart-body {
  padding: 10px;
}

.chart-container {
  width: 100%;
  height: 280px;
}

/* ===== Responsive ===== */
@media (max-width: 1200px) {
  .mapping-grid {
    grid-template-columns: 1fr;
  }
}
</style>
