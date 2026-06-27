<template>
  <div class="capability-page">
    <div class="header-panel">
      <div class="header-copy">
        <span class="panel-kicker">Capability Workspace</span>
        <h2>分布式编译能力页</h2>
        <p>这里承接当前原型真实可执行的接口：QASM 上传、分区求解、芯片映射、拓扑对比与报告导出。</p>
      </div>
      <div class="header-stats">
        <div class="stat-box">
          <span>输入工件</span>
          <strong>{{ shared.circuit ? '已上传' : '未上传' }}</strong>
        </div>
        <div class="stat-box">
          <span>分区状态</span>
          <strong>{{ partitionStatus }}</strong>
        </div>
        <div class="stat-box">
          <span>映射状态</span>
          <strong>{{ mappingStatus }}</strong>
        </div>
      </div>
    </div>

    <div class="tabs-panel">
      <el-tabs v-model="activeTab" class="capability-tabs">
        <el-tab-pane label="分布式编译" name="partition" />
        <el-tab-pane label="芯片映射" name="mapping" />
      </el-tabs>

      <div v-show="activeTab === 'partition'" class="tab-content">
        <PartitionPage />
      </div>
      <div v-show="activeTab === 'mapping'" class="tab-content">
        <MappingPage />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MappingPage from './MappingPage.vue'
import PartitionPage from './PartitionPage.vue'

const shared = inject('shared')
const route = useRoute()
const router = useRouter()
const activeTab = ref(route.query.tab === 'mapping' ? 'mapping' : 'partition')

watch(
  () => route.query.tab,
  (value) => {
    activeTab.value = value === 'mapping' ? 'mapping' : 'partition'
  }
)

watch(activeTab, (value) => {
  router.replace({
    path: '/app/capability',
    query: { tab: value },
  })
})

const partitionStatus = computed(() => {
  const status = shared.stageRuns?.distributed_compiling
  if (status === 'running') return '运行中'
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  return '待执行'
})

const mappingStatus = computed(() => (shared.mapping?.valid ? '已完成' : '待执行'))
</script>

<style scoped>
.capability-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-panel,
.tabs-panel {
  background: #fff;
  border: 1px solid #e6e9f0;
  border-radius: 14px;
}

.header-panel {
  padding: 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.panel-kicker,
.stat-box span {
  color: #667085;
  font-size: 0.74rem;
}

.header-copy h2 {
  margin-top: 6px;
  font-size: 1.12rem;
  color: #101828;
}

.header-copy p {
  margin-top: 8px;
  max-width: 760px;
  color: #475467;
  font-size: 0.84rem;
  line-height: 1.7;
}

.header-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(110px, 1fr));
  gap: 10px;
}

.stat-box {
  border: 1px solid #edf0f5;
  border-radius: 12px;
  padding: 14px;
  background: #fafcff;
}

.stat-box strong {
  display: block;
  margin-top: 6px;
  color: #101828;
  font-size: 0.94rem;
}

.tabs-panel {
  padding: 0 16px 16px;
}

.capability-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.tab-content {
  min-width: 0;
}

@media (max-width: 900px) {
  .header-panel {
    flex-direction: column;
  }

  .header-stats {
    width: 100%;
    grid-template-columns: 1fr;
  }
}
</style>
