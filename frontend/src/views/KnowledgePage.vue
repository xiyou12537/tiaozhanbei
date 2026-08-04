<template>
  <div class="knowledge-page">
    <section class="hero-console">
      <img class="hero-image" :src="heroImage" alt="Knowledge hub" />
      <div class="hero-overlay"></div>

      <div class="hero-content">
        <div class="hero-copy">
          <span class="panel-kicker">Knowledge Base</span>
          <h2>知识库</h2>
        </div>

        <div class="hero-stats">
          <div class="stat-card">
            <span>文档</span>
            <strong>{{ stats.document_count ?? '--' }}</strong>
          </div>
          <div class="stat-card">
            <span>已索引</span>
            <strong>{{ stats.indexed_document_count ?? '--' }}</strong>
          </div>
          <div class="stat-card">
            <span>引用</span>
            <strong>{{ analytics.total_reference_count ?? '--' }}</strong>
          </div>
          <div class="stat-card">
            <span>未引用</span>
            <strong>{{ analytics.unreferenced_indexed_document_count ?? '--' }}</strong>
          </div>
        </div>
      </div>
    </section>

    <div class="knowledge-grid">
      <section class="surface-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker panel-kicker-dark">Search</span>
            <h3>知识检索</h3>
          </div>
        </div>

        <div class="search-form">
          <el-input
            v-model="searchForm.query"
            placeholder="搜索论文、系统文档或工作流记录"
            clearable
            @keyup.enter="handleSearch"
          />
          <el-select v-model="searchForm.documentType" placeholder="文档类型">
            <el-option label="全部文档" value="" />
            <el-option label="系统文档" value="system_doc" />
            <el-option label="论文" value="paper" />
          </el-select>
          <el-input-number v-model="searchForm.topK" :min="1" :max="10" />
          <el-button type="primary" :loading="searching" @click="handleSearch">检索</el-button>
        </div>

        <div class="help-grid">
          <article class="help-card">
            <strong>材料语境</strong>
            <p>催化、吸附、量子编码与评分依据集中检索。</p>
          </article>
          <article class="help-card">
            <strong>系统依据</strong>
            <p>工作流记录、阶段输出与结果解释保持可追溯。</p>
          </article>
        </div>

        <div class="result-block">
          <div class="result-head">
            <strong>检索结果</strong>
            <span>{{ searchHits.length }} 条</span>
          </div>

          <div v-if="!searchHits.length" class="empty-state">
            <strong>暂无结果</strong>
            <p>输入关键词后开始检索。</p>
          </div>

          <div v-else class="hit-list">
            <article
              v-for="item in searchHits"
              :key="`${item.document_id}-${item.chunk_id}`"
              class="hit-card"
            >
              <div class="hit-top">
                <strong><ChemicalFormula :text="item.document_name" /></strong>
                <span>{{ item.document_type }}</span>
              </div>
              <div class="hit-meta">
              <span>section={{ item.section_title || 'default' }}</span>
                <span>score={{ item.score?.toFixed?.(3) ?? item.score }}</span>
              </div>
              <p><ChemicalFormula :text="item.content" /></p>
            </article>
          </div>
        </div>
      </section>

      <aside class="side-column">
        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">Documents</span>
              <h3>文档列表</h3>
            </div>
          </div>

          <div v-if="documents.length" class="doc-list">
            <article v-for="item in documents" :key="item.id" class="doc-card">
              <div class="doc-top">
                <strong><ChemicalFormula :text="item.name" /></strong>
                <span>{{ item.document_type }}</span>
              </div>
              <div class="doc-meta">
                <span>status={{ item.status }}</span>
                <span>chunks={{ item.chunk_count }}</span>
              </div>
              <p><ChemicalFormula :text="item.summary || '暂无摘要。'" /></p>
            </article>
          </div>

          <div v-else class="empty-state compact-empty">
            <strong>暂无文档</strong>
            <p>后端知识库加载后会显示在这里。</p>
          </div>
        </section>

        <section class="surface-panel">
          <div class="panel-heading">
            <div>
              <span class="panel-kicker panel-kicker-dark">References</span>
              <h3>高频引用</h3>
            </div>
          </div>

          <div v-if="analytics.top_documents?.length" class="doc-list">
            <article v-for="item in analytics.top_documents" :key="item.document_id" class="doc-card">
              <div class="doc-top">
                <strong><ChemicalFormula :text="item.document_name" /></strong>
                <span>{{ item.document_type }}</span>
              </div>
              <div class="doc-meta">
                <span>ref={{ item.reference_count }}</span>
                <span>avg={{ item.avg_score?.toFixed?.(3) ?? item.avg_score }}</span>
              </div>
              <p>最近引用：{{ item.last_referenced_at || '--' }}</p>
            </article>
          </div>

          <div v-else class="empty-state compact-empty">
            <strong>暂无引用统计</strong>
            <p>检索或问答引用文档后会生成统计。</p>
          </div>
        </section>
      </aside>
    </div>

    <section class="assistant-section">
      <div class="assistant-summary">
        <div>
          <span class="panel-kicker panel-kicker-dark">Q&A</span>
          <h3>知识问答</h3>
        </div>
        <el-button @click="isAssistantOpen = !isAssistantOpen">
          {{ isAssistantOpen ? '收起' : '打开问答' }}
        </el-button>
      </div>

      <AssistantPanel
        v-if="isAssistantOpen"
        class="assistant-panel-inner"
        kicker="Knowledge Assistant"
        title="知识问答"
        description="围绕索引文档、工作流行为或结果解释继续追问。"
        placeholder="输入知识库或系统问题..."
        :quickQuestions="quickQuestions"
        :helperCards="assistantCards"
      />
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AssistantPanel from '../components/AssistantPanel.vue'
import ChemicalFormula from '../components/ChemicalFormula.vue'
import heroImage from '../assets/chemistry-hero.png'
import {
  fetchKnowledgeAnalytics,
  fetchKnowledgeDocuments,
  fetchKnowledgeStats,
  searchKnowledge,
} from '../api/knowledgeApi'

const documents = ref([])
const stats = ref({})
const analytics = ref({ top_documents: [] })
const searchHits = ref([])
const searching = ref(false)
const isAssistantOpen = ref(false)

const searchForm = reactive({
  query: '',
  documentType: '',
  topK: 5,
})

const quickQuestions = [
  '当前主流程有哪些阶段？',
  '为什么推荐这个材料？',
  '知识库收录了哪些系统文档？',
  '分布式执行结果怎么看？',
]

const assistantCards = [
  { label: '范围', value: '知识 + 工作流', note: '支持文档问答和系统使用问题。' },
  { label: '访问', value: '已登录', note: '知识能力保留在平台工作区内。' },
  { label: '引用', value: '可追溯', note: '回答可回到来源片段。' },
  { label: '模式', value: '检索 + 问答', note: '此处不放文档管理入口。' },
]

onMounted(() => {
  loadKnowledgeData()
})

async function loadKnowledgeData() {
  try {
    const [documentsRes, statsRes, analyticsRes] = await Promise.all([
      fetchKnowledgeDocuments(),
      fetchKnowledgeStats(),
      fetchKnowledgeAnalytics(),
    ])

    documents.value = documentsRes.data || []
    stats.value = statsRes.data || {}
    analytics.value = analyticsRes.data || { top_documents: [] }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '知识库数据加载失败。')
  }
}

async function handleSearch() {
  if (!searchForm.query.trim()) {
    ElMessage.warning('请输入检索关键词。')
    return
  }

  searching.value = true
  try {
    const { data } = await searchKnowledge({
      query: searchForm.query,
      top_k: searchForm.topK,
      document_type: searchForm.documentType || null,
    })
    searchHits.value = data.hits || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '知识检索失败。')
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.knowledge-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-console,
.surface-panel,
.assistant-section {
  border-radius: 8px;
  overflow: hidden;
}

.hero-console {
  position: relative;
  min-height: 250px;
  background: #081a2c;
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
    linear-gradient(90deg, rgba(4, 13, 24, 0.94) 0%, rgba(4, 13, 24, 0.72) 52%, rgba(4, 13, 24, 0.5) 100%),
    linear-gradient(180deg, rgba(8, 18, 32, 0.16) 0%, rgba(8, 18, 32, 0.58) 100%);
}

.hero-content {
  position: relative;
  z-index: 1;
  min-height: 250px;
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(360px, 0.98fr);
  gap: 18px;
  align-items: end;
}

.panel-kicker,
.panel-kicker-dark {
  color: #0f766e;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}

.hero-copy .panel-kicker {
  color: #67d5ca;
}

.hero-copy h2 {
  margin-top: 6px;
  font-size: 1.32rem;
  color: #f8fbff;
  letter-spacing: 0;
}

.hero-copy p {
  margin-top: 10px;
  max-width: 760px;
  color: rgba(228, 236, 246, 0.84);
  font-size: 0.86rem;
  line-height: 1.75;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.stat-card,
.help-card,
.hit-card,
.doc-card {
  border-radius: 8px;
}

.stat-card {
  padding: 16px;
  border: 1px solid rgba(166, 204, 247, 0.18);
  background: rgba(248, 251, 255, 0.96);
}

.stat-card span {
  color: #667085;
  font-size: 0.74rem;
}

.stat-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 1rem;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(320px, 0.92fr);
  gap: 18px;
}

.surface-panel,
.assistant-section {
  padding: 18px;
  border: 1px solid #e6ebf2;
  background: #fff;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-heading h3,
.assistant-summary h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.08rem;
  letter-spacing: 0;
}

.search-form {
  margin-top: 18px;
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) 180px 120px auto;
  gap: 12px;
  align-items: center;
}

.help-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.help-card,
.hit-card,
.doc-card {
  padding: 16px;
  border: 1px solid #e6ebf2;
  background: #f8fbff;
}

.help-card strong,
.hit-top strong,
.doc-top strong,
.empty-state strong {
  color: #101828;
}

.help-card p,
.hit-card p,
.doc-card p,
.empty-state p,
.assistant-summary p {
  margin-top: 8px;
  color: #475467;
  line-height: 1.7;
  font-size: 0.84rem;
}

.result-block {
  margin-top: 18px;
}

.result-head,
.assistant-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-head strong {
  color: #101828;
}

.result-head span,
.hit-top span,
.hit-meta span,
.doc-top span,
.doc-meta span {
  color: #667085;
  font-size: 0.74rem;
}

.empty-state {
  margin-top: 12px;
  padding: 18px;
  border-radius: 8px;
  border: 1px dashed #d0d5dd;
  background: #fbfcfe;
}

.compact-empty {
  margin-top: 18px;
}

.hit-list,
.doc-list {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}

.hit-top,
.doc-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.hit-meta,
.doc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
}

.side-column {
  display: grid;
  gap: 18px;
}

.assistant-panel-inner {
  margin-top: 18px;
}

@media (max-width: 1180px) {
  .hero-content,
  .knowledge-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 980px) {
  .hero-stats,
  .search-form,
  .help-grid {
    grid-template-columns: 1fr;
  }

  .assistant-summary {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
