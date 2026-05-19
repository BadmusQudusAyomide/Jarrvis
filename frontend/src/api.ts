import { ChatRequest, ChatResponse, StreamToken } from './types'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export async function sendMessage(message: string, sessionId: string): Promise<string> {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    } as ChatRequest),
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const data: ChatResponse = await response.json()
  return data.response
}

export async function sendMessageStream(
  message: string,
  sessionId: string,
  onToken: (token: string) => void
): Promise<void> {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    } as ChatRequest),
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.trim()) {
        try {
          const data: StreamToken = JSON.parse(line)
          if (data.token) {
            onToken(data.token)
          }
          if (data.error) {
            throw new Error(data.error)
          }
          if (data.done) {
            return
          }
        } catch (e) {
          // Ignore malformed lines
        }
      }
    }
  }
}
