import {
  type AutoscaleInfo,
  type Logical,
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

/** A supply/demand zone drawn as a box from its base candles to the right edge. `from` = UTC seconds in the same naive-IST encoding as candles. */
export interface Zone {
  label: string
  top: number
  bottom: number
  from: number | null
  kind: 'demand' | 'supply'
  strong: boolean
}

const GAIN = '#34d399'
const LOSS = '#fb7185'

/** Candlestick chart. Candle times are naive IST wall-clock encoded as UTC seconds, so the axis shows exchange time. */
export default function CandleChart({ candles, levels, zones = [] }: { candles: Candle[]; levels: Level[]; zones?: Zone[] }) {
  const host = useRef<HTMLDivElement>(null)
  const layer = useRef<HTMLDivElement>(null)
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

  useEffect(() => {
    const c = chart.current, s = series.current, ov = layer.current, el = host.current
    if (!c || !s || !ov || !el) return
    const extra = [...zones.flatMap((z) => [z.top, z.bottom]), ...levels.map((l) => l.price)].filter((v) => v > 0)
    s.applyOptions({
      autoscaleInfoProvider: (base: () => AutoscaleInfo | null) => {
        const r = base()
        if (!r || !r.priceRange || !zones.length) return r
        return { ...r, priceRange: { minValue: Math.min(r.priceRange.minValue, ...extra), maxValue: Math.max(r.priceRange.maxValue, ...extra) } }
      },
    })
    const times = candles.map((k) => k.time)
    const boxes = zones.map((z) => {
      const d = document.createElement('div')
      const rgb = z.kind === 'demand' ? '52,211,153' : '251,113,133'
      d.style.cssText = `position:absolute;border:1px ${z.strong ? 'solid' : 'dashed'} rgba(${rgb},${z.strong ? 0.9 : 0.55});background:rgba(${rgb},${z.strong ? 0.26 : 0.1});border-radius:3px`
      const early = z.from !== null && times.length > 0 && z.from < times[0]
      d.innerHTML = `<span style="position:absolute;left:6px;top:2px;font-size:10px;color:#e6ebf2;opacity:.85;white-space:nowrap">${z.label}${early ? ' · formed before this window' : ''}</span>`
      ov.appendChild(d)
      const i = z.from === null ? 0 : Math.max(0, times.findIndex((t) => t >= z.from!))
      return { z, d, i: i < 0 ? times.length - 1 : i }
    })
    let dead = false, pending = 0
    const draw = () => {
      if (dead) return
      const w = el.clientWidth - (c.priceScale('right').width() || 0)
      for (const { z, d, i } of boxes) {
        const x = c.timeScale().logicalToCoordinate(i as Logical)
        const y1 = s.priceToCoordinate(z.top), y2 = s.priceToCoordinate(z.bottom)
        if (x === null || y1 === null || y2 === null) { d.style.display = 'none'; continue }
        const left = Math.max(0, x - 3)
        d.style.display = left < w ? 'block' : 'none'
        d.style.left = `${left}px`
        d.style.width = `${Math.max(w - left, 0)}px`
        d.style.top = `${Math.min(y1, y2)}px`
        d.style.height = `${Math.max(Math.abs(y2 - y1), 2)}px`
      }
    }
    const raf = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(draw) }
    c.timeScale().subscribeVisibleLogicalRangeChange(raf)
    c.subscribeCrosshairMove(raf)
    const ro = new ResizeObserver(raf)
    ro.observe(el)
    raf()
    return () => {
      dead = true
      cancelAnimationFrame(pending)
      ro.disconnect()
      c.timeScale().unsubscribeVisibleLogicalRangeChange(raf)
      c.unsubscribeCrosshairMove(raf)
      boxes.forEach((b) => b.d.remove())
    }
  }, [zones, candles, levels])

  const btn =
    'flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-bg/80 text-dim backdrop-blur transition-colors duration-200 hover:text-fg'
  return (
    <div className="relative h-full w-full">
      <div ref={host} className="h-full w-full" role="img" aria-label="Candlestick price chart" />
      <div ref={layer} className="pointer-events-none absolute inset-0 z-[5] overflow-hidden" aria-hidden="true" />
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
