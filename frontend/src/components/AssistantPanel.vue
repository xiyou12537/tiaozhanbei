<template>
  <section class="assistant-panel">
    <div class="assistant-head">
      <div>
        <span class="panel-kicker">{{ kicker }}</span>
        <h3>{{ title }}</h3>
        <p>{{ description }}</p>
      </div>
      <el-button text :disabled="!hasMessages" @click="handleClear">
        <el-icon :size="16"><Delete /></el-icon>
        清空
      </el-button>
    </div>

    <div v-if="helperCards.length" class="helper-grid">
      <article v-for="item in helperCards" :key="item.label" class="helper-card">
        <span>{{ item.label }}</span>
        <strong><ChemicalFormula :text="item.value" /></strong>
        <small><ChemicalFormula :text="item.note" /></small>
      </article>
    </div>

    <div v-if="quickQuestions.length" class="quick-question-row">
      <button
        v-for="item in quickQuestions"
        :key="item"
        class="quick-question"
        :disabled="streaming"
        @click="sendMessage(item)"
      >
        {{ item }}
      </button>
    </div>

    <div class="assistant-surface">
      <ChatMessages
        :messages="messages"
        :streaming="streaming"
        :streamingText="streamingText"
        @suggest="sendMessage"
      />
      <ChatInput
        :disabled="streaming"
        :placeholder="placeholder"
        @send="sendMessage"
      />
    </div>
  </section>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import ChemicalFormula from './ChemicalFormula.vue'
import ChatInput from './ChatInput.vue'
import ChatMessages from './ChatMessages.vue'
import { useChat } from '../composables/useChat'

defineProps({
  kicker: { type: String, default: 'Research Assistant' },
  title: { type: String, default: '研究问答' },
  description: { type: String, default: '围绕当前任务、结果指标或来源依据继续追问。' },
  placeholder: { type: String, default: '输入问题...' },
  quickQuestions: { type: Array, default: () => [] },
  helperCards: { type: Array, default: () => [] },
})

const { messages, streaming, streamingText, hasMessages, loadHistory, sendMessage, clearHistory } = useChat()

onMounted(() => {
  if (!messages.length) {
    loadHistory()
  }
})

async function handleClear() {
  try {
    await ElMessageBox.confirm('清空当前对话记录？', '确认操作', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await clearHistory()
    ElMessage.success('对话记录已清空')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.warn('clear assistant history error:', error)
    }
  }
}
</script>

<style scoped>
.assistant-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  min-height: 0;
  color: #101828;
}

.assistant-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-kicker {
  color: #0f766e;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}

.assistant-head h3 {
  margin-top: 6px;
  color: #101828;
  font-size: 1.06rem;
  letter-spacing: 0;
}

.assistant-head p {
  margin-top: 8px;
  color: #475467;
  font-size: 0.84rem;
  line-height: 1.7;
  max-width: 620px;
}

.assistant-head :deep(.el-button) {
  color: #2456b8;
  border-radius: 8px;
  background: #eef4ff;
  border: 1px solid #d7e4fb;
  padding: 0 12px;
  height: 36px;
}

.helper-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.helper-card {
  padding: 14px;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  background: #f8fbff;
}

.helper-card span,
.helper-card small {
  color: #667085;
  font-size: 0.72rem;
}

.helper-card strong {
  display: block;
  margin-top: 8px;
  color: #101828;
  font-size: 0.94rem;
}

.helper-card small {
  display: block;
  margin-top: 8px;
  line-height: 1.6;
}

.quick-question-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-question {
  border: 1px solid rgba(15, 118, 110, 0.18);
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  border-radius: 999px;
  padding: 8px 12px;
  font-size: 0.74rem;
  cursor: pointer;
}

.quick-question:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.assistant-surface {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 380px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e6ebf2;
  overflow: hidden;
}

@media (max-width: 980px) {
  .helper-grid {
    grid-template-columns: 1fr;
  }
}
</style>
