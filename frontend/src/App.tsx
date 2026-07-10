import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Menu, Plus, MessageSquare, Cpu, Settings, Zap, Activity, HardDrive, Terminal, Mic, Square, Volume2, VolumeX } from 'lucide-react'
import { Message } from './types'
import { sendMessage, clearSession, getSystemStats, transcribeAudio, synthesizeSpeech, getWakeWordWsUrl } from './api'
import VoiceOrb, { VoiceState } from './VoiceOrb'

interface SystemStats {
  cpu: number
  ram: number
  model: string
  status: 'online' | 'thinking' | 'offline'
}

const SESSION_STORAGE_KEY = 'jarvis_session_id'
const SHOW_TRANSCRIPT_KEY = 'jarvis_show_transcript'
const HANDS_FREE_KEY = 'jarvis_hands_free'
const GREETING = 'JARVIS online. All systems operational. How can I assist you today?'

function getOrCreateSessionId(): string {
  let id = localStorage.getItem(SESSION_STORAGE_KEY)
  if (!id) {
    id = `web_${crypto.randomUUID()}`
    localStorage.setItem(SESSION_STORAGE_KEY, id)
  }
  return id
}

function getStoredShowTranscript(): boolean {
  const saved = localStorage.getItem(SHOW_TRANSCRIPT_KEY)
  return saved === null ? true : saved === 'true'
}

function App() {
  const [sessionId] = useState<string>(getOrCreateSessionId)
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
    model: '—',
    status: 'online',
  })
  const [time, setTime] = useState(new Date())
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // --- Voice: mic input, TTS playback, and the live audio-reactive orb ---
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(true)
  const [voiceAnalyser, setVoiceAnalyser] = useState<AnalyserNode | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [showTranscript, setShowTranscript] = useState<boolean>(getStoredShowTranscript)
  const [showSettings, setShowSettings] = useState(false)
  const [handsFreeMode, setHandsFreeMode] = useState<boolean>(() => localStorage.getItem(HANDS_FREE_KEY) === 'true')

  const audioCtxRef = useRef<AudioContext | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null)
  const vadRafRef = useRef<number>()
  const hasSpokenRef = useRef(false)
  const silenceStartRef = useRef<number | null>(null)
  const recordingStartRef = useRef(0)

  // Wake word / hands-free
  const wakeWordWsRef = useRef<WebSocket | null>(null)
  const wakeWordAudioCtxRef = useRef<AudioContext | null>(null)
  const wakeWordProcessorRef = useRef<ScriptProcessorNode | null>(null)
  const handsFreeStreamOwnedRef = useRef(false)

  // Kept in sync with state via effects below so closures created once (e.g.
  // the wake-word WebSocket's onmessage handler) always read live values
  // instead of freezing whatever the state was when they were created.
  const autoSpeakRef = useRef(autoSpeak)
  const isLoadingRef = useRef(isLoading)
  const busyRef = useRef(false) // true whenever voice pipeline is not idle/available

  const getAudioCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext()
    }
    return audioCtxRef.current
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    localStorage.setItem(SHOW_TRANSCRIPT_KEY, String(showTranscript))
  }, [showTranscript])

  useEffect(() => { autoSpeakRef.current = autoSpeak }, [autoSpeak])
  useEffect(() => { isLoadingRef.current = isLoading }, [isLoading])
  useEffect(() => {
    busyRef.current = voiceState !== 'idle' || isTranscribing
  }, [voiceState, isTranscribing])

  // Greet once when the app opens
  useEffect(() => {
    const t = setTimeout(() => {
      if (autoSpeak) speak(GREETING)
    }, 500)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await getSystemStats()
        setStats(prev => ({
          ...prev,
          cpu: data.cpu_usage ? parseFloat(data.cpu_usage) : prev.cpu,
          ram: data.ram_usage ? parseFloat(data.ram_usage) : prev.ram,
          model: data.model || prev.model,
        }))
      } catch {
        setStats(prev => ({ ...prev, status: 'offline' }))
      }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [])

  const speak = async (text: string) => {
    if (!text.trim()) return
    try {
      setVoiceError(null)
      const blob = await synthesizeSpeech(text)
      const url = URL.createObjectURL(blob)

      // Stop anything already playing before starting the new clip
      if (playbackAudioRef.current) {
        playbackAudioRef.current.pause()
      }

      const audio = new Audio(url)
      playbackAudioRef.current = audio

      const ctx = getAudioCtx()
      const source = ctx.createMediaElementSource(audio)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 128
      source.connect(analyser)
      analyser.connect(ctx.destination)
      setVoiceAnalyser(analyser)
      setVoiceState('speaking')

      audio.onended = () => {
        setVoiceState('idle')
        setVoiceAnalyser(null)
        URL.revokeObjectURL(url)
      }
      audio.onerror = () => {
        setVoiceState('idle')
        setVoiceAnalyser(null)
        URL.revokeObjectURL(url)
      }
      await audio.play()
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      setVoiceError(`Couldn't speak reply: ${detail}`)
      setVoiceState('idle')
    }
  }

  // Voice activity detection tuning — RMS is measured on a 0-127 scale
  // (deviation from the 128 silence midpoint in time-domain byte data).
  const SPEECH_RMS_THRESHOLD = 8      // above this = you're actively talking
  const SILENCE_RMS_THRESHOLD = 5     // below this = quiet (has hysteresis vs the speech threshold)
  const SILENCE_STOP_MS = 1300        // stop after this long of quiet following speech
  const MAX_INITIAL_SILENCE_MS = 6000 // give up if nothing was said at all
  const MAX_RECORDING_MS = 25000      // hard cap regardless of VAD

  const stopVadLoop = () => {
    if (vadRafRef.current) {
      cancelAnimationFrame(vadRafRef.current)
      vadRafRef.current = undefined
    }
  }

  const startRecording = async () => {
    try {
      setVoiceError(null)
      // Reuse the persistent hands-free mic stream if one is already open,
      // instead of requesting a second concurrent stream.
      let stream = micStreamRef.current
      if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        micStreamRef.current = stream
      }

      const ctx = getAudioCtx()
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      source.connect(analyser)
      setVoiceAnalyser(analyser)
      setVoiceState('listening')

      audioChunksRef.current = []
      hasSpokenRef.current = false
      silenceStartRef.current = null
      recordingStartRef.current = Date.now()

      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = e => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }
      recorder.start()
      mediaRecorderRef.current = recorder

      // Watch mic volume every frame; auto-stop once you've spoken and gone quiet.
      const timeDomain = new Uint8Array(analyser.fftSize)
      const monitor = () => {
        analyser.getByteTimeDomainData(timeDomain)
        let sumSquares = 0
        for (let i = 0; i < timeDomain.length; i++) {
          const deviation = timeDomain[i] - 128
          sumSquares += deviation * deviation
        }
        const rms = Math.sqrt(sumSquares / timeDomain.length)
        const elapsed = Date.now() - recordingStartRef.current

        if (rms > SPEECH_RMS_THRESHOLD) {
          hasSpokenRef.current = true
          silenceStartRef.current = null
        } else if (rms < SILENCE_RMS_THRESHOLD && hasSpokenRef.current) {
          if (silenceStartRef.current === null) silenceStartRef.current = Date.now()
          if (Date.now() - silenceStartRef.current > SILENCE_STOP_MS) {
            stopRecording()
            return
          }
        }

        if (!hasSpokenRef.current && elapsed > MAX_INITIAL_SILENCE_MS) {
          stopRecording()
          return
        }
        if (elapsed > MAX_RECORDING_MS) {
          stopRecording()
          return
        }

        vadRafRef.current = requestAnimationFrame(monitor)
      }
      vadRafRef.current = requestAnimationFrame(monitor)
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      setVoiceError(`Couldn't access microphone: ${detail}`)
      setVoiceState('idle')
    }
  }

  const stopRecording = () => {
    const recorder = mediaRecorderRef.current
    if (!recorder) return

    stopVadLoop()
    const spoke = hasSpokenRef.current

    recorder.onstop = async () => {
      // Hands-free mode keeps the mic stream alive between commands so it
      // can keep listening for the next wake word; tap-to-talk releases it.
      if (!handsFreeStreamOwnedRef.current) {
        micStreamRef.current?.getTracks().forEach(t => t.stop())
        micStreamRef.current = null
      }
      setVoiceAnalyser(null)
      setVoiceState('idle')

      const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
      audioChunksRef.current = []

      // Nothing but silence/noise was captured — don't send it to Whisper,
      // which reliably hallucinates plausible-sounding text on empty audio.
      if (blob.size === 0 || !spoke) return

      setIsTranscribing(true)
      try {
        const text = await transcribeAudio(blob)
        if (text.trim()) {
          await sendUserMessage(text)
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err)
        setVoiceError(`Transcription failed: ${detail}`)
      } finally {
        setIsTranscribing(false)
      }
    }
    recorder.stop()
    mediaRecorderRef.current = null
  }

  const toggleRecording = () => {
    if (voiceState === 'listening') {
      stopRecording()
    } else if (voiceState === 'idle' && !isLoading) {
      startRecording()
    }
  }

  const stopHandsFreeListening = () => {
    handsFreeStreamOwnedRef.current = false

    if (wakeWordProcessorRef.current) {
      wakeWordProcessorRef.current.disconnect()
      wakeWordProcessorRef.current = null
    }
    if (wakeWordAudioCtxRef.current) {
      wakeWordAudioCtxRef.current.close().catch(() => {})
      wakeWordAudioCtxRef.current = null
    }
    if (wakeWordWsRef.current) {
      wakeWordWsRef.current.close()
      wakeWordWsRef.current = null
    }
    // Only release the mic if nothing else (an active command recording) is using it
    if (!busyRef.current) {
      micStreamRef.current?.getTracks().forEach(t => t.stop())
      micStreamRef.current = null
    }
  }

  const startHandsFreeListening = async () => {
    try {
      setVoiceError(null)
      let stream = micStreamRef.current
      if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        micStreamRef.current = stream
      }
      handsFreeStreamOwnedRef.current = true

      const ws = new WebSocket(getWakeWordWsUrl())
      wakeWordWsRef.current = ws

      ws.onmessage = event => {
        try {
          const data = JSON.parse(event.data)
          if (data.detected && !busyRef.current) {
            startRecording()
          }
        } catch {
          // ignore malformed messages
        }
      }
      ws.onerror = () => {
        setVoiceError('Wake-word listener lost connection')
      }

      // openWakeWord needs 16-bit 16kHz mono PCM — run a dedicated 16kHz
      // AudioContext so no manual resampling is needed.
      const ctx = new AudioContext({ sampleRate: 16000 })
      wakeWordAudioCtxRef.current = ctx
      const source = ctx.createMediaStreamSource(stream)
      const processor = ctx.createScriptProcessor(4096, 1, 1)
      wakeWordProcessorRef.current = processor

      processor.onaudioprocess = e => {
        if (busyRef.current) return
        if (ws.readyState !== WebSocket.OPEN) return
        const input = e.inputBuffer.getChannelData(0)
        const pcm16 = new Int16Array(input.length)
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]))
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
        }
        ws.send(pcm16.buffer)
      }

      // ScriptProcessorNode only fires its callback while connected to a
      // destination — route through a silent gain so nothing is audible.
      const silentGain = ctx.createGain()
      silentGain.gain.value = 0
      source.connect(processor)
      processor.connect(silentGain)
      silentGain.connect(ctx.destination)
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      setVoiceError(`Couldn't start hands-free listening: ${detail}`)
      setHandsFreeMode(false)
    }
  }

  useEffect(() => {
    localStorage.setItem(HANDS_FREE_KEY, String(handsFreeMode))
    if (handsFreeMode) {
      startHandsFreeListening()
    } else {
      stopHandsFreeListening()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handsFreeMode])

  const sendUserMessage = async (text: string) => {
    if (!text.trim() || isLoadingRef.current) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text.trim(),
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
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
      const result = await sendMessage(userMessage.content, sessionId)
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessage.id
            ? { ...msg, content: result.response, isStreaming: false, requiresConfirmation: result.requires_confirmation }
            : msg
        )
      )
      if (autoSpeakRef.current) {
        speak(result.response)
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      setMessages(prev =>
        prev.map(msg =>
          msg.id === assistantMessage.id
            ? { ...msg, content: `Connection error: ${detail}`, isStreaming: false }
            : msg
        )
      )
    } finally {
      setIsLoading(false)
      setStats(prev => ({ ...prev, status: 'online' }))
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = input
    setInput('')
    await sendUserMessage(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const clearChat = async () => {
    try {
      await clearSession(sessionId)
      setMessages([
        {
          id: 'welcome',
          role: 'assistant',
          content: 'Session cleared. JARVIS ready.',
          timestamp: new Date(),
        },
      ])
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err)
      setMessages(prev => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: `Couldn't clear the session: ${detail}`,
          timestamp: new Date(),
        },
      ])
    }
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
            <button className="settings-btn" onClick={() => setShowSettings(true)}>
              <Settings size={15} />
              <span>Settings</span>
            </button>
          </div>
        </aside>

        {showSettings && (
          <div className="settings-overlay" onClick={() => setShowSettings(false)}>
            <div className="settings-panel" onClick={e => e.stopPropagation()}>
              <div className="settings-panel-header">
                <span>SETTINGS</span>
                <button className="settings-close-btn" onClick={() => setShowSettings(false)}>×</button>
              </div>

              <label className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Show transcript</span>
                  <span className="settings-row-desc">Keep a scrolling text log visible below the voice orb</span>
                </div>
                <input
                  type="checkbox"
                  checked={showTranscript}
                  onChange={e => setShowTranscript(e.target.checked)}
                />
              </label>

              <label className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Speak replies aloud</span>
                  <span className="settings-row-desc">Jarvis reads its responses out loud as it replies</span>
                </div>
                <input
                  type="checkbox"
                  checked={autoSpeak}
                  onChange={e => setAutoSpeak(e.target.checked)}
                />
              </label>

              <label className="settings-row">
                <div className="settings-row-text">
                  <span className="settings-row-title">Hands-free ("Hey Jarvis")</span>
                  <span className="settings-row-desc">Mic stays on and listens for the wake word — no tapping needed</span>
                </div>
                <input
                  type="checkbox"
                  checked={handsFreeMode}
                  onChange={e => setHandsFreeMode(e.target.checked)}
                />
              </label>
            </div>
          </div>
        )}

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

            <button
              className={`speak-toggle-btn ${autoSpeak ? 'speak-toggle-on' : ''}`}
              onClick={() => setAutoSpeak(v => !v)}
              title={autoSpeak ? 'Voice replies on — click to mute' : 'Voice replies off — click to unmute'}
            >
              {autoSpeak ? <Volume2 size={16} /> : <VolumeX size={16} />}
            </button>

            <div className="topbar-clock">
              <span className="clock-time">{formatTime(time)}</span>
              <span className="clock-date">{formatDate(time)}</span>
            </div>
          </header>

          {/* Voice hero — the main event */}
          <div className={`voice-hero ${showTranscript ? 'voice-hero-compact' : 'voice-hero-full'}`}>
            <button
              type="button"
              className="voice-hero-orb-btn"
              onClick={toggleRecording}
              disabled={(isLoading && voiceState !== 'listening') || isTranscribing || voiceState === 'speaking'}
              title={voiceState === 'listening' ? 'Stop recording' : 'Tap to speak to Jarvis'}
            >
              <VoiceOrb analyser={voiceAnalyser} state={voiceState} size={showTranscript ? 180 : 280} />
            </button>
            <div className="voice-hero-status">
              {voiceState === 'listening'
                ? 'LISTENING…'
                : voiceState === 'speaking'
                ? 'SPEAKING…'
                : isTranscribing
                ? 'TRANSCRIBING…'
                : handsFreeMode
                ? "SAY “HEY JARVIS”"
                : 'TAP THE ORB TO SPEAK'}
            </div>
            {voiceError && (
              <div className="voice-error-toast" onClick={() => setVoiceError(null)}>
                {voiceError}
              </div>
            )}
          </div>

          {/* Messages / transcript */}
          <div className={`messages-area ${showTranscript ? '' : 'messages-area-hidden'}`}>
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

                  <div
                    className={`bubble ${message.role === 'user' ? 'bubble-user' : 'bubble-ai'} ${
                      message.requiresConfirmation ? 'bubble-confirm' : ''
                    }`}
                  >
                    {message.role === 'assistant' && (
                      <div className="bubble-header">
                        <span className="bubble-sender">
                          {message.requiresConfirmation ? 'JARVIS · CONFIRMATION NEEDED' : 'JARVIS'}
                        </span>
                        <span className="bubble-time">{formatMsgTime(message.timestamp)}</span>
                      </div>
                    )}
                    <div className="bubble-content">
                      {message.content || (message.isStreaming && <span className="thinking-text">Processing...</span>)}
                      {message.isStreaming && <span className="cursor-blink" />}
                    </div>
                    {message.requiresConfirmation && !message.isStreaming && (
                      <div className="bubble-confirm-actions">
                        <button
                          type="button"
                          className="confirm-btn confirm-yes"
                          disabled={isLoading}
                          onClick={() => sendUserMessage('yes')}
                        >
                          Yes, proceed
                        </button>
                        <button
                          type="button"
                          className="confirm-btn confirm-no"
                          disabled={isLoading}
                          onClick={() => sendUserMessage('no')}
                        >
                          No, cancel
                        </button>
                      </div>
                    )}
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
                  type="button"
                  onClick={toggleRecording}
                  disabled={(isLoading && voiceState !== 'listening') || isTranscribing || voiceState === 'speaking'}
                  className={`mic-btn ${voiceState === 'listening' ? 'mic-btn-active' : ''}`}
                  title={voiceState === 'listening' ? 'Stop recording' : 'Speak to Jarvis'}
                >
                  {voiceState === 'listening' ? <Square size={15} /> : <Mic size={16} />}
                </button>
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
              <div className="input-hint">Enter to send · Shift+Enter for new line · Mic to talk</div>
            </form>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
