<template>
  <div class="partition-page">
    <div class="top-panels">
      <div class="panel-card">
        <div class="panel-header">
          <span class="panel-icon"><el-icon><UploadFilled /></el-icon></span>
          <span class="panel-title">上传 QASM 电路</span>
        </div>
        <div class="panel-body">
          <el-upload
            class="upload-area"
            drag
            :auto-upload="false"
            :on-change="handleFile"
            accept=".qasm,.txt"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">
              <span>将 .qasm 文件拖到此处</span>
              <em>或点击选择文件</em>
            </div>
          </el-upload>
          <div class="divider-text">
            <span>或直接粘贴内容</span>
          </div>
          <el-input
            v-model="qasmText"
            type="textarea"
            :rows="5"
            placeholder="在此粘贴 QASM 电路描述..."
            class="qasm-input"
          />
          <el-button
            type="primary"
            @click="handleUpload"
            :disabled="!qasmText.trim()"
            :loading="uploading"
            class="action-btn"
          >
            <el-icon v-if="!uploading"><Pointer /></el-icon>
            解析电路
          </el-button>
        </div>
      </div>

      <div class="panel-card">
        <div class="panel-header">
          <span class="panel-icon"><el-icon><InfoFilled /></el-icon></span>
          <span class="panel-title">电路信息</span>
          <el-tag v-if="shared.circuit" type="success" size="small" effect="light">已解析</el-tag>
          <el-tag v-else size="small" effect="light" style="opacity: 0.5">等待上传</el-tag>
        </div>
        <div v-if="shared.circuit" class="panel-body">
          <div class="stat-grid">
            <div class="stat-item">
              <span class="stat-value">{{ shared.circuit.num_qubits }}</span>
              <span class="stat-label">量子比特数</span>
            </div>
            <div class="stat-item">
              <span class="stat-value">{{ shared.circuit.total_gates }}</span>
              <span class="stat-label">总门数</span>
            </div>
            <div class="stat-item highlight">
              <span class="stat-value">{{ shared.circuit.multi_qubit_gates }}</span>
              <span class="stat-label">多比特门</span>
            </div>
            <div class="stat-item">
              <span class="stat-value mono">{{ shared.circuit.circuit_id?.slice(0, 8) }}</span>
              <span class="stat-label">电路 ID</span>
            </div>
          </div>
          <el-divider style="margin: 12px 0" />
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="量子比特数">{{ shared.circuit.num_qubits }}</el-descriptions-item>
            <el-descriptions-item label="总门数">{{ shared.circuit.total_gates }}</el-descriptions-item>
            <el-descriptions-item label="多比特门">
              <el-tag type="warning" size="small">{{ shared.circuit.multi_qubit_gates }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <div v-else class="panel-body panel-placeholder">
          <div class="placeholder-icon">
            <el-icon :size="36"><Document /></el-icon>
          </div>
          <p class="placeholder-text">
            上传电路文件或粘贴 QASM 内容后，<br>解析结果将在此显示
          </p>
        </div>
      </div>

      <div class="panel-card">
        <div class="panel-header">
          <span class="panel-icon"><el-icon><Setting /></el-icon></span>
          <span class="panel-title">分区参数</span>
        </div>
        <div class="panel-body">
          <el-form :model="params" label-position="top" size="small" class="param-form">
            <div class="param-row">
              <el-form-item label="分区数 k">
                <el-input-number
                  v-model="params.num_partitions"
                  :min="1"
                  :max="20"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item label="最大不均衡度">
                <el-input-number
                  v-model="params.max_imbalance"
                  :min="0"
                  :max="20"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
            </div>
            <div class="param-row">
              <el-form-item label="b1 (权重 1)">
                <el-slider v-model="params.b1" :min="1" :max="30" :step="0.5" show-input :show-input-controls="false" />
              </el-form-item>
            </div>
            <div class="param-row">
              <el-form-item label="b2 (权重 2)">
                <el-slider v-model="params.b2" :min="1" :max="30" :step="0.5" show-input :show-input-controls="false" />
              </el-form-item>
            </div>
            <div class="param-row">
              <el-form-item label="alpha (衰减因子)">
                <el-slider v-model="params.alpha" :min="0.5" :max="10" :step="0.5" show-input :show-input-controls="false" />
              </el-form-item>
            </div>
            <div class="param-row">
              <el-form-item label="beta (正则项)">
                <el-slider v-model="params.beta" :min="0.5" :max="10" :step="0.5" show-input :show-input-controls="false" />
              </el-form-item>
            </div>
            <div class="param-row param-toggles">
              <el-form-item label="网格搜索">
                <el-switch v-model="params.search" />
              </el-form-item>
            </div>
            <el-button
              type="primary"
              @click="handleRun"
              :loading="loading"
              :disabled="!shared.circuit"
              class="action-btn"
            >
              <el-icon v-if="!loading"><CaretRight /></el-icon>
              {{ loading ? '计算中...' : '开始分区计算' }}
            </el-button>
          </el-form>

          <div v-if="loading" class="progress-area">
            <el-progress
              :percentage="progress"
              :status="progress === 100 ? 'success' : ''"
              :stroke-width="6"
            />
            <p class="progress-msg">{{ statusMsg }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="results-section">
      <div class="panel-card result-data">
        <div class="panel-header">
          <span class="panel-icon"><el-icon><DataAnalysis /></el-icon></span>
          <span class="panel-title">分区结果</span>
          <el-tag v-if="shared.partitionResult" type="success" size="small" effect="light">已完成</el-tag>
        </div>
        <div v-if="shared.partitionResult" class="panel-body">
          <div class="stat-row">
            <div class="stat-card">
              <span class="stat-card-value">{{ shared.partitionResult.teleportations }}</span>
              <span class="stat-card-label">传态次数</span>
            </div>
            <div class="stat-card">
              <span class="stat-card-value">{{ shared.partitionResult.global_gates }}</span>
              <span class="stat-card-label">全局门数</span>
            </div>
            <div class="stat-card">
              <span class="stat-card-value">{{ shared.partitionResult.optimized_gate_count }}</span>
              <span class="stat-card-label">优化后门数</span>
            </div>
            <div class="stat-card">
              <span class="stat-card-value">{{ shared.partitionResult.elapsed_seconds }}s</span>
              <span class="stat-card-label">耗时</span>
            </div>
          </div>
          <el-table :data="shared.partitionResult.partitions" size="small" stripe class="partition-table">
            <el-table-column label="分区" width="60">
              <template #default="{ row }">P{{ row.index + 1 }}</template>
            </el-table-column>
            <el-table-column prop="size" label="量子比特数" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.size }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="qubits" label="量子比特列表">
              <template #default="{ row }">
                <span class="qubit-list">{{ row.qubits?.join(', ') }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="download-row">
            <el-button size="small" type="primary" :href="getReportDownloadUrl(shared.taskId)" download>
              <el-icon><Download /></el-icon>下载报告 (JSON)
            </el-button>
            <el-button size="small" type="success" tag="a" :href="getPartitionGraphPngUrl(shared.taskId)" download>
              <el-icon><Picture /></el-icon>下载交互图 (PNG)
            </el-button>
          </div>
        </div>
        <div v-else class="panel-body panel-placeholder">
          <div class="placeholder-icon">
            <el-icon :size="36"><PieChart /></el-icon>
          </div>
          <p class="placeholder-text">
            {{ shared.circuit ? '配置参数后点击“开始分区计算”' : '请先上传并解析电路文件' }}
          </p>
        </div>
      </div>

      <div class="panel-card result-graph">
        <div class="panel-header">
          <span class="panel-icon"><el-icon><Share /></el-icon></span>
          <span class="panel-title">分区交互图</span>
          <span class="panel-hint">边标签 = 全局门数量</span>
        </div>
        <div v-if="shared.partitionResult" class="panel-body graph-body">
          <div ref="graphContainer" class="graph-container"></div>
        </div>
        <div v-else class="panel-body panel-placeholder">
          <div class="placeholder-icon">
            <el-icon :size="36"><Share /></el-icon>
          </div>
          <p class="placeholder-text">分区计算完成后，<br>交互图将在此渲染</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, inject, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { getReportDownloadUrl, getPartitionGraphPngUrl } from '../api'
import * as api from '../api'

const shared = inject('shared')
const qasmText = ref('')
const uploading = ref(false)
const loading = ref(false)
const progress = ref(0)
const statusMsg = ref('')
const graphContainer = ref(null)
let network = null
let pollTimer = null
let isMounted = true
let visNetworkModule = null
let visDataModule = null

const params = reactive({
  num_partitions: 2,
  max_imbalance: 1,
  b1: 10,
  b2: 2,
  alpha: 3,
  beta: 1,
  search: false,
})

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

function handleFile(file) {
  const reader = new FileReader()
  reader.onload = event => {
    qasmText.value = typeof event.target?.result === 'string' ? event.target.result : ''
    void handleUpload()
  }
  reader.readAsText(file.raw)
}

async function handleUpload() {
  if (!qasmText.value.trim()) return
  uploading.value = true
  shared.circuit = null
  shared.taskId = null
  shared.partitionResult = null
  shared.mapping = null
  shared.edgeCosts = null
  shared.targetEdges = []
  shared.topoComparisons = null
  shared.lastError = ''
  shared.workflowStatus = 'created'
  shared.currentStage = 'created'
  shared.stageRuns = {
    ...shared.stageRuns,
    created: 'success',
    validated: 'pending',
    distributed_compiling: 'pending',
    aggregating: 'pending',
    completed: 'pending',
  }

  try {
    const { data } = await api.uploadCircuit(qasmText.value.trim())
    shared.circuit = data
    shared.workflowStatus = 'validated'
    shared.currentStage = 'validated'
    shared.stageRuns = {
      ...shared.stageRuns,
      created: 'success',
      validated: 'success',
      distributed_compiling: 'pending',
      aggregating: 'pending',
      completed: 'pending',
    }
    ElMessage.success('电路解析成功')
  } catch (error) {
    shared.workflowStatus = 'failed'
    shared.lastError = error.response?.data?.detail || error.message
    ElMessage.error(`解析失败：${error.response?.data?.detail || error.message}`)
  } finally {
    uploading.value = false
  }
}

async function handleRun() {
  if (!shared.circuit) return
  loading.value = true
  progress.value = 0
  statusMsg.value = '提交任务...'
  shared.partitionResult = null
  shared.mapping = null
  shared.targetEdges = []
  shared.topoComparisons = null
  shared.lastError = ''
  shared.workflowStatus = 'running'
  shared.currentStage = 'distributed_compiling'
  shared.stageRuns = {
    ...shared.stageRuns,
    created: 'success',
    validated: 'success',
    distributed_compiling: 'running',
    aggregating: 'pending',
    completed: 'pending',
  }

  try {
    const { data } = await api.runPartition({
      circuit_id: shared.circuit.circuit_id,
      ...params,
    })
    shared.taskId = data.task_id

    const poll = async () => {
      if (!isMounted) return
      const { data: status } = await api.getTaskStatus(shared.taskId)
      if (!isMounted) return
      progress.value = status.progress || 0
      statusMsg.value = status.message || '任务处理中...'

      if (status.status === 'completed') {
        progress.value = 100
        const { data: result } = await api.getPartitionResult(shared.taskId)
        if (!isMounted) return
        shared.partitionResult = result
        shared.workflowStatus = 'partial_completed'
        shared.currentStage = 'distributed_compiling'
        shared.stageRuns = {
          ...shared.stageRuns,
          distributed_compiling: 'success',
          aggregating: 'pending',
          completed: 'pending',
        }

        try {
          const { data: graphData } = await api.getGraphData(shared.taskId)
          if (isMounted) {
            shared.edgeCosts = graphData.edge_costs ?? null
          }
        } catch {
          if (isMounted) {
            shared.edgeCosts = null
          }
        }

        loading.value = false
        await nextTick()
        if (isMounted) await renderGraph()
        ElMessage.success('分区计算完成')
      } else if (status.status === 'failed') {
        if (!isMounted) return
        loading.value = false
        shared.workflowStatus = 'failed'
        shared.stageRuns = {
          ...shared.stageRuns,
          distributed_compiling: 'failed',
          aggregating: 'pending',
          completed: 'pending',
        }
        shared.lastError = status.message || '分区计算失败'
        ElMessage.error('计算失败')
      } else {
        pollTimer = setTimeout(poll, 800)
      }
    }

    void poll()
  } catch (error) {
    if (!isMounted) return
    loading.value = false
    shared.workflowStatus = 'failed'
    shared.stageRuns = {
      ...shared.stageRuns,
      distributed_compiling: 'failed',
      aggregating: 'pending',
      completed: 'pending',
    }
    shared.lastError = error.response?.data?.detail || error.message
    ElMessage.error('启动失败')
  }
}

async function renderGraph() {
  try {
    if (!graphContainer.value || !shared.partitionResult?.partitions) return
    const { Network, DataSet } = await loadVisModules()
    if (!isMounted || !graphContainer.value) return

    const parts = shared.partitionResult.partitions
    const costs = shared.edgeCosts || {}
    const colors = [
      '#36cfc9', '#597ef7', '#ffc53d', '#ff7a45',
      '#73d13d', '#ff85c0', '#9254de', '#5cdbd3',
    ]

    const nodes = parts.map((part, index) => ({
      id: `P${index + 1}`,
      label: `分区${index + 1}\n(${part.size} 量子比特)`,
      size: 30 + part.size * 6,
      font: { size: 14, face: 'system-ui' },
      color: { background: colors[index % colors.length], border: '#1a1a2e' },
    }))

    const edges = []
    for (let i = 0; i < parts.length; i += 1) {
      for (let j = i + 1; j < parts.length; j += 1) {
        const key = `P${i + 1}-P${j + 1}`
        const weight = costs[key] ?? costs[`P${j + 1}-P${i + 1}`] ?? 0
        edges.push({
          from: `P${i + 1}`,
          to: `P${j + 1}`,
          label: String(weight),
          width: Math.max(1, Math.min(8, weight / 5)),
          font: { size: 16, strokeWidth: 3, strokeColor: '#fff' },
          color: { color: '#b0b8c8', highlight: '#36cfc9' },
        })
      }
    }

    if (network) {
      try {
        network.destroy()
      } catch {
        // vis-network may already be disposed
      }
      network = null
    }

    network = new Network(
      graphContainer.value,
      { nodes: new DataSet(nodes), edges: new DataSet(edges) },
      {
        physics: {
          solver: 'forceAtlas2Based',
          stabilization: { iterations: 80 },
        },
        edges: { smooth: { type: 'continuous' } },
      }
    )
  } catch (error) {
    shared.lastError = shared.lastError || error.message
  }
}

watch(() => shared.edgeCosts, () => nextTick(() => { void renderGraph() }))

onMounted(() => {
  isMounted = true
  if (shared.partitionResult) nextTick(() => { void renderGraph() })
})

onUnmounted(() => {
  isMounted = false
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  if (network) {
    try {
      network.destroy()
    } catch {
      // vis-network may already be disposed
    }
    network = null
  }
  if (graphContainer.value) {
    graphContainer.value.innerHTML = ''
  }
})
</script>

<style scoped>
.partition-page {
  max-width: 1500px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.top-panels {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.results-section {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 16px;
  align-items: start;
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
  font-size: 0.72rem;
  font-weight: 400;
  color: #999;
}

.panel-body {
  padding: 18px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.panel-placeholder {
  align-items: center;
  justify-content: center;
  min-height: 200px;
  border: 1px dashed #d9e3f0;
  border-radius: 12px;
  background: #fbfcfe;
}

.placeholder-icon {
  color: #b8c2cf;
  margin-bottom: 12px;
}

.placeholder-text {
  font-size: 0.8rem;
  color: #98a2b3;
  text-align: center;
  line-height: 1.6;
}

.upload-area {
  width: 100%;
}

.upload-icon {
  font-size: 2rem;
  color: #8fa8c7;
}

.upload-text {
  font-size: 0.85rem;
  color: #667085;
  margin-top: 8px;
}

.upload-text em {
  color: #2456b8;
  font-style: normal;
  cursor: pointer;
}

.divider-text {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 14px 0;
  color: #98a2b3;
  font-size: 0.72rem;
}

.divider-text::before,
.divider-text::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e6ebf2;
}

.qasm-input {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.78rem;
}

.action-btn {
  width: 100%;
  margin-top: 14px;
  height: 40px;
  border-radius: 10px;
  font-weight: 600;
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat-item {
  text-align: center;
  padding: 12px 8px;
  background: #fafcff;
  border-radius: 12px;
  border: 1px solid #e6ebf2;
}

.stat-item.highlight {
  background: linear-gradient(180deg, #fff7eb, #ffffff);
  border-color: #f5d4a6;
}

.stat-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.stat-value.mono {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.75rem;
  color: #888;
}

.stat-item.highlight .stat-value {
  color: #d46b08;
}

.stat-label {
  display: block;
  font-size: 0.7rem;
  color: #98a2b3;
  margin-top: 4px;
}

.param-form {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.param-row {
  margin-bottom: 4px;
}

.param-toggles {
  margin-bottom: 0;
}

.param-form :deep(.el-form-item) {
  margin-bottom: 10px;
}

.param-form :deep(.el-form-item__label) {
  font-size: 0.75rem;
  color: #666;
  padding-bottom: 2px;
}

.progress-area {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #edf1f6;
}

.progress-msg {
  font-size: 0.72rem;
  color: #98a2b3;
  text-align: center;
  margin-top: 6px;
}

.stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 14px 8px;
  background: linear-gradient(180deg, #ffffff, #f7fbff);
  border-radius: 12px;
  border: 1px solid #e6ebf2;
}

.stat-card-value {
  display: block;
  font-size: 1.3rem;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.stat-card-label {
  display: block;
  font-size: 0.68rem;
  color: #98a2b3;
  margin-top: 2px;
}

.partition-table {
  margin-bottom: 14px;
}

.qubit-list {
  font-size: 0.78rem;
  color: #666;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}

.download-row {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid #edf1f6;
}

.graph-body {
  padding: 12px;
}

.graph-container {
  width: 100%;
  height: 450px;
  border: 1px solid #e6ebf2;
  border-radius: 12px;
  background: radial-gradient(circle at top, rgba(55, 125, 255, 0.06), transparent 40%), #f8fbff;
}

:deep(.el-upload-dragger) {
  border-radius: 12px;
  border-color: #d7e3f3;
  background: #fbfcff;
}

:deep(.el-upload-dragger:hover) {
  border-color: #9fcbff;
}

:deep(.el-descriptions__label),
:deep(.el-descriptions__content) {
  font-size: 0.78rem;
}

:deep(.el-table) {
  --el-table-border-color: #e6ebf2;
  --el-table-header-bg-color: #f7faff;
  --el-table-row-hover-bg-color: #f8fbff;
  border-radius: 12px;
  overflow: hidden;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-upload-dragger),
:deep(.el-input-number),
:deep(.el-slider__runway) {
  border-radius: 12px;
}

:deep(.el-button--primary.action-btn) {
  background: linear-gradient(135deg, #18baa9, #377dff);
  border: none;
}

@media (max-width: 1200px) {
  .top-panels {
    grid-template-columns: 1fr 1fr;
  }

  .results-section {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .top-panels {
    grid-template-columns: 1fr;
  }

  .stat-row {
    grid-template-columns: 1fr 1fr;
  }

  .download-row {
    flex-direction: column;
  }
}
</style>
