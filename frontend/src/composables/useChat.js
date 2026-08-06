import { ref, reactive, computed } from 'vue'
import { streamChat } from '../chatStream'
import { getChatHistory, clearChatHistory } from '../api'

const messages = reactive([])
const streaming = ref(false)
const streamingText = ref('')
const streamingReferences = ref([])
const loading = ref(false)

export function useChat() {
  const hasMessages = computed(() => messages.length > 0)

  async function loadHistory() {
    loading.value = true
    try {
      const { data } = await getChatHistory()
      messages.splice(0, messages.length, ...(data.messages || []))
    } catch (error) {
      console.warn('加载聊天历史失败，可能是未登录或后端暂不可用。', error)
    } finally {
      loading.value = false
    }
  }

  async function sendMessage(text) {
    const trimmed = text.trim()
    if (!trimmed || streaming.value) return

    messages.push({ role: 'user', content: trimmed, references: [] })
    streaming.value = true
    streamingText.value = ''
    streamingReferences.value = []

    await streamChat(trimmed, {
      onToken(_token, full) {
        streamingText.value = full
      },
      onDone(full, references) {
        messages.push({ role: 'assistant', content: full, references: references || [] })
        streamingText.value = ''
        streamingReferences.value = []
        streaming.value = false
      },
      onError(err) {
        messages.push({
          role: 'assistant',
          content: `聊天请求失败：${err}`,
          references: [],
        })
        streamingText.value = ''
        streamingReferences.value = []
        streaming.value = false
      },
    })
  }

  async function clearHistory() {
    try {
      await clearChatHistory()
    } catch (error) {
      console.warn('清空聊天历史失败，已先清理本地状态。', error)
    }

    messages.splice(0, messages.length)
    streamingText.value = ''
    streamingReferences.value = []
    streaming.value = false
  }

  return {
    messages,
    streaming,
    streamingText,
    streamingReferences,
    loading,
    hasMessages,
    loadHistory,
    sendMessage,
    clearHistory,
  }
}
