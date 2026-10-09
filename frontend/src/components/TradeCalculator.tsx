import { ArrowCounterClockwise } from '@phosphor-icons/react'
import Segmented from './Segmented'
import { CAPITAL, MAX_LOSS_PER_TRADE, REWARD_RISK, inr, parseNum, planTrade, type ZoneType } from '../lib/sizing'

interface Props {
  type: ZoneType
  entry: string
  stop: string
  lastPrice: number | null
  onType: (t: ZoneType) => void
  onEntry: (v: string) => void
  onStop: (v: string) => void
  onReset: () => void
}

const field =
  'num w-full rounded-lg border border-line bg-bg px-3 py-2.5 text-fg outline-none transition-colors duration-200 focus:border-accent'

export default function TradeCalculator({ type, entry, stop, lastPrice, onType, onEntry, onStop, onReset }: Props) {
  const plan = planTrade(type, parseNum(entry), parseNum(stop))

  return (
    <section className="rounded-2xl glass p-5" aria-labelledby="calc-h">
      <div className="mb-4 flex items-center justify-between">
        <h2 id="calc-h" className="font-semibold">
          Trade levels
        </h2>
        <button
          type="button"
          onClick={onReset}
          disabled={lastPrice === null}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-dim transition-colors duration-200 hover:text-fg disabled:opacity-40"
        >
          <ArrowCounterClockwise size={14} aria-hidden="true" /> Use last price
        </button>
      </div>

      <Segmented
        kind="radio"
        label="Zone type"
        className="mb-4 [&>button]:flex-1"
        itemClassName="py-2"
        value={type}
        onChange={onType}
        options={[
          { id: 'demand', label: 'Demand (buy)' },
          { id: 'supply', label: 'Supply (sell)' },
        ]}
      />

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm text-dim">
          Entry
          <input className={`${field} mt-1`} inputMode="decimal" value={entry} onChange={(e) => onEntry(e.target.value)} />
        </label>
        <label className="block text-sm text-dim">
          Stop
          <input className={`${field} mt-1`} inputMode="decimal" value={stop} onChange={(e) => onStop(e.target.value)} />
        </label>
      </div>

      <div className="mt-5 min-h-[168px]" aria-live="polite">
        {plan.valid ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Out label={`Target (${REWARD_RISK}:1)`} value={inr(plan.target, 2)} tone="gain" />
            <Out label="Risk per share" value={inr(plan.risk, 2)} />
            <Out label="Shares" value={inr(plan.shares)} />
            <Out label="Capital used" value={`Rs ${inr(plan.capitalUsed)}`} />
            <Out label="Worst case" value={`-Rs ${inr(plan.maxLoss)}`} tone="loss" />
            <Out label="If target hit" value={`+Rs ${inr(plan.maxGain)}`} tone="gain" />
          </dl>
        ) : (
          <p className="text-sm text-loss">{plan.reason}</p>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-dim">
        Sizing follows the backtest rules: max loss Rs {inr(MAX_LOSS_PER_TRADE)} per trade, Rs {inr(CAPITAL)} capital, no leverage. Gaps can make a real loss
        larger than the stop distance.
      </p>
    </section>
  )
}

function Out({ label, value, tone }: { label: string; value: string; tone?: 'gain' | 'loss' }) {
  return (
    <div>
      <dt className="text-xs text-dim">{label}</dt>
      <dd className={`num mt-0.5 text-base ${tone === 'gain' ? 'text-accent' : tone === 'loss' ? 'text-loss' : 'text-fg'}`}>{value}</dd>
    </div>
  )
}
