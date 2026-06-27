<template>
  <div class="chat-input-area">
    <div class="input-row">
      <textarea
        ref="inputRef"
        v-model="text"
        class="chat-textarea"
        :placeholder="placeholder"
        :disabled="disabled"
        :rows="1"
        @input="autoResize"
        @keydown.enter.exact.prevent="handleSend"
      ></textarea>
      <button
        class="send-btn"
        :class="{ active: text.trim() && !disabled }"
        :disabled="!text.trim() || disabled"
        @click="handleSend"
      >
        <el-icon :size="18"><Promotion /></el-icon>
      </button>
    </div>
    <p class="input-hint" v-if="!disabled">Enter 发送 · Shift+Enter 换行</p>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

defineProps({
  placeholder: { type: String, default: '输入你的问题...' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])

const text = ref('')
const inputRef = ref(null)

function autoResize() {
  const el = inputRef.value
  if (el) {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }
}

function handleSend() {
  const trimmed = text.value.trim()
  if (!trimmed) return
  emit('send', trimmed)
  text.value = ''
  nextTick(() => {
    const el = inputRef.value
    if (el) { el.style.height = 'auto' }
  })
}

defineExpose({ focus: () => inputRef.value?.focus() })
</script>

<style scoped>
.chat-input-area {
  padding: 12px 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
  background: rgba(0,0,0,0.15);
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.chat-textarea {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  color: #e8eaed;
  font-size: 0.85rem;
  font-family: inherit;
  padding: 10px 14px;
  resize: none;
  outline: none;
  line-height: 1.5;
  max-height: 120px;
  transition: border-color 0.2s;
}
.chat-textarea:focus { border-color: rgba(54,207,201,0.3); }
.chat-textarea::placeholder { color: #4a5d70; }
.chat-textarea:disabled { opacity: 0.5; }
.send-btn {
  width: 38px; height: 38px;
  border-radius: 10px;
  border: none;
  background: rgba(255,255,255,0.06);
  color: #5a6d80;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.send-btn.active { background: rgba(54,207,201,0.15); color: #36cfc9; }
.send-btn.active:hover { background: rgba(54,207,201,0.25); }
.send-btn:disabled { cursor: not-allowed; }
.input-hint {
  font-size: 0.65rem;
  color: #3a4d60;
  margin-top: 6px;
  text-align: center;
}
</style>
