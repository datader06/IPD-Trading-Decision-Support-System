import {
  CandlestickSeries,
  ColorType,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import { MagnifyingGlassMinus, MagnifyingGlassPlus, ArrowsOutLineHorizontal } from '@phosphor-icons/react'
import { useEffect, useRef } from 'react'
import type { Candle } from '../lib/api'

export interface Level {
  price: number
  title: string
  color: string
}

const GAIN = '#34d399'
const LOSS = '#fb7185'

/** Candlestick chart. Candle times are naive IST wall-clock encoded as UTC seconds, so the axis shows exchange time. */
export default function CandleChart({ candles, levels }: { candles: Candle[]; levels: Level[] }) {
  const host = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lines = useRef<IPriceLine[]>([])

  /** Scale the visible bar range by `factor` (>1 zooms out) around a logical index (default: the right edge), keeping at least 10 bars on screen. */
  const zoomBy = (factor: number, anchor?: number | null) => {
    const ts = chart.current?.timeScale()
    const r = ts?.getVisibleLogicalRange()
    if (!ts || !r) return
    const a = anchor ?? r.to // buttons keep the newest visible bar in place; the wheel anchors on the cursor
    const from = a - (a - r.from) * factor
    const to = a + (r.to - a) * factor
    if (to - from < 10) return
    ts.setVisibleLogicalRange({ from, to })
  }

  useEffect(() => {
    if (!host.current) return
    const c = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8', fontFamily: 'Geist Mono Variable, ui-monospace, monospace', fontSize: 11 },
      grid: { vertLines: { color: 'rgba(148,163,184,0.06)' }, horzLines: { color: 'rgba(148,163,184,0.06)' } },
      rightPriceScale: { borderColor: 'rgba(148,163,184,0.15)' },
      timeScale: { borderColor: 'rgba(148,163,184,0.15)', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: 'rgba(148,163,184,0.4)' }, horzLine: { color: 'rgba(148,163,184,0.4)' } },
      // The wheel must scroll the page, not zoom the chart. Zoom is explicit: Ctrl/Cmd + wheel (a trackpad pinch arrives
      // as one), the buttons, or a two-finger pinch on touch. A vertical swipe on touch screens scrolls the page.
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: { time: true, price: true }, axisDoubleClickReset: true },
    })
    chart.current = c
    series.current = c.addSeries(CandlestickSeries, {
      upColor: GAIN,
      downColor: LOSS,
      borderUpColor: GAIN,
      borderDownColor: LOSS,
      wickUpColor: GAIN,
      wickDownColor: LOSS,
    })
    const el = host.current
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return // plain scroll: let the page handle it
      e.preventDefault()
      const x = e.clientX - el.getBoundingClientRect().left
      zoomBy(Math.exp(e.deltaY * (e.ctrlKey && !e.metaKey ? 0.01 : 0.002)), c.timeScale().coordinateToLogical(x))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      el.removeEventListener('wheel', onWheel)
      c.remove()
      chart.current = null
      series.current = null
      lines.current = []
    }
  }, [])

  useEffect(() => {
    if (!series.current) return
    series.current.setData(candles.map((k) => ({ ...k, time: k.time as UTCTimestamp })))
    chart.current?.timeScale().fitContent()
  }, [candles])

  useEffect(() => {
    const s = series.current
    if (!s) return
    lines.current.forEach((l) => s.removePriceLine(l))
    lines.current = levels
      .filter((l) => l.price > 0)
      .map((l) =>
        s.createPriceLine({ price: l.price, color: l.color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: l.title }),
      )
  }, [levels, candles])

  const btn =
    'flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-bg/80 text-dim backdrop-blur transition-colors duration-200 hover:text-fg'
  return (
    <div className="relative h-full w-full">
      <div ref={host} className="h-full w-full" role="img" aria-label="Candlestick price chart" />
      <div className="absolute left-2 top-2 z-10 flex items-center gap-1">
        <button type="button" className={btn} aria-label="Zoom in" onClick={() => zoomBy(0.7)}>
          <MagnifyingGlassPlus size={16} aria-hidden="true" />
        </button>
        <button type="button" className={btn} aria-label="Zoom out" onClick={() => zoomBy(1 / 0.7)}>
          <MagnifyingGlassMinus size={16} aria-hidden="true" />
        </button>
        <button type="button" className={btn} aria-label="Fit all bars" onClick={() => chart.current?.timeScale().fitContent()}>
          <ArrowsOutLineHorizontal size={16} aria-hidden="true" />
        </button>
        <span className="ml-1 hidden text-xs text-dim sm:inline">Ctrl/⌘ + scroll to zoom</span>
      </div>
    </div>
  )
}
