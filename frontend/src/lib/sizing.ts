/** Position sizing exactly as src/candidates.py and config.py: Rs 1,000 max loss, Rs 1,00,000 capital, 2:1 reward-risk. */
export const MAX_LOSS_PER_TRADE = 1000
export const CAPITAL = 100000
export const REWARD_RISK = 2

export type ZoneType = 'demand' | 'supply'

export interface TradePlan {
  valid: boolean
  reason?: string
  risk: number
  target: number
  shares: number
  capitalUsed: number
  maxLoss: number
  maxGain: number
}

/** Parse what a person types into a price: tolerates thousands separators, spaces and a Rs / rupee prefix. NaN if it is not a number. */
export function parseNum(raw: string): number {
  const t = raw.replace(/rs\.?|\u20b9|,|\s/gi, '')
  return /^-?\d*\.?\d+$/.test(t) ? parseFloat(t) : NaN
}

/** Stops closer than this fraction of the entry cannot be traded after costs and are almost always a typo. */
export const MIN_RISK_FRACTION = 0.0005

export function planTrade(type: ZoneType, entry: number, stop: number): TradePlan {
  const empty = { risk: 0, target: 0, shares: 0, capitalUsed: 0, maxLoss: 0, maxGain: 0 }
  const bad = (reason: string): TradePlan => ({ valid: false, reason, ...empty })
  if (Number.isNaN(entry) || Number.isNaN(stop)) return bad('Enter an entry and a stop as plain numbers.')
  if (entry <= 0 || stop <= 0) return bad('Entry and stop must both be above zero.')
  const wrongSide = type === 'demand' ? stop >= entry : stop <= entry
  if (wrongSide) return bad(type === 'demand' ? 'A demand trade needs the stop below the entry.' : 'A supply trade needs the stop above the entry.')
  const risk = Math.abs(entry - stop)
  if (risk / entry < MIN_RISK_FRACTION) return bad('The stop is within 0.05% of the entry. That is too tight to trade after costs.')
  const target = type === 'demand' ? entry + REWARD_RISK * risk : entry - REWARD_RISK * risk
  if (target <= 0) return bad('The stop is so wide that a 2:1 target would fall below zero.')
  const shares = Math.min(Math.floor(MAX_LOSS_PER_TRADE / risk), Math.floor(CAPITAL / entry))
  if (shares <= 0) return bad('Risk per share is too large for a Rs 1,000 max loss.')
  return {
    valid: true,
    risk,
    target,
    shares,
    capitalUsed: shares * entry,
    maxLoss: shares * risk,
    maxGain: shares * risk * REWARD_RISK,
  }
}

export const inr = (n: number, digits = 0) =>
  new Intl.NumberFormat('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n)
