<template>
  <div class="chat-page">
    <section class="hero-console">
      <img class="hero-image" :src="heroImage" alt="AI 助手主视觉" />
      <div class="hero-overlay"></div>

      <div class="hero-content">
        <div class="hero-copy">
          <span class="panel-kicker">Research Assistant</span>
          <h2>AI 助手</h2>
        </div>

        <div class="hero-actions">
          <el-button text :disabled="!hasMessages" @click="handleClear">
            <el-icon :size="16"><Delete /></el-icon>
            清空对话
          </el-button>
        </div>
      </div>
    </section>

    <section class="chat-surface">
      <ChatMessages
        :messages="messages"
        :streaming="streaming"
        :streamingText="streamingText"
        @suggest="sendMessage"
      />

      <ChatInput :disabled="streaming" @send="sendMessage" />
    </section>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatMessages from '../components/ChatMessages.vue'
import ChatInput from '../components/ChatInput.vue'
import { useChat } from '../composables/useChat'
import heroImage from '../assets/chemistry-hero.png'

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
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.warn('clear chat history error:', error)
    }
  }
}
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-console {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  background: #081a2c;
  min-height: 240px;
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
  min-height: 240px;
  padding: 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}

.panel-kicker {
  color: #67d5ca;
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
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

.hero-actions :deep(.el-button) {
  color: #f8fbff;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(166, 204, 247, 0.18);
  padding: 0 14px;
  height: 38px;
}

.chat-surface {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px - 40px - 258px);
  min-height: 520px;
  background: #0b1727;
  border-radius: 18px;
  border: 1px solid rgba(166, 204, 247, 0.14);
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

@media (max-width: 720px) {
  .hero-content {
    padding: 16px;
    align-items: flex-start;
    flex-direction: column;
    justify-content: flex-end;
  }

  .chat-surface {
    height: calc(100vh - 48px - 40px - 220px);
    min-height: 460px;
  }
}
</style>
