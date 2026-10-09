import { useGSAP } from '@gsap/react'
import { MagnifyingGlass, WarningCircle } from '@phosphor-icons/react'
import gsap from 'gsap'
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import Baselines from '../components/Baselines'
import CandleChart, { type Level } from '../components/CandleChart'
import Nav from '../components/Nav'
import Segmented from '../components/Segmented'
import TradeCalculator from '../components/TradeCalculator'
import TradesTable from '../components/TradesTable'
import { FALLBACK_SYMBOLS, SymbolError, fetchCandles, searchSymbols, type CandleResult, type Interval, type SymbolHit } from '../lib/api'
import { parseNum, type ZoneType } from '../lib/sizing'

const INTERVALS: { id: Interval; label: string }[] = [
  { id: '15m', label: '15m' },
  { id: '60m', label: '60m' },
  { id: '1d', label: 'Daily' },
]

const round2 = (n: number) => (Math.round(n * 100) / 100).toString()

export default function Desk() {
  const root = useRef<HTMLDivElement>(null)
  const [symbol, setSymbol] = useState('RELIANCE')
  const [query, setQuery] = useState('RELIANCE')
  const [hits, setHits] = useState<SymbolHit[]>(FALLBACK_SYMBOLS)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [interval, setIntervalId] = useState<Interval>('15m')
  const [result, setResult] = useState<CandleResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const needsLevels = useRef(true)
  const [type, setType] = useState<ZoneType>('demand')
  const [entry, setEntry] = useState('')
  const [stop, setStop] = useState('')

  useGSAP(
    () => {
      gsap.matchMedia().add('(prefers-reduced-motion: no-preference)', () => {
        gsap.from('.panel', { opacity: 0, y: 24, duration: 0.6, stagger: 0.08, ease: 'power3.out' })
      })
    },
    { scope: root },
  )

  // Candles: reload on symbol or interval change.
  useEffect(() => {
    const ac = new AbortController()
    setLoading(true)
    setError(null)
    fetchCandles(symbol, interval, ac.signal)
      .then((r) => {
        setResult(r)
        setLoading(false)
      })
      .catch((e) => {
        if (ac.signal.aborted) return
        setLoading(false)
        if (e instanceof SymbolError) {
          setResult(null)
          setError(e.message)
        }
      })
    return () => ac.abort()
  }, [symbol, interval])

  // A different symbol means different prices: levels restart from its last price once. Changing the interval keeps them.
  useEffect(() => {
    needsLevels.current = true
  }, [symbol])

  // Symbol suggestions (debounced).
  useEffect(() => {
    const ac = new AbortController()
    const t = setTimeout(
      () =>
        searchSymbols(query, ac.signal)
          .then((h) => {
            setHits(h)
            setActive(-1)
          })
          .catch(() => undefined),
      200,
    )
    return () => {
      clearTimeout(t)
      ac.abort()
    }
  }, [query])

  const last = result?.candles.at(-1)?.close ?? null

  const resetLevels = useCallback(
    (t: ZoneType) => {
      if (last === null) return
      setEntry(round2(last))
      setStop(round2(t === 'demand' ? last * 0.99 : last * 1.01))
    },
    [last],
  )

  useEffect(() => {
    if (last !== null && needsLevels.current) {
      needsLevels.current = false
      resetLevels(type)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [last])

  const levels: Level[] = useMemo(() => {
    const e = parseNum(entry)
    const s = parseNum(stop)
    if (!(e > 0) || !(s > 0)) return []
    const risk = Math.abs(e - s)
    const valid = type === 'demand' ? s < e : s > e
    const target = e + (type === 'demand' ? 2 : -2) * risk
    if (!valid || target <= 0) return []
    return [
      { price: target, title: 'Target', color: '#34d399' },
      { price: e, title: 'Entry', color: '#e6ebf2' },
      { price: s, title: 'Stop', color: '#fb7185' },
    ]
  }, [entry, stop, type])

  const choose = (s: string) => {
    setSymbol(s)
    setQuery(s)
    setOpen(false)
    setActive(-1)
  }

  const onSymbolKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!hits.length) return
      e.preventDefault()
      setOpen(true)
      setActive((a) => (e.key === 'ArrowDown' ? (a + 1) % hits.length : a <= 0 ? hits.length - 1 : a - 1))
    } else if (e.key === 'Enter' && open && active >= 0 && hits[active]) {
      e.preventDefault()
      choose(hits[active].symbol)
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActive(-1)
    }
  }

  const listOpen = open && query.trim().length >= 0 && (hits.length > 0 || query.trim().length > 0)

  return (
    <div ref={root} className="min-h-dvh">
      <div className="ambient" aria-hidden="true" />
      <Nav />
      <main className="mx-auto grid max-w-[1400px] grid-cols-[minmax(0,1fr)] gap-4 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          <section className="panel glass rounded-2xl p-4 sm:p-5" aria-label="Price chart">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <div className="relative">
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (query.trim()) choose(query.trim().toUpperCase())
                  }}
                  role="search"
                >
                  <label htmlFor="sym" className="sr-only">
                    NSE symbol
                  </label>
                  <MagnifyingGlass size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-dim" aria-hidden="true" />
                  <input
                    id="sym"
                    role="combobox"
                    aria-expanded={listOpen}
                    aria-controls="sym-list"
                    aria-autocomplete="list"
                    aria-activedescendant={active >= 0 ? `sym-opt-${active}` : undefined}
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value.toUpperCase())
                      setOpen(true)
                    }}
                    onKeyDown={onSymbolKey}
                    onFocus={() => setOpen(true)}
                    onBlur={() => setTimeout(() => setOpen(false), 120)}
                    autoComplete="off"
                    spellCheck={false}
                    className="num w-44 rounded-lg border border-line bg-bg py-2 pl-9 pr-3 uppercase text-fg outline-none transition-colors duration-200 focus:border-accent"
                  />
                </form>
                {listOpen && (
                  <ul id="sym-list" role="listbox" aria-label="Matching symbols" className="absolute z-20 mt-1 max-h-64 w-64 overflow-auto rounded-xl p-1 glass shadow-2xl">
                    {hits.length === 0 && (
                      <li role="presentation" className="px-3 py-2 text-xs leading-relaxed text-dim">
                        No match for “{query.trim()}”. Press Enter to try it anyway.
                      </li>
                    )}
                    {hits.map((h, i) => (
                      <li
                        key={h.symbol}
                        id={`sym-opt-${i}`}
                        role="option"
                        aria-selected={i === active}
                        onMouseDown={(e) => e.preventDefault()}
                        onMouseEnter={() => setActive(i)}
                        onClick={() => choose(h.symbol)}
                        className={`flex cursor-pointer items-baseline justify-between gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 ${i === active ? 'bg-white/[0.09]' : ''}`}
                      >
                        <span className="num">{h.symbol}</span>
                        <span className="truncate text-xs text-dim">{h.name !== h.symbol ? h.name : ''}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <Segmented label="Interval" value={interval} onChange={setIntervalId} options={INTERVALS} />

              <div className="ml-auto flex items-center gap-3 text-sm">
                {last !== null && <span className="num text-lg">{last.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>}
                {result && (
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs ${result.source === 'kite' ? 'bg-accent/15 text-accent' : 'bg-muted text-dim'}`}
                    title={result.note}
                  >
                    {result.source === 'kite' ? 'Kite data' : 'Demo data'}
                  </span>
                )}
              </div>
            </div>

            {result?.source === 'demo' && !error && (
              <p className="mb-3 rounded-lg border border-line bg-bg px-3 py-2 text-xs leading-relaxed text-dim" role="status">
                Showing synthetic bars, not real prices. {result.note ? `Reason: ${result.note.replace(/\.$/, '')}. ` : ''}Start the API and log in to Kite to see real data.
              </p>
            )}

            <div className={`h-[420px] transition-opacity duration-300 sm:h-[480px] ${loading && result ? 'opacity-50' : ''}`} aria-busy={loading}>
              {error ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center" role="alert">
                  <WarningCircle size={36} weight="duotone" className="text-loss" aria-hidden="true" />
                  <p className="max-w-[46ch] text-sm leading-relaxed text-dim">{error}</p>
                </div>
              ) : result ? (
                <CandleChart candles={result.candles} levels={levels} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-dim">Loading…</div>
              )}
            </div>
          </section>

          <div className="panel">
            <TradesTable />
          </div>
        </div>

        <aside className="min-w-0 space-y-4">
          <div className="panel">
            <TradeCalculator
              type={type}
              entry={entry}
              stop={stop}
              lastPrice={last}
              onType={(t) => {
                setType(t)
                resetLevels(t)
              }}
              onEntry={setEntry}
              onStop={setStop}
              onReset={() => resetLevels(type)}
            />
          </div>
          <div className="panel">
            <Baselines />
          </div>
        </aside>
      </main>
    </div>
  )
}
