import { useEffect, useState } from 'react'
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'
import { AlertCircle, Check, Moon, Sun } from 'lucide-react'

import { ApiError } from '../api/client'

export function Card({
  children,
  className = '',
  ...props
}: HTMLAttributes<HTMLElement> & {
  children: ReactNode
  className?: string
}) {
  return <section className={`card ${className}`} {...props}>{children}</section>
}

export function Button({
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`button ${className}`} {...props}>
      {children}
    </button>
  )
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function ConfidenceBadge({ value }: { value: string }) {
  const tone =
    value === 'exact' ? 'good' : value === 'inferred' ? 'info' : 'bad'
  return <Badge tone={tone}>{value}</Badge>
}

export function Skeleton({ lines = 1 }: { lines?: number }) {
  return (
    <div className="skeleton-stack" aria-label="Loading">
      {Array.from({ length: lines }, (_, index) => (
        <span className="skeleton" key={index} />
      ))}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="state-panel">
      <div className="state-icon"><Check size={20} aria-hidden="true" /></div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const problem =
    error instanceof Error
      ? error instanceof ApiError
        ? `${error.code}: ${error.message}`
        : error.message
      : 'An unexpected error occurred.'
  return (
    <div className="state-panel error-panel" role="alert">
      <div className="state-icon"><AlertCircle size={20} aria-hidden="true" /></div>
      <h2>Something went wrong</h2>
      <p>{problem}</p>
    </div>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() =>
    document.documentElement.dataset.theme === 'light' ? 'light' : 'dark',
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('onboarder-theme', theme)
    } catch {
      // Theme remains active for this page load when storage is unavailable.
    }
  }, [theme])

  const nextTheme = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      className="icon-button"
      type="button"
      aria-label={`Switch to ${nextTheme} theme`}
      onClick={() => setTheme(nextTheme)}
    >
      {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  )
}

export function AnimatedNumber({
  value,
  duration = 650,
}: {
  value: number
  duration?: number
}) {
  const [display, setDisplay] = useState(value)
  const prefersReducedMotion =
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  useEffect(() => {
    if (prefersReducedMotion) return
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min((now - start) / duration, 1)
      setDisplay(Math.round(value * progress))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [duration, prefersReducedMotion, value])

  return <span>{(prefersReducedMotion ? value : display).toLocaleString()}</span>
}
