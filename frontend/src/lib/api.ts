export type Interval = '15m' | '60m' | '1d'

export interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface CandleResult {
  candles: Candle[]
  /** 'kite' = real bars from the read-only API; 'demo' = synthetic bars so the UI works without a Kite login. */
  source: 'kite' | 'demo'
  note?: string
}

export interface SymbolHit {
  symbol: string
  name: string
}

export interface TradeRow {
  ticker?: string
  type?: string
  entry_time?: string
  entry_price?: number
  stop?: number
  target?: number
  outcome?: string
  r?: number
}

export interface TradesResult {
  combo: string
  source: string | null
  rows: TradeRow[]
  /** Set when the API answered but could not use the file, or could not be reached at all. */
  error: string | null
}

/** The symbol cannot be charted: unknown to Kite, or (with no Kite login) not one of the few demo symbols. */
export class SymbolError extends Error {}

export const FALLBACK_SYMBOLS: SymbolHit[] = [
  'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'BHARTIARTL', 'HINDUNILVR',
].map((symbol) => ({ symbol, name: symbol }))

/** After a 503 (Kite not logged in) skip the network for a while instead of failing on every keystroke. */
let kiteDownUntil = 0
const kiteDown = () => Date.now() < kiteDownUntil

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  if (kiteDown() && !url.startsWith('/api/trades')) throw new ApiError('Kite is not logged in. Run kite_login.py, then restart the API.', 503)
  const res = await fetch(url, { signal })
  if (res.status === 503) kiteDownUntil = Date.now() + 30_000
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(typeof detail === 'string' ? detail : res.statusText, res.status)
  }
  return res.json() as Promise<T>
}

const DAYS: Record<Interval, number> = { '15m': 20, '60m': 90, '1d': 500 }

export async function fetchCandles(symbol: string, interval: Interval, signal?: AbortSignal): Promise<CandleResult> {
  try {
    const q = new URLSearchParams({ symbol, interval, days: String(DAYS[interval]) })
    const data = await getJson<{ candles: Candle[] }>(`/api/candles?${q}`, signal)
    if (!data.candles.length) throw new Error('Kite returned no bars for this range.')
    return { candles: data.candles, source: 'kite' }
  } catch (e) {
    if (signal?.aborted) throw e
    if (e instanceof ApiError && e.status === 404) throw new SymbolError(`${symbol} is not an NSE equity. Check the spelling.`)
    // Without a Kite login only the demo symbols can be drawn; anything else would be an invented chart for a name that may not exist.
    if (!FALLBACK_SYMBOLS.some((s) => s.symbol === symbol.toUpperCase())) {
      throw new SymbolError(`${symbol} cannot be shown without a Kite login. Demo mode covers ${FALLBACK_SYMBOLS.map((s) => s.symbol).join(', ')}.`)
    }
    return { candles: demoCandles(symbol, interval), source: 'demo', note: e instanceof Error ? e.message : 'API unreachable' }
  }
}

export async function searchSymbols(q: string, signal?: AbortSignal): Promise<SymbolHit[]> {
  try {
    return await getJson<SymbolHit[]>(`/api/symbols?${new URLSearchParams({ q })}`, signal)
  } catch {
    const needle = q.trim().toUpperCase()
    return FALLBACK_SYMBOLS.filter((s) => s.symbol.includes(needle))
  }
}

export async function fetchTrades(combo: string, signal?: AbortSignal): Promise<TradesResult> {
  try {
    return await getJson<TradesResult>(`/api/trades?combo=${combo}`, signal)
  } catch (e) {
    if (signal?.aborted) throw e
    return { combo, source: null, rows: [], error: 'The API is not reachable. Start it with: api/.venv/bin/uvicorn api.main:app --port 8000' }
  }
}

/* ---- synthetic data (clearly labelled in the UI; never mixed with Kite bars) ---- */

function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Session timestamps (IST wall-clock encoded as UTC seconds, like the Kite bars), weekdays 09:15-15:30, newest last. */
function sessionTimes(interval: Interval, count: number): number[] {
  const day = 86400
  const step = { '15m': 900, '60m': 3600, '1d': day }[interval]
  const nowIst = Math.floor(Date.now() / 1000) + 19800
  const out: number[] = []
  let d = Math.floor(nowIst / day) * day
  while (out.length < count) {
    const weekday = new Date(d * 1000).getUTCDay()
    if (weekday !== 0 && weekday !== 6) {
      if (interval === '1d') {
        if (d <= nowIst) out.push(d)
      } else {
        const bars: number[] = []
        for (let t = d + 9 * 3600 + 15 * 60; t < d + 15 * 3600 + 30 * 60; t += step) bars.push(t)
        for (const t of bars.reverse()) if (t + step <= nowIst) out.push(t)
      }
    }
    d -= day
  }
  return out.slice(0, count).reverse()
}

function demoCandles(symbol: string, interval: Interval): Candle[] {
  const rnd = mulberry32([...symbol].reduce((a, c) => a * 31 + c.charCodeAt(0), 7))
  const vol = { '15m': 0.0035, '60m': 0.007, '1d': 0.014 }[interval]
  let price = 400 + rnd() * 2400
  return sessionTimes(interval, 260).map((time) => {
    const open = price
    const close = open * (1 + (rnd() - 0.48) * 2 * vol)
    const high = Math.max(open, close) * (1 + rnd() * vol * 0.6)
    const low = Math.min(open, close) * (1 - rnd() * vol * 0.6)
    price = close
    return { time, open: r2(open), high: r2(high), low: r2(low), close: r2(close) }
  })
}

const r2 = (n: number) => Math.round(n * 100) / 100
