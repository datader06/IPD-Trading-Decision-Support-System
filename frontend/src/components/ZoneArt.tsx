import { useEffect, useState } from 'react'

const UP = '#34d399'
const DOWN = '#fb7185'
// [open, high, low, close] on a 0-100 price scale: drop into a base, rally out of it, pullback into the zone, rally again.
const BARS: [number, number, number, number][] = [
  [70, 72, 62, 64], [64, 66, 56, 58], [58, 60, 50, 52], [52, 54, 44, 46], [46, 48, 38, 40],
  [40, 45, 36, 41], [41, 44, 35, 39], [39, 43, 36, 40],
  [40, 58, 39, 56], [56, 66, 55, 64], [64, 72, 63, 70],
  [70, 71, 60, 62], [62, 63, 51, 53], [53, 54, 41, 44], [44, 53, 40, 52], [52, 62, 50, 60], [60, 70, 59, 68],
]
const X0 = 28
const STEP = 33
const W = 15
const y = (p: number) => 372 - p * 4

const HTF = { top: 47, bottom: 33 }
const LTF = { top: 44, bottom: 37 }
const RISK = LTF.top - LTF.bottom
const TARGET = LTF.top + 2 * RISK
const MONO = 'Geist Mono Variable, ui-monospace, monospace'
const SMALL = '(max-width: 640px)'

function useCompact() {
  const [compact, setCompact] = useState(() => typeof window !== 'undefined' && window.matchMedia(SMALL).matches)
  useEffect(() => {
    const mq = window.matchMedia(SMALL)
    const on = () => setCompact(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return compact
}

function Pill({ x, yy, label, color, big }: { x: number; yy: number; label: string; color: string; big: boolean }) {
  const fs = big ? 21 : 10.5
  const w = label.length * fs * 0.6 + (big ? 20 : 16)
  const h = big ? 32 : 20
  return (
    <g>
      <rect x={x} y={yy - h / 2} width={w} height={h} rx={big ? 9 : 6} fill="rgba(10,12,17,0.82)" stroke={color} strokeOpacity="0.55" />
      <text x={x + (big ? 10 : 8)} y={yy + fs * 0.34} fill={color} fontSize={fs} fontFamily={MONO} letterSpacing="0.4">
        {label}
      </text>
    </g>
  )
}

/** Illustration of the strategy: higher-timeframe zone, matching lower-timeframe zone, then entry / stop / 2:1 target.
 *  Class names (cndl, zone-htf, zone-ltf, lvl-*) are the hooks the GSAP timelines animate. Prices are illustrative only. */
export default function ZoneArt({ className = '' }: { className?: string }) {
  const compact = useCompact()
  const zf = compact ? 20 : 10.5
  const baseX = X0 + 5 * STEP - 8
  const right = X0 + BARS.length * STEP + 4
  const ltfX = X0 + 12 * STEP - 10
  return (
    <svg viewBox="0 0 740 400" className={className} role="img" aria-label="Illustration: a demand zone with entry, stop and target levels">
      <defs>
        <linearGradient id="za-htf" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={UP} stopOpacity="0.2" />
          <stop offset="1" stopColor={UP} stopOpacity="0.05" />
        </linearGradient>
        <linearGradient id="za-ltf" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={UP} stopOpacity="0.38" />
          <stop offset="1" stopColor={UP} stopOpacity="0.14" />
        </linearGradient>
      </defs>

      <g stroke="rgba(255,255,255,0.045)">
        {[60, 120, 180, 240, 300, 360].map((gy) => (
          <line key={gy} x1="0" x2="740" y1={gy} y2={gy} />
        ))}
      </g>

      <g className="zone-htf" style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
        <rect x={baseX} y={y(HTF.top)} width={right - baseX} height={y(HTF.bottom) - y(HTF.top)} rx="4" fill="url(#za-htf)" stroke={UP} strokeOpacity="0.4" strokeDasharray="3 5" />
        <text x={baseX + 8} y={y(HTF.top) - 8} fill="#8af0c6" fontSize={zf} fontFamily={MONO} letterSpacing="1.2">
          {compact ? 'DAILY' : 'DAILY ZONE'}
        </text>
      </g>

      <g className="zone-ltf" style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}>
        <rect x={ltfX} y={y(LTF.top)} width={right - ltfX} height={y(LTF.bottom) - y(LTF.top)} rx="3" fill="url(#za-ltf)" stroke={UP} strokeOpacity="0.75" />
        <text x={right - 6} y={y(LTF.bottom) + (compact ? 26 : 16)} textAnchor="end" fill="#8af0c6" fontSize={zf} fontFamily={MONO} letterSpacing="1.2">
          {compact ? '15M' : '15M ZONE'}
        </text>
      </g>

      {BARS.map(([o, h, l, c], i) => {
        const x = X0 + i * STEP
        const col = c >= o ? UP : DOWN
        return (
          <g key={i} className="cndl" style={{ transformBox: 'fill-box', transformOrigin: 'center bottom' }}>
            <line x1={x + W / 2} x2={x + W / 2} y1={y(h)} y2={y(l)} stroke={col} strokeOpacity="0.85" strokeWidth="1.1" strokeLinecap="round" />
            <rect x={x} y={y(Math.max(o, c))} width={W} height={Math.max(2.5, Math.abs(y(o) - y(c)))} fill={col} fillOpacity={c >= o ? 0.92 : 0.88} rx="2" />
          </g>
        )
      })}

      {[
        { cls: 'lvl-target', p: TARGET, col: UP, label: compact ? 'TARGET' : 'TARGET +2R' },
        { cls: 'lvl-entry', p: LTF.top, col: '#e6ebf2', label: 'ENTRY' },
        { cls: 'lvl-stop', p: LTF.bottom, col: DOWN, label: compact ? 'STOP' : 'STOP -1R' },
      ].map((l) => (
        <g key={l.cls} className={l.cls} style={{ transformBox: 'fill-box', transformOrigin: 'left center' }}>
          <line x1={X0 + 11 * STEP} x2="636" y1={y(l.p)} y2={y(l.p)} stroke={l.col} strokeOpacity="0.9" strokeDasharray="5 5" strokeWidth="1.2" />
          <Pill x={642} yy={y(l.p)} label={l.label} color={l.col} big={compact} />
        </g>
      ))}
    </svg>
  )
}
