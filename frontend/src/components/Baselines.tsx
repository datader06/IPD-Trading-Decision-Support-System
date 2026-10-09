import { useState } from 'react'
import { BASELINES } from '../lib/baselines'
import { inr } from '../lib/sizing'
import Segmented from './Segmented'

export default function Baselines() {
  const [id, setId] = useState(BASELINES[0].id)
  const set = BASELINES.find((b) => b.id === id) ?? BASELINES[0]

  return (
    <section className="rounded-2xl glass p-5" aria-labelledby="base-h">
      <h2 id="base-h" className="font-semibold">
        Backtest baselines
      </h2>
      <Segmented
        label="Baseline set"
        className="mt-3 [&>button]:flex-1"
        value={id}
        onChange={setId}
        options={BASELINES.map((b) => ({ id: b.id, label: b.title }))}
      />
      <p className="mt-3 text-xs text-dim">
        {set.window} · {set.source}
      </p>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <caption className="sr-only">Backtest results by timeframe combo</caption>
          <thead className="text-left text-xs text-dim">
            <tr>
              <th className="py-2 pr-2 font-medium">Combo</th>
              <th className="py-2 pr-2 text-right font-medium">Trades</th>
              <th className="py-2 pr-2 text-right font-medium">Win rate</th>
              <th className="py-2 pr-2 text-right font-medium">Avg R</th>
              <th className="py-2 text-right font-medium">P&amp;L (Rs)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line/60">
            {set.rows.map((r) => (
              <tr key={r.combo}>
                <td className="py-2.5 pr-2">
                  <div className="font-medium">{r.combo}</div>
                  <div className="text-xs text-dim">{r.label}</div>
                </td>
                <td className="num py-2.5 pr-2 text-right">
                  {r.n}
                  {r.n < 30 && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 py-0.5 text-xs text-dim" title="Sample under 30 trades">
                      &lt;30
                    </span>
                  )}
                </td>
                <td className="num py-2.5 pr-2 text-right">
                  {r.winRate.toFixed(1)}%
                  <div className="text-xs text-dim">
                    [{r.ci[0]}-{r.ci[1]}]
                  </div>
                </td>
                <td className={`num py-2.5 pr-2 text-right ${r.avgR >= 0 ? 'text-accent' : 'text-loss'}`}>{r.avgR >= 0 ? '+' : ''}{r.avgR.toFixed(3)}</td>
                <td className={`num py-2.5 text-right ${r.pnl >= 0 ? 'text-accent' : 'text-loss'}`}>{r.pnl >= 0 ? '+' : '-'}{inr(Math.abs(r.pnl))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-dim">
        Gross of costs. Win-rate brackets are 95% bootstrap intervals. These are candidate baselines, not confirmed: the trade review is still in progress.
      </p>
    </section>
  )
}
