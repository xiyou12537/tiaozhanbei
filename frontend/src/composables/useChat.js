/**
 * useChat —— 共享的 AI 对话状态与逻辑。
 *
 * 供 ChatPage 和 ChatWidget 共同使用，
 * 管理消息列表、流式状态、发送/清空/加载历史等操作。
 */

import { ref, reactive, computed } from 'vue'
import { streamChat } from '../chatStream'
import { getChatHistory, clearChatHistory } from '../api'

// ── 单例状态（全局共享，ChatPage 和 ChatWidget 看到同一份对话）──
const messages = reactive([])
const streaming = ref(false)
const streamingText = ref('')
const loading = ref(false)

export function useChat() {
  const hasMessages = computed(() => messages.length > 0)

  /** 从后端加载对话历史 */
  async function loadHistory() {
    loading.value = true
    try {
      const { data } = await getChatHistory()
      messages.splice(0, messages.length, ...(data.messages || []))
    } catch {
      // 静默失败 —— 可能未登录
    } finally {
      loading.value = false
    }
  }

  /** 发送消息并流式接收回复 */
  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed || streaming.value) return

    // 添加用户消息
    messages.push({ role: 'user', content: trimmed })
    streaming.value = true
    streamingText.value = ''

    await streamChat(trimmed, {
      onToken(token, full) {
        streamingText.value = full
      },
      onDone(full) {
        messages.push({ role: 'assistant', content: full })
        streamingText.value = ''
        streaming.value = false
      },
      onError(err) {
        messages.push({ role: 'assistant', content: `❌ ${err}` })
        streamingText.value = ''
        streaming.value = false
      },
    })
  }

  /** 清除对话历史 */
  async function clearHistory() {
    try {
      await clearChatHistory()
    } catch {
      // 即使 API 失败也清空本地
    }
    messages.splice(0, messages.length)
    streamingText.value = ''
    streaming.value = false
  }

  return {
    messages,
    streaming,
    streamingText,
    loading,
    hasMessages,
    loadHistory,
    sendMessage,
    clearHistory,
  }
}
