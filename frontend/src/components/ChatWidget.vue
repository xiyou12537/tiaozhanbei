<template>
  <Teleport to="body">
    <!-- 浮动按钮 -->
    <button
      v-if="!panelOpen"
      class="chat-fab"
      @click="openPanel"
    >
      <svg viewBox="0 0 24 24" fill="none" width="22" height="22">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>
        <circle cx="12" cy="12" r="1" fill="currentColor"/>
      </svg>
      <span class="fab-label">AI</span>
    </button>

    <!-- 滑出面板 -->
    <Transition name="panel">
      <div v-if="panelOpen" class="chat-panel">
        <div class="panel-header">
          <div class="panel-header-left">
            <svg viewBox="0 0 24 24" fill="none" width="18" height="18" color="#36cfc9">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
              <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>
              <circle cx="12" cy="12" r="1" fill="currentColor"/>
            </svg>
            <span>量子 AI 助手</span>
          </div>
          <div class="panel-header-right">
            <button class="panel-btn" @click="handleClear" title="清空对话">
              <el-icon :size="16"><Delete /></el-icon>
            </button>
            <button class="panel-btn" @click="panelOpen = false" title="关闭">
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
          placeholder="问我关于量子计算的任何问题..."
          @send="sendMessage"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import { useChat } from '../composables/useChat'

const panelOpen = ref(false)
const inputRef = ref(null)

const { messages, streaming, streamingText, hasMessages, loadHistory, sendMessage, clearHistory } = useChat()

// 打开面板时加载历史
watch(panelOpen, (open) => {
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
/* FAB */
.chat-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 999;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #36cfc9, #08979c);
  color: #fff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  box-shadow: 0 4px 20px rgba(54,207,201,0.35);
  transition: transform 0.2s, box-shadow 0.2s;
}
.chat-fab:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 28px rgba(54,207,201,0.45);
}
.fab-label {
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.05em;
}

/* Panel */
.chat-panel {
  position: fixed;
  bottom: 88px;
  right: 24px;
  z-index: 998;
  width: 400px;
  height: 560px;
  background: #141e2b;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  box-shadow: 0 16px 60px rgba(0,0,0,0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.2);
  flex-shrink: 0;
}
.panel-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #e8eaed;
}
.panel-header-right { display: flex; gap: 4px; }
.panel-btn {
  width: 30px; height: 30px;
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
.panel-btn:hover { background: rgba(255,255,255,0.06); color: #c0ccda; }

/* Transition */
.panel-enter-active { transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); }
.panel-leave-active { transition: all 0.2s ease-in; }
.panel-enter-from, .panel-leave-to {
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
