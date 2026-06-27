<template>
  <div class="chat-messages" ref="scrollRef">
    <!-- 空状态 -->
    <div v-if="!messages.length && !streaming" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 60 60" fill="none" width="60" height="60">
          <circle cx="30" cy="30" r="28" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
          <circle cx="30" cy="30" r="12" stroke="currentColor" stroke-width="2" opacity="0.6"/>
          <circle cx="30" cy="30" r="3" fill="currentColor" opacity="0.8"/>
        </svg>
      </div>
      <h4>量子 AI 助手</h4>
      <p>我可以帮你解答关于量子电路分区、芯片映射、<br/>QASM 格式和分布式量子计算的问题。</p>
      <div class="suggestions">
        <button
          v-for="q in suggestions"
          :key="q"
          class="suggest-btn"
          @click="$emit('suggest', q)"
        >{{ q }}</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div
      v-for="(msg, idx) in messages"
      :key="idx"
      class="message"
      :class="msg.role"
    >
      <div class="msg-avatar">
        <span v-if="msg.role === 'user'" class="avatar-user">
          {{ username.charAt(0).toUpperCase() }}
        </span>
        <span v-else class="avatar-ai">
          <svg viewBox="0 0 24 24" fill="none" width="16" height="16">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>
            <circle cx="12" cy="12" r="1" fill="currentColor"/>
          </svg>
        </span>
      </div>
      <div class="msg-body">
        <div class="msg-content" v-html="renderContent(msg.content)"></div>
      </div>
    </div>

    <!-- 流式输出中的消息 -->
    <div v-if="streaming && streamingText" class="message assistant">
      <div class="msg-avatar">
        <span class="avatar-ai">
          <svg viewBox="0 0 24 24" fill="none" width="16" height="16">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>
            <circle cx="12" cy="12" r="1" fill="currentColor"/>
          </svg>
        </span>
      </div>
      <div class="msg-body">
        <div class="msg-content" v-html="renderContent(streamingText)"></div>
        <span class="typing-cursor">|</span>
      </div>
    </div>

    <!-- 等待中指示器 -->
    <div v-if="streaming && !streamingText" class="message assistant">
      <div class="msg-avatar">
        <span class="avatar-ai">
          <svg viewBox="0 0 24 24" fill="none" width="16" height="16">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/>
            <circle cx="12" cy="12" r="1" fill="currentColor"/>
          </svg>
        </span>
      </div>
      <div class="msg-body">
        <div class="typing-dots">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  streamingText: { type: String, default: '' },
})

defineEmits(['suggest'])

const scrollRef = ref(null)
const username = (() => {
  try { return JSON.parse(localStorage.getItem('user') || '{}').username || '用户' }
  catch { return '用户' }
})()

const suggestions = [
  '什么是量子电路分区？',
  '如何选择分区参数 b1 和 b2？',
  '芯片拓扑有哪几种类型？',
  'EPR 代价是什么意思？',
]

function renderContent(text) {
  if (!text) return ''
  return marked.parse(text, { breaks: true })
}

// 自动滚动到底部
function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.streamingText, scrollToBottom)
onMounted(scrollToBottom)
</script>

<style scoped>
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Empty State */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 20px;
  color: #5a6d80;
}
.empty-icon { margin-bottom: 16px; color: #36cfc9; }
.empty-state h4 { font-size: 1rem; color: #c0ccda; margin-bottom: 8px; }
.empty-state p { font-size: 0.82rem; line-height: 1.6; margin-bottom: 20px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.suggest-btn {
  background: rgba(54,207,201,0.08);
  border: 1px solid rgba(54,207,201,0.15);
  color: #36cfc9;
  font-size: 0.75rem;
  padding: 6px 14px;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
}
.suggest-btn:hover {
  background: rgba(54,207,201,0.15);
  border-color: rgba(54,207,201,0.3);
}

/* Messages */
.message {
  display: flex;
  gap: 10px;
  padding: 6px 16px;
  animation: msg-in 0.25s ease;
}
@keyframes msg-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.msg-avatar { flex-shrink: 0; padding-top: 2px; }
.avatar-user, .avatar-ai {
  width: 30px; height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  font-weight: 600;
}
.avatar-user { background: linear-gradient(135deg, #36cfc9, #08979c); color: #fff; }
.avatar-ai { background: rgba(255,255,255,0.06); color: #36cfc9; }

.msg-body { flex: 1; min-width: 0; }
.msg-content {
  font-size: 0.85rem;
  line-height: 1.7;
  color: #c0ccda;
}
/* Markdown styles */
.msg-content :deep(p) { margin: 0 0 8px; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(code) {
  background: rgba(255,255,255,0.06);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
.msg-content :deep(pre) {
  background: rgba(0,0,0,0.3);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}
.msg-content :deep(pre code) { background: transparent; padding: 0; }
.msg-content :deep(ul), .msg-content :deep(ol) { padding-left: 18px; margin: 6px 0; }
.msg-content :deep(li) { margin-bottom: 4px; }

.message.user .msg-content {
  background: rgba(54,207,201,0.1);
  padding: 10px 14px;
  border-radius: 12px 12px 0 12px;
  display: inline-block;
  max-width: 85%;
}

/* Typing */
.typing-cursor {
  color: #36cfc9;
  animation: blink 0.8s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

.typing-dots {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
}
.typing-dots span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #5a6d80;
  animation: dot-bounce 1.4s infinite ease-in-out both;
}
.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }
@keyframes dot-bounce {
  0%,80%,100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
