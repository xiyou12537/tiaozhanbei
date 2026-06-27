<template>
  <div class="history-page">
    <div class="summary-row">
      <div class="summary-card">
        <span>历史工作流</span>
        <strong>{{ records.length }}</strong>
      </div>
      <div class="summary-card">
        <span>成功任务</span>
        <strong>{{ completedCount }}</strong>
      </div>
      <div class="summary-card">
        <span>平均传态</span>
        <strong>{{ avgTeleport }}</strong>
      </div>
      <div class="summary-card">
        <span>映射方案数</span>
        <strong>{{ mappingCount }}</strong>
      </div>
    </div>

    <div class="panel-card">
      <div class="panel-header">
        <span class="panel-icon"><el-icon><Clock /></el-icon></span>
        <span class="panel-title">工作流回看</span>
        <el-button size="small" @click="loadHistory" :loading="loading" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      <div class="panel-body" v-loading="loading">
        <!-- 空状态 -->
        <div v-if="!loading && records.length === 0" class="empty-state">
          <div class="empty-icon">
            <el-icon :size="40"><FolderOpened /></el-icon>
          </div>
          <h4>暂无工作流记录</h4>
          <p>完成一次分区计算后，平台原型会把任务记录归档到这里</p>
          <el-button type="primary" @click="$router.push('/app/capability?tab=partition')">
            <el-icon><Cpu /></el-icon>
            前往能力页
          </el-button>
        </div>

        <!-- 时间线 -->
        <el-timeline v-if="records.length">
          <el-timeline-item
            v-for="rec in records"
            :key="rec.task_id"
            :timestamp="rec.created_at?.slice(0, 19)"
            placement="top"
            :color="rec.status === 'completed' ? '#36cfc9' : '#ff4d4f'"
          >
            <div class="timeline-card">
              <div class="timeline-header">
                <span class="timeline-circuit">{{ rec.circuit_name }}</span>
                <el-tag
                  :type="rec.status === 'completed' ? 'success' : 'danger'"
                  size="small"
                  effect="light"
                >
                  {{ rec.status === 'completed' ? '已完成' : '失败' }}
                </el-tag>
              </div>

              <div class="timeline-stats">
                <div class="t-stat">
                  <span class="t-stat-val">{{ rec.num_qubits }}</span>
                  <span class="t-stat-label">量子比特</span>
                </div>
                <div class="t-stat">
                  <span class="t-stat-val">{{ rec.total_gates }}</span>
                  <span class="t-stat-label">总门数</span>
                </div>
                <div class="t-stat">
                  <span class="t-stat-val accent">{{ rec.result?.teleportations ?? '?' }}</span>
                  <span class="t-stat-label">传态次数</span>
                </div>
                <div class="t-stat">
                  <span class="t-stat-val">{{ rec.result?.global_gates ?? '?' }}</span>
                  <span class="t-stat-label">全局门</span>
                </div>
                <div class="t-stat">
                  <span class="t-stat-val mono">{{ rec.elapsed_seconds }}s</span>
                  <span class="t-stat-label">耗时</span>
                </div>
              </div>

              <div class="timeline-meta">
                <span class="meta-item">
                  分区数 k={{ rec.params?.num_partitions }}
                </span>
                <span class="meta-sep">·</span>
                <span class="meta-item">b1={{ rec.params?.b1 }}</span>
                <span class="meta-sep">·</span>
                <span class="meta-item">b2={{ rec.params?.b2 }}</span>
              </div>

              <div class="timeline-partitions" v-if="rec.result?.partitions?.length">
                <span class="part-label">分区结果：</span>
                <el-tag
                  v-for="p in rec.result.partitions"
                  :key="p.index"
                  size="small"
                  effect="plain"
                  class="part-tag"
                >
                  P{{ p.index + 1 }}({{ p.size }})
                </el-tag>
              </div>

              <div class="timeline-mappings" v-if="rec.mappings?.length">
                <span class="part-label">芯片映射：</span>
                <el-tag
                  v-for="m in rec.mappings"
                  :key="m.topology_name"
                  size="small"
                  type="success"
                  effect="plain"
                  class="map-tag"
                >
                  {{ m.topology_name }}: EPR={{ m.epr_cost }}
                </el-tag>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../api'

const records = ref([])
const loading = ref(false)

const completedCount = computed(() => records.value.filter(item => item.status === 'completed').length)
const mappingCount = computed(() => records.value.reduce((sum, item) => sum + (item.mappings?.length || 0), 0))
const avgTeleport = computed(() => {
  const values = records.value
    .map(item => item.result?.teleportations)
    .filter(value => typeof value === 'number')
  if (!values.length) return '--'
  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)
})

async function loadHistory() {
  loading.value = true
  try {
    const { data } = await api.get('/user/history')
    records.value = data.history || []
  } catch (e) {
    console.error('加载历史记录失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<style scoped>
.history-page {
  max-width: 1200px;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.summary-card {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 12px;
  padding: 16px;
}

.summary-card span {
  color: #667085;
  font-size: 0.74rem;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1.16rem;
}

/* ===== Panel Card ===== */
.panel-card {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e8ecf1;
  overflow: hidden;
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

.refresh-btn {
  border-radius: 6px;
}

.panel-body {
  padding: 24px;
}

/* ===== Empty State ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

.empty-icon {
  color: #d0d5dd;
  margin-bottom: 16px;
}

.empty-state h4 {
  font-size: 1rem;
  color: #555;
  margin: 0 0 6px;
}

.empty-state p {
  font-size: 0.82rem;
  color: #aaa;
  margin: 0 0 20px;
}

/* ===== Timeline Card ===== */
.timeline-card {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 8px;
  padding: 18px;
  transition: box-shadow 0.15s;
}

.timeline-card:hover {
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.05);
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.timeline-circuit {
  font-weight: 600;
  font-size: 0.9rem;
  color: #1a1a2e;
}

/* Stats */
.timeline-stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.t-stat {
  text-align: center;
  padding: 10px 6px;
  background: #fafbfc;
  border-radius: 6px;
  border: 1px solid #f0f2f5;
}

.t-stat-val {
  display: block;
  font-size: 1.1rem;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.t-stat-val.accent {
  color: #d46b08;
}

.t-stat-val.mono {
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.85rem;
  color: #666;
}

.t-stat-label {
  display: block;
  font-size: 0.65rem;
  color: #999;
  margin-top: 2px;
}

/* Meta */
.timeline-meta {
  margin-bottom: 10px;
  font-size: 0.75rem;
  color: #999;
}

.meta-item {
  color: #888;
}

.meta-sep {
  margin: 0 6px;
  color: #ddd;
}

/* Tags */
.timeline-partitions,
.timeline-mappings {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.part-label {
  font-size: 0.72rem;
  color: #999;
  margin-right: 4px;
}

.part-tag,
.map-tag {
  font-size: 0.7rem;
}

/* ===== Timeline Overrides ===== */
:deep(.el-timeline-item__timestamp) {
  font-size: 0.75rem;
  color: #aaa;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .summary-row {
    grid-template-columns: 1fr 1fr;
  }

  .timeline-stats {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
