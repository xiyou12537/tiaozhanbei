<template>
  <div class="mapping-page">
    <div v-if="!shared.partitionResult" class="guide-banner">
      <div class="guide-icon">
        <el-icon :size="28"><WarningFilled /></el-icon>
      </div>
      <div class="guide-body">
        <h4>需要先完成电路分区</h4>
        <p>芯片映射依赖分区计算结果，请先在“电路分区”页完成分区计算，再使用此功能。</p>
      </div>
      <el-button type="primary" @click="$router.push('/app/partition')">
        <el-icon><Grid /></el-icon>
        前往电路分区
      </el-button>
    </div>

    <div v-else class="mapping-grid">
      <div class="left-column">
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Edit /></el-icon></span>
            <span class="panel-title">芯片拓扑设计</span>
          </div>
          <div class="panel-body">
            <div class="topo-field">
              <label class="field-label">拓扑类型</label>
              <el-select v-model="topoType" style="width: 100%" @change="onTopoTypeChange">
                <el-option v-for="type in topoTypes" :key="type.value" :value="type.value" :label="type.label" />
              </el-select>
            </div>

            <div v-if="topoType !== 'custom'" class="topo-params">
              <div v-if="['ring', 'star', 'linear', 'fully'].includes(topoType)" class="param-row">
                <label class="field-label">芯片数量</label>
                <el-input-number
                  v-model="paramN"
                  :min="2"
                  :max="12"
                  @change="generateTopo"
                  controls-position="right"
                  style="width: 100%"
                />
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

            <div v-if="topoType === 'custom'" class="custom-matrix">
              <div class="custom-controls">
                <label class="field-label">芯片数量</label>
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
              <p v-if="customEdgesList.length" class="edge-list">
                已连接：{{ customEdgesList.map(edge => `T${edge[0] + 1}-T${edge[1] + 1}`).join(', ') }}
              </p>
            </div>

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

            <div v-if="targetEdges.length" class="topo-preview">
              <div class="preview-label">拓扑预览</div>
              <div ref="targetGraphRef" class="preview-graph"></div>
            </div>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Finished /></el-icon></span>
            <span class="panel-title">映射结果</span>
            <el-tag v-if="shared.mapping?.valid" type="success" size="small" effect="light">已计算</el-tag>
          </div>
          <div v-if="shared.mapping?.valid" class="panel-body">
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
          <div v-else class="panel-body panel-placeholder">
            <p class="placeholder-text">设计拓扑后点击“计算最优映射”</p>
          </div>
        </div>
      </div>

      <div class="right-column">
        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><Share /></el-icon></span>
            <span class="panel-title">映射可视化</span>
            <span class="panel-hint">绿色 = 已映射，灰色 = 未映射</span>
          </div>
          <div v-if="shared.mapping?.valid && shared.edgeCosts" class="panel-body graph-body">
            <div ref="overlayRef" class="graph-container"></div>
          </div>
          <div v-else class="panel-body panel-placeholder">
            <div class="placeholder-icon">
              <el-icon :size="36"><Share /></el-icon>
            </div>
            <p class="placeholder-text">完成映射计算后，<br>可视化结果将在此渲染</p>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-header">
            <span class="panel-icon"><el-icon><TrendCharts /></el-icon></span>
            <span class="panel-title">拓扑代价对比</span>
          </div>
          <div v-if="shared.topoComparisons?.length > 1" class="panel-body chart-body">
            <div ref="chartRef" class="chart-container"></div>
          </div>
          <div v-else class="panel-body panel-placeholder">
            <p class="placeholder-text">点击“一键对比常用拓扑”查看结果</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const shared = inject('shared')

const topoTypes = [
  { value: 'ring', label: '环形 (Ring)' },
  { value: 'star', label: '星形 (Star)' },
  { value: 'linear', label: '线性 (Linear)' },
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
const customN = ref(4)
const customEdgesList = ref([])

const targetGraphRef = ref(null)
const overlayRef = ref(null)
const chartRef = ref(null)
let targetNet = null
let overlayNet = null
let chart = null
let isMounted = true
let visNetworkModule = null
let visDataModule = null
let echartsModule = null

async function loadVisModules() {
  if (!visNetworkModule) {
    visNetworkModule = await import('vis-network')
  }
  if (!visDataModule) {
    visDataModule = await import('vis-data')
  }
  return {
    Network: visNetworkModule.Network,
    DataSet: visDataModule.DataSet,
  }
}

async function loadEcharts() {
  if (!echartsModule) {
    echartsModule = await import('echarts')
  }
  return echartsModule
}

function generateTopo() {
  const edges = []
  const nodeCount = paramN.value

  switch (topoType.value) {
    case 'ring':
      for (let i = 0; i < nodeCount; i += 1) {
        edges.push([i, (i + 1) % nodeCount])
      }
      break
    case 'star':
      for (let i = 1; i < nodeCount; i += 1) {
        edges.push([0, i])
      }
      break
    case 'linear':
      for (let i = 0; i < nodeCount - 1; i += 1) {
        edges.push([i, i + 1])
      }
      break
    case 'fully':
      for (let i = 0; i < nodeCount; i += 1) {
        for (let j = i + 1; j < nodeCount; j += 1) {
          edges.push([i, j])
        }
      }
      break
    case 'grid': {
      const rows = paramR.value
      const cols = paramC.value
      for (let i = 0; i < rows; i += 1) {
        for (let j = 0; j < cols; j += 1) {
          const id = i * cols + j
          if (j < cols - 1) edges.push([id, id + 1])
          if (i < rows - 1) edges.push([id, id + cols])
        }
      }
      break
    }
    case 'custom':
      edges.push(...customEdgesList.value)
      break
    default:
      break
  }

  targetEdges.value = edges.map(([source, target]) => ({ source, target }))
  shared.targetEdges = targetEdges.value
  nextTick(() => { void renderTargetGraph() })
}

function onTopoTypeChange() {
  if (topoType.value === 'custom') {
    initCustomGrid()
    return
  }
  generateTopo()
}

function initCustomGrid() {
  customEdgesList.value = []
  generateTopo()
}

function toggleEdge(a, b) {
  const existingIndex = customEdgesList.value.findIndex(
    edge => (edge[0] === a && edge[1] === b) || (edge[0] === b && edge[1] === a)
  )
  if (existingIndex >= 0) {
    customEdgesList.value.splice(existingIndex, 1)
  } else {
    customEdgesList.value.push([a, b])
  }
  generateTopo()
}

function hasEdge(a, b) {
  return customEdgesList.value.some(
    edge => (edge[0] === a && edge[1] === b) || (edge[0] === b && edge[1] === a)
  )
}

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
    await renderOverlay()
  } catch (error) {
    shared.workflowStatus = 'failed'
    shared.currentStage = 'aggregating'
    shared.stageRuns = {
      ...shared.stageRuns,
      aggregating: 'failed',
      completed: 'pending',
    }
    shared.lastError = error.response?.data?.detail || error.message
    ElMessage.error('映射计算失败')
  } finally {
    mappingLoading.value = false
  }

  if (isMounted) {
    await comparePresets()
  }
}

async function handleQuickCompare() {
  await comparePresets()
}

const topoLabelMap = {
  ring: '环形',
  star: '星形',
  linear: '线性',
  fully: '全连接',
}
const topoCompareNames = ref([])

async function comparePresets() {
  if (!shared.taskId || !shared.partitionResult) return

  const comparisons = {}
  const presets = {
    ring: { count: shared.partitionResult.num_partitions },
    star: { count: shared.partitionResult.num_partitions },
    linear: { count: shared.partitionResult.num_partitions },
  }
  const order = []

  for (const [name, config] of Object.entries(presets)) {
    const limitedCount = Math.min(config.count, 6)
    const edges = []
    if (name === 'ring') {
      for (let i = 0; i < limitedCount; i += 1) {
        edges.push({ source: i, target: (i + 1) % limitedCount })
      }
    } else if (name === 'star') {
      for (let i = 1; i < limitedCount; i += 1) {
        edges.push({ source: 0, target: i })
      }
    } else if (name === 'linear') {
      for (let i = 0; i < limitedCount - 1; i += 1) {
        edges.push({ source: i, target: i + 1 })
      }
    }

    const label = topoLabelMap[name]
    comparisons[label] = edges
    order.push(label)
  }

  comparisons['当前拓扑'] = targetEdges.value
  order.push('当前拓扑')
  topoCompareNames.value = order

  try {
    const { data } = await api.compareTopologies(shared.taskId, comparisons)
    shared.topoComparisons = data.comparisons
    await nextTick()
    await renderChart()
  } catch {
    shared.topoComparisons = null
  }
}

function destroyNet(networkInstance) {
  if (!networkInstance) return
  try {
    networkInstance.destroy()
  } catch {
    // vis-network may already be disposed
  }
}

async function renderTargetGraph() {
  try {
    if (!isMounted || !targetGraphRef.value || !targetEdges.value.length) return
    const { Network, DataSet } = await loadVisModules()
    if (!isMounted || !targetGraphRef.value) return

    const chips = [...new Set(targetEdges.value.flatMap(edge => [edge.source, edge.target]))].sort()
    const nodes = chips.map(chip => ({
      id: `T${chip + 1}`,
      label: `芯片${chip + 1}`,
      size: 22,
      font: { size: 13 },
      color: { background: '#91cc75', border: '#333' },
    }))
    const edges = targetEdges.value.map(edge => ({
      from: `T${edge.source + 1}`,
      to: `T${edge.target + 1}`,
      color: '#666',
      width: 2,
    }))

    destroyNet(targetNet)
    targetNet = new Network(
      targetGraphRef.value,
      { nodes: new DataSet(nodes), edges: new DataSet(edges) },
      {
        physics: { solver: 'barnesHut', stabilization: { iterations: 40 } },
        edges: { smooth: { type: 'continuous' } },
      }
    )
  } catch (error) {
    shared.lastError = shared.lastError || error.message
  }
}

async function renderOverlay() {
  try {
    if (!isMounted || !overlayRef.value || !shared.edgeCosts || !shared.mapping?.valid) return
    const { Network, DataSet } = await loadVisModules()
    if (!isMounted || !overlayRef.value) return

    const costs = shared.edgeCosts
    const mapping = shared.mapping.mapping
    const allParts = new Set()

    Object.keys(costs).forEach(key => {
      const [from, to] = key.split('-')
      if (from) allParts.add(from)
      if (to) allParts.add(to)
    })

    const mappedParts = new Set(Object.values(mapping))
    const mappedEdges = new Set()
    targetEdges.value.forEach(edge => {
      const partA = mapping[`T${edge.source + 1}`]
      const partB = mapping[`T${edge.target + 1}`]
      if (!partA || !partB) return
      mappedEdges.add(`${partA}-${partB}`)
      mappedEdges.add(`${partB}-${partA}`)
    })

    const nodes = [...allParts].map(partitionId => ({
      id: partitionId,
      label: partitionId + (mappedParts.has(partitionId) ? ' ✓' : ''),
      size: mappedParts.has(partitionId) ? 28 : 20,
      font: { size: 13 },
      color: mappedParts.has(partitionId)
        ? { background: '#52c41a', border: '#237804' }
        : { background: '#d9d9d9', border: '#999' },
    }))

    const visEdges = Object.entries(costs).map(([key, weight]) => {
      const [from, to] = key.split('-')
      const isMapped = mappedEdges.has(key)
      return {
        from,
        to,
        label: String(weight),
        width: isMapped ? 4 : Math.max(1, Math.min(6, weight / 8)),
        font: { size: 12, strokeWidth: 2, strokeColor: '#fff' },
        color: isMapped
          ? { color: '#52c41a', highlight: '#73d13d' }
          : { color: '#ccc', highlight: '#aaa' },
      }
    })

    destroyNet(overlayNet)
    overlayNet = new Network(
      overlayRef.value,
      { nodes: new DataSet(nodes), edges: new DataSet(visEdges) },
      {
        physics: { solver: 'forceAtlas2Based', stabilization: { iterations: 60 } },
        edges: { smooth: { type: 'continuous' } },
      }
    )
  } catch (error) {
    shared.lastError = shared.lastError || error.message
  }
}

async function renderChart() {
  try {
    if (!isMounted || !chartRef.value || !shared.topoComparisons?.length) return
    const echarts = await loadEcharts()
    if (!isMounted || !chartRef.value) return

    if (!chart) {
      chart = echarts.init(chartRef.value)
    }

    const validComparisons = shared.topoComparisons.filter(item => item.valid)
    const names =
      topoCompareNames.value.length === validComparisons.length
        ? topoCompareNames.value
        : validComparisons.map((_, index) => `拓扑${index + 1}`)
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
          data: validComparisons.map(item => item.total_epr_cost),
          barMaxWidth: 50,
          itemStyle: {
            color: params => colors[params.dataIndex % colors.length],
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
  } catch (error) {
    shared.lastError = shared.lastError || error.message
  }
}

onMounted(() => {
  isMounted = true
  generateTopo()
  if (shared.mapping?.valid) nextTick(() => { void renderOverlay() })
  if (shared.topoComparisons?.length) nextTick(() => { void renderChart() })
})

onUnmounted(() => {
  isMounted = false
  destroyNet(targetNet)
  targetNet = null
  destroyNet(overlayNet)
  overlayNet = null
  if (chart) {
    try {
      chart.dispose()
    } catch {
      // echarts instance may already be disposed
    }
    chart = null
  }
  if (targetGraphRef.value) targetGraphRef.value.innerHTML = ''
  if (overlayRef.value) overlayRef.value.innerHTML = ''
  if (chartRef.value) chartRef.value.innerHTML = ''
})
</script>

<style scoped>
.mapping-page {
  max-width: 1500px;
}

.guide-banner {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 28px 32px;
  background: linear-gradient(180deg, #ffffff, #f9fbff);
  border-radius: 16px;
  border: 1px solid #e6ebf2;
  margin-top: 40px;
}

.guide-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(180deg, #fff7eb, #ffffff);
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
  color: #667085;
  margin: 0;
}

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

.panel-card {
  background: linear-gradient(180deg, #ffffff, #f9fbff);
  border-radius: 16px;
  border: 1px solid #e6ebf2;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.2s;
}

.panel-card:hover {
  border-color: #d7e3f3;
  box-shadow: 0 10px 24px rgba(15, 23, 40, 0.05);
  transform: translateY(-1px);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  background: #f7faff;
  border-bottom: 1px solid #edf1f6;
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
  border-radius: 8px;
  background: #edf4ff;
  color: #2456b8;
  flex-shrink: 0;
}

.panel-title {
  flex: 1;
}

.panel-hint {
  font-size: 0.7rem;
  font-weight: 400;
  color: #98a2b3;
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
  border: 1px dashed #d9e3f0;
  border-radius: 12px;
  background: #fbfcfe;
}

.placeholder-icon {
  color: #b8c2cf;
  margin-bottom: 10px;
}

.placeholder-text {
  font-size: 0.82rem;
  color: #98a2b3;
  text-align: center;
}

.topo-field {
  margin-bottom: 14px;
}

.field-label {
  display: block;
  font-size: 0.75rem;
  color: #667085;
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
  color: #98a2b3;
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
  color: #667085;
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
  border: 1px solid #d7e3f3;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 0.8rem;
  transition: 0.15s;
  background: #fafcff;
  user-select: none;
}

.adj-cell:hover:not(.disabled) {
  background: #eef6ff;
  border-color: #9fcbff;
}

.adj-cell.active {
  background: linear-gradient(135deg, #18baa9, #377dff);
  border-color: transparent;
  color: #fff;
  font-weight: 700;
}

.adj-cell.disabled {
  background: #f5f5f5;
  border-color: #eee;
  cursor: default;
  color: transparent;
}

.edge-list {
  font-size: 0.7rem;
  color: #98a2b3;
  margin-top: 4px;
}

.topo-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.action-btn {
  width: 100%;
  border-radius: 10px;
  font-weight: 600;
  height: 40px;
}

.action-btn.secondary {
  border-color: #d7e3f3;
  color: #2456b8;
  background: #f7fbff;
}

.topo-preview {
  border-top: 1px solid #f0f2f5;
  padding-top: 14px;
}

.preview-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #667085;
  margin-bottom: 8px;
}

.preview-graph {
  height: 180px;
  border: 1px solid #e6ebf2;
  border-radius: 12px;
  background: radial-gradient(circle at top, rgba(55, 125, 255, 0.06), transparent 40%), #f8fbff;
}

.cost-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.cost-item {
  text-align: center;
  padding: 14px 8px;
  background: linear-gradient(180deg, #ffffff, #f7fbff);
  border-radius: 12px;
  border: 1px solid #e6ebf2;
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
  color: #98a2b3;
  margin-top: 2px;
}

.mapping-table {
  margin-top: 8px;
}

.graph-body {
  padding: 10px;
}

.graph-container {
  width: 100%;
  height: 420px;
  border: 1px solid #e6ebf2;
  border-radius: 12px;
  background: radial-gradient(circle at top, rgba(55, 125, 255, 0.06), transparent 40%), #f8fbff;
}

.chart-body {
  padding: 10px;
}

.chart-container {
  width: 100%;
  height: 280px;
  border-radius: 12px;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper),
:deep(.el-input-number),
:deep(.el-table) {
  border-radius: 12px;
}

:deep(.el-table) {
  --el-table-border-color: #e6ebf2;
  --el-table-header-bg-color: #f7faff;
  --el-table-row-hover-bg-color: #f8fbff;
  overflow: hidden;
}

:deep(.el-button--primary.action-btn) {
  background: linear-gradient(135deg, #18baa9, #377dff);
  border: none;
}

@media (max-width: 1200px) {
  .mapping-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .guide-banner {
    flex-direction: column;
    align-items: flex-start;
    padding: 24px;
  }

  .custom-controls {
    flex-wrap: wrap;
  }

  .cost-row {
    grid-template-columns: 1fr;
  }
}
</style>
