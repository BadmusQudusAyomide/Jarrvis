export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isStreaming?: boolean
}

export interface ChatState {
  messages: Message[]
  isLoading: boolean
  sessionId: string
}

export interface ChatRequest {
  message: string
  session_id: string
}

export interface ChatResponse {
  response: string
}

export interface StreamToken {
  token?: string
  error?: string
  done?: boolean
}
