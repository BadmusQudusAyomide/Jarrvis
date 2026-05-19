import { useState, useRef, useEffect } from 'react'
import { Send, Menu, Plus, MessageSquare, Cpu, Settings, Zap, Activity, HardDrive, Terminal } from 'lucide-react'
import { Message } from './types'
import { sendMessage } from './api'

interface SystemStats {
  cpu: number
  ram: number
  model: string
  status: 'online' | 'thinking' | 'offline'
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'JARVIS online. All systems operational. How can I assist you today?',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [stats, setStats] = useState<SystemStats>({
    cpu: 0,
    ram: 0,
    model: 'llama3.1:8b',
    status: 'online',
  })
  const [time, setTime] = useState(new Date())
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch('http://localhost:8000/system/stats')
        if (res.ok) {
          const data = await res.json()
          setStats(prev => ({
            ...prev,
            cpu: data.cpu_usage ? parseFloat(data.cpu_usage) : prev.cpu,
            ram: data.ram_usage ? parseFloat(data.ram_usage) : prev.ram,
          }))
        }
      } catch {}
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    setStats(prev => ({ ...prev, status: 'thinking' }))

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }
    setMessages(prev => [...prev, assistantMessage])

    try {
      const fullResponse = await sendMessage(userMessage.content, 'web-session')
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessage.id
            ? { ...msg, content: fullResponse, isStreaming: false }
            : msg
        )
      )
    } catch {
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessage.id
            ? { ...msg, content: 'Connection error. Please retry.', isStreaming: false }
            : msg
        )
      )
    } finally {
      setIsLoading(false)
      setStats(prev => ({ ...prev, status: 'online' }))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const clearChat = () => {
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: 'Session cleared. JARVIS ready.',
        timestamp: new Date(),
      },
    ])
  }

  const formatTime = (date: Date) =>
    date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })

  const formatDate = (date: Date) =>
    date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

  const formatMsgTime = (date: Date) =>
    date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })

  return (
    <div className="jarvis-root">
      {/* Ambient background effects */}
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="scanlines" />

      <div className="layout">
        {/* Sidebar */}
        <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
          <div className="sidebar-header">
            <div className="brand">
              <div className="brand-icon">
                <Cpu size={18} />
              </div>
              <div className="brand-text">
                <span className="brand-name">JARVIS</span>
                <span className="brand-sub">v2.0 · CODESTREAM</span>
              </div>
            </div>
          </div>

          <div className="sidebar-section">
            <button className="new-chat-btn" onClick={clearChat}>
              <Plus size={16} />
              <span>New Session</span>
            </button>
          </div>

          {/* System Status Panel */}
          <div className="status-panel">
            <div className="status-panel-header">
              <Activity size={12} />
              <span>SYSTEM STATUS</span>
            </div>

            <div className="status-row">
              <div className="status-label">
                <Zap size={11} />
                <span>STATUS</span>
              </div>
              <div className={`status-badge status-${stats.status}`}>
                <span className="status-dot" />
                {stats.status.toUpperCase()}
              </div>
            </div>

            <div className="status-row">
              <div className="status-label">
                <Cpu size={11} />
                <span>CPU</span>
              </div>
              <div className="stat-bar-wrap">
                <div className="stat-bar">
                  <div className="stat-bar-fill" style={{ width: `${stats.cpu}%` }} />
                </div>
                <span className="stat-val">{stats.cpu.toFixed(0)}%</span>
              </div>
            </div>

            <div className="status-row">
              <div className="status-label">
                <HardDrive size={11} />
                <span>RAM</span>
              </div>
              <div className="stat-bar-wrap">
                <div className="stat-bar">
                  <div className="stat-bar-fill ram" style={{ width: `${stats.ram}%` }} />
                </div>
                <span className="stat-val">{stats.ram.toFixed(0)}%</span>
              </div>
            </div>

            <div className="status-row">
              <div className="status-label">
                <Terminal size={11} />
                <span>MODEL</span>
              </div>
              <span className="model-badge">{stats.model}</span>
            </div>
          </div>

          <div className="sidebar-conversations">
            <div className="section-label">RECENT</div>
            <button className="convo-item convo-active">
              <MessageSquare size={13} />
              <span>Current Session</span>
            </button>
          </div>

          <div className="sidebar-footer">
            <button className="settings-btn">
              <Settings size={15} />
              <span>Settings</span>
            </button>
          </div>
        </aside>

        {/* Main area */}
        <main className="main">
          {/* Header */}
          <header className="topbar">
            <button className="menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
              <Menu size={18} />
            </button>

            <div className="topbar-title">
              <span className="topbar-name">JARVIS</span>
              <span className="topbar-dot">·</span>
              <span className="topbar-sub">Personal AI Agent</span>
            </div>

            <div className="topbar-clock">
              <span className="clock-time">{formatTime(time)}</span>
              <span className="clock-date">{formatDate(time)}</span>
            </div>
          </header>

          {/* Messages */}
          <div className="messages-area">
            <div className="messages-inner">
              {messages.map(message => (
                <div
                  key={message.id}
                  className={`message-row ${message.role === 'user' ? 'message-row-user' : 'message-row-assistant'}`}
                >
                  {message.role === 'assistant' && (
                    <div className="avatar avatar-ai">
                      <Cpu size={14} />
                    </div>
                  )}

                  <div className={`bubble ${message.role === 'user' ? 'bubble-user' : 'bubble-ai'}`}>
                    {message.role === 'assistant' && (
                      <div className="bubble-header">
                        <span className="bubble-sender">JARVIS</span>
                        <span className="bubble-time">{formatMsgTime(message.timestamp)}</span>
                      </div>
                    )}
                    <div className="bubble-content">
                      {message.content || (message.isStreaming && <span className="thinking-text">Processing...</span>)}
                      {message.isStreaming && <span className="cursor-blink" />}
                    </div>
                    {message.role === 'user' && (
                      <div className="bubble-footer-user">
                        <span className="bubble-time">{formatMsgTime(message.timestamp)}</span>
                      </div>
                    )}
                  </div>

                  {message.role === 'user' && (
                    <div className="avatar avatar-user">U</div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="input-area">
            <form onSubmit={handleSubmit} className="input-form">
              <div className={`input-box ${isLoading ? 'input-box-loading' : ''}`}>
                <div className="input-prefix">&gt;_</div>
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Enter command or query..."
                  rows={1}
                  className="input-field"
                  disabled={isLoading}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="send-btn"
                >
                  {isLoading ? (
                    <span className="spinner" />
                  ) : (
                    <Send size={16} />
                  )}
                </button>
              </div>
              <div className="input-hint">Enter to send · Shift+Enter for new line</div>
            </form>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
