import { ChatRequest, ChatResponse, StreamToken, SystemStatsResponse } from './types'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export function getWakeWordWsUrl(): string {
  return API_URL.replace(/^http/, 'ws') + '/voice/wakeword'
}

export async function sendMessage(message: string, sessionId: string): Promise<ChatResponse> {
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

  return response.json()
}

export async function clearSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_URL}/chat/clear?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
}

export async function getSystemStats(): Promise<SystemStatsResponse> {
  const response = await fetch(`${API_URL}/system/stats`)
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  return response.json()
}

export async function transcribeAudio(blob: Blob): Promise<string> {
  const form = new FormData()
  form.append('file', blob, 'recording.webm')
  const response = await fetch(`${API_URL}/voice/transcribe`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  const data = await response.json()
  if (data.error) {
    throw new Error(data.error)
  }
  return data.text as string
}

export async function synthesizeSpeech(text: string): Promise<Blob> {
  const response = await fetch(`${API_URL}/voice/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`HTTP error! status: ${response.status} ${detail}`)
  }
  return response.blob()
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
