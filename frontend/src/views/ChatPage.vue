<template>
  <div class="chat-page">
    <div class="chat-header">
      <div class="chat-header-left">
        <div class="header-icon">
          <svg viewBox="0 0 40 40" fill="none" width="32" height="32">
            <circle cx="20" cy="20" r="18" stroke="currentColor" stroke-width="1.5" opacity="0.4"/>
            <circle cx="20" cy="20" r="8" stroke="currentColor" stroke-width="2"/>
            <circle cx="20" cy="20" r="2" fill="currentColor"/>
          </svg>
        </div>
        <div>
          <h3>量子 AI 助手</h3>
          <span class="header-sub">基于大语言模型 · 量子计算领域问答</span>
        </div>
      </div>
      <div class="chat-header-right">
        <el-button text size="small" @click="handleClear" :disabled="!hasMessages">
          <el-icon :size="16"><Delete /></el-icon>
          清空对话
        </el-button>
      </div>
    </div>

    <ChatMessages
      :messages="messages"
      :streaming="streaming"
      :streamingText="streamingText"
      @suggest="sendMessage"
    />

    <ChatInput
      :disabled="streaming"
      @send="sendMessage"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatMessages from '../components/ChatMessages.vue'
import ChatInput from '../components/ChatInput.vue'
import { useChat } from '../composables/useChat'

const { messages, streaming, streamingText, hasMessages, loadHistory, sendMessage, clearHistory } = useChat()

onMounted(() => {
  if (!messages.length) loadHistory()
})

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空所有对话历史吗？', '确认', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
    clearHistory()
    ElMessage.success('对话历史已清空')
  } catch {}
}
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px - 40px);  /* topbar + padding */
  background: #0f1923;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.06);
  overflow: hidden;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.1);
  flex-shrink: 0;
}
.chat-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-icon { color: #36cfc9; }
.chat-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: #e8eaed;
}
.header-sub {
  font-size: 0.7rem;
  color: #4a5d70;
}
.chat-header-right {
  display: flex;
  gap: 8px;
}
.chat-header-right :deep(.el-button) { color: #5a6d80; }
.chat-header-right :deep(.el-button:hover) { color: #ff4d4f; }
</style>
