/**
 * SSE 流式读取工具 —— 发送聊天消息并流式接收 AI 回复。
 *
 * 使用 fetch + ReadableStream 解析 Server-Sent Events，
 * 支持 token 级别的实时渲染。
 */

export async function streamChat(message, { onToken, onDone, onError }) {
  const token = localStorage.getItem('token')
  if (!token) {
    onError && onError('未登录，请先登录')
    return
  }

  let controller = new AbortController()

  try {
    const response = await fetch('/api/chat/send', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ message }),
      signal: controller.signal,
    })

    if (!response.ok) {
      const body = await response.text()
      let errMsg = `请求失败 (${response.status})`
      try {
        const err = JSON.parse(body)
        errMsg = err.detail || errMsg
      } catch {}
      onError && onError(errMsg)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let fullContent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim()
          if (dataStr === '[DONE]') continue

          try {
            const data = JSON.parse(dataStr)
            if (data.token) {
              fullContent += data.token
              onToken && onToken(data.token, fullContent)
            } else if (data.error) {
              onError && onError(data.error)
              return
            } else if (data.done) {
              onDone && onDone(data.content || fullContent, data.references || [])
              return
            }
          } catch {
            // skip unparseable lines
          }
        }
      }
    }

    // Stream ended without explicit done event
    onDone && onDone(fullContent, [])

  } catch (err) {
    if (err.name === 'AbortError') return
    onError && onError(err.message || '网络请求失败')
  }

  // 返回 abort 函数以便外部取消
  return () => controller.abort()
}
