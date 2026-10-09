/** Research + ML bundle written by dz-engine `scripts/export_desk_data.py` into public/data/desk.json (static, read-only). */
export interface Stat { n: number; wins: number; win_rate: number | null; ci: [number | null, number | null]; avg_r: number | null; pnl: number }
export interface BaseSet { title: string; window: string; rows: (Stat & { combo: 'DIT15' | 'WIT' | 'MIT' })[]; all: Stat }
export interface Experiment { name: string; what: string; data: string; best: string; metric: string; auc: number | null; p: number; passed: boolean }
export interface Similar { ticker: string; entry_time: string; type: string; win: number; r: number; era: string; distance: number }
export interface Feature { name: string; label: string; value: number; pct: number; contribution: number }
export interface Insight {
  available: boolean
  reason?: string
  similar?: Similar[]
  similar_win_rate?: number
  similar_avg_r?: number
  unusual?: boolean
  novelty_pct?: number
  features?: Feature[]
}
export interface Setup {
  ticker: string
  strategy: 'DIT15' | 'WIT' | 'MIT'
  status: string
  type: 'demand' | 'supply'
  entry: number
  stop: number
  target: number
  price: number
  dist_pct: number
  htf_proximal: number
  htf_distal: number
  ltf_proximal: number
  ltf_distal: number
  htf_formed_at: string
  ltf_formed_at: string
  as_of: string
  insight: Insight | null
}
export interface DeskData {
  baselines: Record<'v6' | 'v6_train' | 'v6_holdout' | 'oos' | 'v5', BaseSet>
  experiments: Experiment[]
  setups: Setup[]
  ml_meta: { history_rows: number; history_by_strategy: Record<string, { n: number; win_rate: number; avg_r: number }>; note: string }
  power: { test_trades: number; base: number; min_detectable: number }
}

let cache: Promise<DeskData | null> | null = null
export const loadDesk = () =>
  (cache ??= fetch('/data/desk.json')
    .then(async (r) => {
      const t = await r.text()
      return r.ok && !/^\s*<!doctype/i.test(t) ? (JSON.parse(t) as DeskData) : null
    })
    .catch(() => null))

export const COMBO_LABEL = { DIT15: 'Daily + 15m', WIT: 'Weekly + 2h', MIT: 'Monthly + daily' } as const

/** Naive exchange-time string -> UTC seconds, the same encoding the chart uses for candle times. */
export const toChartTime = (s: string | null | undefined): number | null => {
  if (!s || s === 'nan') return null
  const [d, t = '00:00'] = s.split(' ')
  const [y, m, dd] = d.split('-').map(Number)
  const [h, mi] = t.split(':').map(Number)
  return Number.isFinite(y) ? Date.UTC(y, m - 1, dd, h || 0, mi || 0) / 1000 : null
}
