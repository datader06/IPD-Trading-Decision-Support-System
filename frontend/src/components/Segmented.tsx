import { useRef, type KeyboardEvent, type ReactNode } from 'react'

export interface SegmentOption<T extends string> {
  id: T
  label: ReactNode
}

interface Props<T extends string> {
  options: SegmentOption<T>[]
  value: T
  onChange: (id: T) => void
  label: string
  /** 'tab' for switching a view, 'radio' for choosing a value in a form. */
  kind?: 'tab' | 'radio'
  className?: string
  itemClassName?: string
}

/** Segmented control with the keyboard behaviour the ARIA patterns ask for: one tab stop, arrow keys / Home / End move and select. */
export default function Segmented<T extends string>({ options, value, onChange, label, kind = 'tab', className = '', itemClassName = '' }: Props<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const tab = kind === 'tab'

  const onKey = (e: KeyboardEvent, i: number) => {
    const last = options.length - 1
    const next =
      e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (i === last ? 0 : i + 1)
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (i === 0 ? last : i - 1)
      : e.key === 'Home' ? 0
      : e.key === 'End' ? last
      : -1
    if (next < 0) return
    e.preventDefault()
    onChange(options[next].id)
    refs.current[next]?.focus()
  }

  return (
    <div role={tab ? 'tablist' : 'radiogroup'} aria-label={label} className={`flex gap-1 rounded-lg bg-bg p-1 ${className}`}>
      {options.map((o, i) => {
        const on = o.id === value
        return (
          <button
            key={o.id}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role={tab ? 'tab' : 'radio'}
            {...(tab ? { 'aria-selected': on } : { 'aria-checked': on })}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors duration-200 ${on ? 'bg-white/[0.09] text-fg' : 'text-dim hover:text-fg'} ${itemClassName}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
