// frontend/src/components/brand/PrismLogo.tsx
import * as React from 'react'

export type PrismState =
  | 'idle'
  | 'loading'
  | 'streaming'
  | 'thinking'
  | 'error'
  | 'mono-white'
  | 'mono-dark'

interface PrismLogoProps {
  state?: PrismState
  size?: number
  className?: string
}

// Per-state color config
const STATE_COLORS: Record<
  PrismState,
  { outline: string; ray1: string; ray2: string; ray3: string; core: string; gradId: string }
> = {
  idle:         { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  loading:      { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  streaming:    { outline: 'url(#prism-grad-violet)', ray1: '#f472b6', ray2: '#a78bfa', ray3: '#60a5fa', core: '#e0d7ff', gradId: 'prism-grad-violet' },
  thinking:     { outline: 'url(#prism-grad-amber)',  ray1: '#fbbf24', ray2: '#f59e0b', ray3: '#fde68a', core: '#fde68a', gradId: 'prism-grad-amber'  },
  error:        { outline: 'url(#prism-grad-red)',    ray1: '#f87171', ray2: '#ef4444', ray3: '#fca5a5', core: '#fca5a5', gradId: 'prism-grad-red'    },
  'mono-white': { outline: '#e0d7ff', ray1: '#ffffff', ray2: '#ffffff', ray3: '#ffffff', core: '#ffffff', gradId: '' },
  'mono-dark':  { outline: '#1a1a2e', ray1: '#1a1a2e', ray2: '#1a1a2e', ray3: '#1a1a2e', core: '#1a1a2e', gradId: '' },
}

// Per-state animation class for the main prism group
const STATE_ANIM: Record<PrismState, string> = {
  idle:         'prism-idle',
  loading:      'prism-load',
  streaming:    'prism-stream',
  thinking:     'prism-think',
  error:        'prism-error',
  'mono-white': 'prism-idle',
  'mono-dark':  'prism-idle',
}

// Per-state ray opacity (for static rays)
const RAY_OPACITY: Record<PrismState, number> = {
  idle: 0.35, loading: 0.7, streaming: 0, thinking: 0, error: 0.7,
  'mono-white': 0.4, 'mono-dark': 0.4,
}

// States that use animated rays (sweep in/out)
const ANIMATED_RAYS = new Set<PrismState>(['streaming', 'thinking'])

const KEYFRAMES = `
  /* ── Idle: slow gentle sway ── */
  .prism-idle { animation: prismIdleSway 4s ease-in-out infinite; transform-origin: 40px 40px; }
  @keyframes prismIdleSway {
    0%,100% { transform: rotate(-5deg); }
    50%     { transform: rotate(5deg); }
  }

  /* ── Loading: fast spin ── */
  .prism-load        { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; }
  .prism-load-trail1 { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; animation-delay: -0.1s; opacity: 0.25; }
  .prism-load-trail2 { animation: prismSpin 1.2s linear infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.10; }
  @keyframes prismSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

  /* ── Streaming: pendulum 1.8s ── */
  .prism-stream        { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; }
  .prism-stream-trail1 { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.1s; opacity: 0.20; }
  .prism-stream-trail2 { animation: prismPendulum 1.8s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.08; }
  @keyframes prismPendulum {
    0%   { transform: rotate(-18deg); }
    50%  { transform: rotate(18deg); }
    100% { transform: rotate(-18deg); }
  }

  /* ── Thinking: slow pendulum 3.5s ── */
  .prism-think        { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; }
  .prism-think-trail1 { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.2s; opacity: 0.20; }
  .prism-think-trail2 { animation: prismPendulum 3.5s ease-in-out infinite; transform-origin: 40px 40px; animation-delay: -0.4s; opacity: 0.08; }

  /* ── Error: shake ── */
  .prism-error { animation: prismShake 0.5s ease-in-out infinite; transform-origin: 40px 40px; }
  @keyframes prismShake {
    0%,100% { transform: translateX(0) rotate(0deg); }
    15%     { transform: translateX(-4px) rotate(-3deg); }
    35%     { transform: translateX(4px) rotate(3deg); }
    55%     { transform: translateX(-3px) rotate(-2deg); }
    75%     { transform: translateX(3px) rotate(2deg); }
    90%     { transform: translateX(-1px) rotate(-1deg); }
  }

  /* ── Animated rays (streaming + thinking) ── */
  .prism-ray-sweep   { stroke-dasharray: 70; animation: prismRaySweep var(--ray-dur, 1.8s) ease-in-out infinite; }
  .prism-ray-sweep-2 { animation-delay: 0.3s; }
  .prism-ray-sweep-3 { animation-delay: 0.6s; }
  @keyframes prismRaySweep {
    0%,100% { stroke-dashoffset: 70; opacity: 0; }
    40%,60% { stroke-dashoffset: 0; opacity: 0.9; }
  }

  /* ── Core pulses ── */
  .prism-core-stream { animation: prismCoreStream 1.8s ease-in-out infinite; }
  @keyframes prismCoreStream { 0%,100% { r: 5px; } 50% { r: 7px; filter: drop-shadow(0 0 6px #a78bfa); } }

  .prism-core-think { animation: prismCoreThink 3.5s ease-in-out infinite; }
  @keyframes prismCoreThink { 0%,100% { r: 5px; } 50% { r: 6px; filter: drop-shadow(0 0 10px #fbbf24); } }

  .prism-core-idle { animation: prismCoreIdle 4s ease-in-out infinite; }
  @keyframes prismCoreIdle { 0%,100% { r: 4px; } 50% { r: 5.5px; } }
`

export function PrismLogo({ state = 'idle', size = 64, className }: PrismLogoProps) {
  const c = STATE_COLORS[state]
  const animClass = STATE_ANIM[state]
  const useAnimRays = ANIMATED_RAYS.has(state)
  const rayOpacity = RAY_OPACITY[state]
  const strokeWidth = size <= 16 ? 3 : 2
  const coreR = size <= 16 ? 7 : state === 'streaming' || state === 'thinking' ? 5 : 4
  const rayDur = state === 'thinking' ? '3.5s' : '1.8s'

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="prism-grad-violet" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#f472b6" />
          <stop offset="50%"  stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#60a5fa" />
        </linearGradient>
        <linearGradient id="prism-grad-amber" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#fbbf24" />
          <stop offset="50%"  stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#fde68a" />
        </linearGradient>
        <linearGradient id="prism-grad-red" x1="12" y1="8" x2="68" y2="72" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#f87171" />
          <stop offset="50%"  stopColor="#ef4444" />
          <stop offset="100%" stopColor="#fca5a5" />
        </linearGradient>
        <style>{KEYFRAMES}</style>
      </defs>

      {/* Ghost trails for loading */}
      {state === 'loading' && (
        <>
          <g className="prism-load-trail2">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
          <g className="prism-load-trail1">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
        </>
      )}

      {/* Ghost trails for streaming */}
      {state === 'streaming' && (
        <>
          <g className="prism-stream-trail2">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
          <g className="prism-stream-trail1">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
        </>
      )}

      {/* Ghost trails for thinking */}
      {state === 'thinking' && (
        <>
          <g className="prism-think-trail2">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
          <g className="prism-think-trail1">
            <polygon points="40,8 68,40 40,72 12,40" fill="none" stroke={c.outline} strokeWidth={strokeWidth} />
          </g>
        </>
      )}

      {/* Main prism outline */}
      <g className={animClass}>
        <polygon
          points="40,8 68,40 40,72 12,40"
          fill="none"
          stroke={c.outline}
          strokeWidth={strokeWidth}
        />
      </g>

      {/* Rays */}
      {useAnimRays ? (
        <>
          <line x1="40" y1="8" x2="68" y2="40" stroke={c.ray1} strokeWidth={strokeWidth}
            className="prism-ray-sweep"
            style={{ '--ray-dur': rayDur } as React.CSSProperties} />
          <line x1="40" y1="8" x2="40" y2="72" stroke={c.ray2} strokeWidth={strokeWidth}
            className="prism-ray-sweep prism-ray-sweep-2"
            style={{ '--ray-dur': rayDur } as React.CSSProperties} />
          <line x1="40" y1="8" x2="12" y2="40" stroke={c.ray3} strokeWidth={strokeWidth}
            className="prism-ray-sweep prism-ray-sweep-3"
            style={{ '--ray-dur': rayDur } as React.CSSProperties} />
        </>
      ) : (
        <>
          <line x1="40" y1="8" x2="68" y2="40" stroke={c.ray1} strokeWidth={strokeWidth} opacity={rayOpacity} />
          <line x1="40" y1="8" x2="40" y2="72" stroke={c.ray2} strokeWidth={strokeWidth} opacity={rayOpacity} />
          <line x1="40" y1="8" x2="12" y2="40" stroke={c.ray3} strokeWidth={strokeWidth} opacity={rayOpacity} />
        </>
      )}

      {/* Core dot */}
      <circle
        cx="40"
        cy="40"
        r={coreR}
        fill={c.core}
        className={
          state === 'streaming' ? 'prism-core-stream' :
          state === 'thinking'  ? 'prism-core-think'  :
          state === 'idle'      ? 'prism-core-idle'   : undefined
        }
      />
    </svg>
  )
}
