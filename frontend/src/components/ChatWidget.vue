<template>
  <Teleport to="body">
    <button v-if="!panelOpen" class="chat-fab" @click="openPanel">
      <svg viewBox="0 0 24 24" fill="none" width="22" height="22">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" />
        <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2" />
        <circle cx="12" cy="12" r="1" fill="currentColor" />
      </svg>
      <span class="fab-label">AI</span>
    </button>

    <Transition name="panel">
      <div v-if="panelOpen" class="chat-panel">
        <div class="panel-header">
          <div class="panel-header-left">
            <svg viewBox="0 0 24 24" fill="none" width="18" height="18" color="#36cfc9">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" />
              <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2" />
              <circle cx="12" cy="12" r="1" fill="currentColor" />
            </svg>
            <span>量子 AI 助手</span>
          </div>
          <div class="panel-header-right">
            <button class="panel-btn" title="清空对话" @click="handleClear">
              <el-icon :size="16"><Delete /></el-icon>
            </button>
            <button class="panel-btn" title="关闭" @click="panelOpen = false">
              <el-icon :size="18"><Close /></el-icon>
            </button>
          </div>
        </div>

        <ChatMessages
          :messages="messages"
          :streaming="streaming"
          :streamingText="streamingText"
          @suggest="sendMessage"
        />

        <ChatInput
          ref="inputRef"
          :disabled="streaming"
          placeholder="问我任何关于量子编译或平台流程的问题..."
          @send="sendMessage"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import { useChat } from '../composables/useChat'

const panelOpen = ref(false)
const inputRef = ref(null)

const { messages, streaming, streamingText, loadHistory, sendMessage, clearHistory } = useChat()

watch(panelOpen, open => {
  if (open && !messages.length) {
    loadHistory()
  }
  if (open) {
    nextTick(() => inputRef.value?.focus())
  }
})

function openPanel() {
  panelOpen.value = true
}

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
.chat-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 999;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #18baa9, #377dff);
  color: #fff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  box-shadow: 0 10px 28px rgba(33, 81, 150, 0.28);
  transition: transform 0.2s, box-shadow 0.2s;
}

.chat-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 14px 34px rgba(33, 81, 150, 0.36);
}

.fab-label {
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.chat-panel {
  position: fixed;
  bottom: 88px;
  right: 24px;
  z-index: 998;
  width: 400px;
  height: 560px;
  background: #0b1727;
  border: 1px solid rgba(166, 204, 247, 0.14);
  border-radius: 16px;
  box-shadow: 0 24px 60px rgba(5, 14, 26, 0.38);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(166, 204, 247, 0.1);
  background: rgba(255, 255, 255, 0.03);
  flex-shrink: 0;
}

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #eef4fb;
}

.panel-header-right {
  display: flex;
  gap: 4px;
}

.panel-btn {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #5a6d80;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.panel-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #c0ccda;
}

.panel-enter-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.panel-leave-active {
  transition: all 0.2s ease-in;
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(0.96);
}

@media (max-width: 460px) {
  .chat-panel {
    width: calc(100vw - 16px);
    right: 8px;
    bottom: 80px;
    height: 480px;
    border-radius: 12px;
  }
}
</style>
