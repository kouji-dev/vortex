// frontend/src/components/brand/VortexWordmark.tsx
import * as React from 'react'

export type WordmarkVariant = 'gradient' | 'white' | 'dark'

interface VortexWordmarkProps {
  variant?: WordmarkVariant
  /** Font size in px. Default 17. Use ≥28 for gradient variant. */
  size?: number
  className?: string
}

const VARIANT_STYLE: Record<WordmarkVariant, React.CSSProperties> = {
  gradient: {
    background: 'linear-gradient(90deg, #f472b6, #a78bfa, #60a5fa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  white: { color: '#e0d7ff' },
  dark:  { color: '#1a1a2e' },
}

export function VortexWordmark({ variant = 'white', size = 17, className }: VortexWordmarkProps) {
  return (
    <span
      className={className}
      style={{
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        fontWeight: 700,
        fontSize: size,
        letterSpacing: '-0.03em',
        lineHeight: 1,
        userSelect: 'none',
        ...VARIANT_STYLE[variant],
      }}
    >
      Vortex
    </span>
  )
}
