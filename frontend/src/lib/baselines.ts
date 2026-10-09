/** Backtest numbers copied from docs/STATUS.md (sections 7 and 9). Gross of costs, Rs 1,000 risk per trade, replay win/loss
 *  with still-ambiguous trades scored by the legacy heuristic. NOT confirmed baselines: review is pending (STATUS.md). */
export interface BaselineRow {
  combo: 'DIT15' | 'WIT' | 'MIT'
  label: string
  n: number
  winRate: number
  ci: [number, number]
  avgR: number
  pnl: number
}

export interface BaselineSet {
  id: string
  title: string
  window: string
  source: string
  rows: BaselineRow[]
}

export const BASELINES: BaselineSet[] = [
  {
    id: 'v1',
    title: 'Baseline v1',
    window: 'Entries from 2024-01-01',
    source: 'STATUS.md section 7',
    rows: [
      { combo: 'DIT15', label: 'Daily + 15m', n: 231, winRate: 29.9, ci: [24, 36], avgR: -0.112, pnl: -15380 },
      { combo: 'WIT', label: 'Weekly + 60m', n: 63, winRate: 41.3, ci: [30, 54], avgR: 0.241, pnl: 14090 },
      { combo: 'MIT', label: 'Monthly + daily', n: 24, winRate: 41.7, ci: [21, 62], avgR: 0.25, pnl: 5897 },
    ],
  },
  {
    id: 'long',
    title: 'Long history',
    window: 'Entries from 2021-01-01, cap 5, strict HTF',
    source: 'STATUS.md section 9',
    rows: [
      { combo: 'DIT15', label: 'Daily + 15m', n: 268, winRate: 32.5, ci: [27, 38], avgR: -0.039, pnl: 3421 },
      { combo: 'WIT', label: 'Weekly + 60m', n: 98, winRate: 36.7, ci: [28, 46], avgR: 0.122, pnl: 11517 },
      { combo: 'MIT', label: 'Monthly + daily', n: 35, winRate: 48.6, ci: [31, 66], avgR: 0.415, pnl: 13330 },
    ],
  },
]
