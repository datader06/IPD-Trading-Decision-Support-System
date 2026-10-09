import { useEffect, useState } from 'react'
import { BASELINES, type BaselineSet } from '../lib/baselines'
import { COMBO_LABEL, loadDesk } from '../lib/research'
import { inr } from '../lib/sizing'
import Segmented from './Segmented'

export default function Baselines() {
  const [sets, setSets] = useState<BaselineSet[]>(BASELINES)
  const [id, setId] = useState(BASELINES[0].id)
  useEffect(() => {
    loadDesk().then((d) => {
      if (!d) return
      const pick = [['v6', 'v6 final'], ['v6_holdout', '2026'], ['oos', '2015–20'], ['v5', 'v5']] as const
      const next: BaselineSet[] = pick.map(([k, short]) => ({
        id: k,
        title: short,
        window: d.baselines[k].window,
        source: k === 'oos' ? 'final engine re-run on 2015–2020 bars, rules frozen' : 'STATUS.md sections 16–19',
        rows: d.baselines[k].rows.map((r) => ({ combo: r.combo, label: COMBO_LABEL[r.combo], n: r.n, winRate: r.win_rate ?? 0, ci: [r.ci[0] ?? 0, r.ci[1] ?? 0] as [number, number], avgR: r.avg_r ?? 0, pnl: r.pnl })),
      }))
      setSets(next)
      setId('v6')
    })
  }, [])
  const set = sets.find((b) => b.id === id) ?? sets[0]

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
        options={sets.map((b) => ({ id: b.id, label: b.title }))}
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
        Gross of costs, Rs 1,000 risk per trade. Brackets are 95% intervals. v6 cutoffs were chosen on 2021+ trades; the 2015–2020 set was never seen when choosing them, so it is the honest out-of-sample check.
      </p>
    </section>
  )
}
