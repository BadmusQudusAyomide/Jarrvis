import { useEffect, useRef } from 'react'

export type VoiceState = 'idle' | 'listening' | 'speaking'

interface VoiceOrbProps {
  analyser: AnalyserNode | null
  state: VoiceState
  size?: number
}

const BAR_COUNT = 48

const STATE_COLOR: Record<VoiceState, string> = {
  idle: '0, 180, 255',
  listening: '0, 212, 255',
  speaking: '120, 210, 255',
}

export default function VoiceOrb({ analyser, state, size = 220 }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef = useRef<number>()
  const idlePhaseRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.scale(dpr, dpr)

    const dataArray = analyser ? new Uint8Array(analyser.frequencyBinCount) : null
    const center = size / 2
    const baseRadius = size * 0.22
    const maxBarLen = size * 0.24
    const color = STATE_COLOR[state]

    const draw = () => {
      ctx.clearRect(0, 0, size, size)

      let amplitude = 0
      let levels: number[]

      if (analyser && dataArray && state !== 'idle') {
        analyser.getByteFrequencyData(dataArray)
        levels = new Array(BAR_COUNT)
        const bins = Math.floor(dataArray.length / BAR_COUNT)
        for (let i = 0; i < BAR_COUNT; i++) {
          let sum = 0
          for (let b = 0; b < bins; b++) sum += dataArray[i * bins + b]
          const v = sum / bins / 255
          levels[i] = v
          amplitude += v
        }
        amplitude /= BAR_COUNT
      } else {
        // Gentle idle "breathing" animation when nothing is listening/speaking
        idlePhaseRef.current += 0.02
        levels = new Array(BAR_COUNT)
        for (let i = 0; i < BAR_COUNT; i++) {
          const v = 0.12 + 0.06 * Math.sin(idlePhaseRef.current + i * 0.35)
          levels[i] = v
        }
        amplitude = 0.15 + 0.05 * Math.sin(idlePhaseRef.current * 0.7)
      }

      // Outer radiating bars
      for (let i = 0; i < BAR_COUNT; i++) {
        const angle = (i / BAR_COUNT) * Math.PI * 2
        const len = baseRadius + levels[i] * maxBarLen
        const x1 = center + Math.cos(angle) * baseRadius
        const y1 = center + Math.sin(angle) * baseRadius
        const x2 = center + Math.cos(angle) * len
        const y2 = center + Math.sin(angle) * len

        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.strokeStyle = `rgba(${color}, ${0.35 + levels[i] * 0.65})`
        ctx.lineWidth = 2.5
        ctx.lineCap = 'round'
        ctx.stroke()
      }

      // Glowing core
      const coreRadius = baseRadius * (0.55 + amplitude * 0.5)
      const gradient = ctx.createRadialGradient(center, center, 0, center, center, coreRadius * 1.6)
      gradient.addColorStop(0, `rgba(${color}, ${0.5 + amplitude * 0.4})`)
      gradient.addColorStop(0.6, `rgba(${color}, ${0.15 + amplitude * 0.2})`)
      gradient.addColorStop(1, 'rgba(0, 0, 0, 0)')

      ctx.beginPath()
      ctx.arc(center, center, coreRadius * 1.6, 0, Math.PI * 2)
      ctx.fillStyle = gradient
      ctx.fill()

      ctx.beginPath()
      ctx.arc(center, center, coreRadius * 0.5, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${color}, 0.9)`
      ctx.shadowColor = `rgba(${color}, 0.8)`
      ctx.shadowBlur = 20
      ctx.fill()
      ctx.shadowBlur = 0

      rafRef.current = requestAnimationFrame(draw)
    }

    draw()
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [analyser, state, size])

  return <canvas ref={canvasRef} style={{ width: size, height: size }} className="voice-orb-canvas" />
}
