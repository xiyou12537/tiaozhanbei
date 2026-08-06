<template>
  <div class="capability-page">
    <section class="hero-console">
      <img class="hero-image" :src="heroImage" alt="编译能力页主视觉" />
      <div class="hero-overlay"></div>

      <div class="hero-content">
        <div class="hero-copy">
          <span class="panel-kicker">Capability Workspace</span>
          <h2>分布式编译能力页</h2>
        </div>

        <div class="hero-stats">
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
    </section>

    <section class="surface-panel">
      <div class="tab-bar">
        <div class="tab-copy">
          <span class="panel-kicker panel-kicker-dark">Compiler Tools</span>
          <h3>编译子域能力</h3>
        </div>

        <el-tabs v-model="activeTab" class="capability-tabs">
          <el-tab-pane label="电路分区" name="partition" />
          <el-tab-pane label="芯片映射" name="mapping" />
        </el-tabs>
      </div>

      <div v-show="activeTab === 'partition'" class="tab-content themed-capability">
        <PartitionPage />
      </div>
      <div v-show="activeTab === 'mapping'" class="tab-content themed-capability">
        <MappingPage />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import heroImage from '../assets/chemistry-hero.png'

const MappingPage = defineAsyncComponent(() => import('./MappingPage.vue'))
const PartitionPage = defineAsyncComponent(() => import('./PartitionPage.vue'))

const shared = inject('shared')
const route = useRoute()
const router = useRouter()
const activeTab = ref(route.query.tab === 'mapping' ? 'mapping' : 'partition')

watch(
  () => route.query.tab,
  value => {
    activeTab.value = value === 'mapping' ? 'mapping' : 'partition'
  }
)

watch(activeTab, value => {
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
  gap: 18px;
}

.hero-console {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  background: #081a2c;
  min-height: 280px;
}

.hero-image,
.hero-overlay {
  position: absolute;
  inset: 0;
}

.hero-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero-overlay {
  background:
    linear-gradient(90deg, rgba(4, 13, 24, 0.92) 0%, rgba(4, 13, 24, 0.68) 45%, rgba(4, 13, 24, 0.42) 100%),
    linear-gradient(180deg, rgba(8, 18, 32, 0.16) 0%, rgba(8, 18, 32, 0.58) 100%);
}

.hero-content {
  position: relative;
  z-index: 1;
  min-height: 280px;
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 18px;
  align-items: end;
}

.panel-kicker {
  color: #67d5ca;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}

.panel-kicker-dark {
  color: #0f766e;
}

.hero-copy h2 {
  margin-top: 6px;
  font-size: 1.18rem;
  color: #f8fbff;
}

.hero-copy p {
  margin-top: 10px;
  max-width: 760px;
  color: rgba(228, 236, 246, 0.84);
  font-size: 0.84rem;
  line-height: 1.75;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.stat-box {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid rgba(166, 204, 247, 0.16);
  background: rgba(4, 13, 24, 0.88);
}

.stat-box span {
  color: rgba(223, 232, 243, 0.72);
  font-size: 0.74rem;
}

.stat-box strong {
  display: block;
  margin-top: 8px;
  color: #fff;
  font-size: 1rem;
}

.surface-panel {
  padding: 18px;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.tab-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.tab-copy h3 {
  margin-top: 6px;
  font-size: 1.04rem;
  color: #101828;
}

.capability-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.capability-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.capability-tabs :deep(.el-tabs__item) {
  height: 36px;
  color: #667085;
}

.capability-tabs :deep(.el-tabs__item.is-active) {
  color: #2456b8;
}

.tab-content {
  min-width: 0;
}

.themed-capability :deep(.panel-card),
.themed-capability :deep(.guide-banner) {
  border-radius: 16px;
  border: 1px solid #e6ebf2;
  background: linear-gradient(180deg, #ffffff, #f9fbff);
  box-shadow: none;
}

.themed-capability :deep(.panel-card:hover) {
  border-color: #d7e3f3;
  box-shadow: 0 10px 24px rgba(15, 23, 40, 0.05);
}

.themed-capability :deep(.panel-header) {
  background: #f7faff;
  border-bottom: 1px solid #edf1f6;
  color: #101828;
}

.themed-capability :deep(.panel-icon) {
  background: #edf4ff;
  color: #2456b8;
}

.themed-capability :deep(.panel-hint),
.themed-capability :deep(.field-label),
.themed-capability :deep(.placeholder-text),
.themed-capability :deep(.hint-text),
.themed-capability :deep(.edge-list),
.themed-capability :deep(.stat-label),
.themed-capability :deep(.cost-label),
.themed-capability :deep(.preview-label) {
  color: #667085;
}

.themed-capability :deep(.graph-container),
.themed-capability :deep(.preview-graph) {
  border-radius: 10px;
  border-color: #e6ebf2;
  background: #f8fbff;
}

.themed-capability :deep(.action-btn) {
  border-radius: 10px;
}

.themed-capability :deep(.el-upload-dragger),
.themed-capability :deep(.el-textarea__inner),
.themed-capability :deep(.el-select__wrapper),
.themed-capability :deep(.el-input__wrapper) {
  border-radius: 12px;
}

.themed-capability :deep(.guide-banner) {
  margin-top: 0;
}

@media (max-width: 1100px) {
  .hero-content,
  .hero-stats {
    grid-template-columns: 1fr;
  }

  .tab-bar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
