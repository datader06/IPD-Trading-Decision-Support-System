import { Brain } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { loadDesk, type DeskData, type Setup } from '../lib/research'

const pc = (v: number) => `${Math.round(v * 100)}%`
const sg = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}`

export default function MLInsights({ setup }: { setup: Setup | null }) {
  const [desk, setDesk] = useState<DeskData | null>(null)
  useEffect(() => {
    loadDesk().then(setDesk)
  }, [])
  const ins = setup?.insight
  const base = setup ? desk?.ml_meta.history_by_strategy[setup.strategy] : undefined

  return (
    <section className="rounded-2xl glass p-5" aria-labelledby="ml-h">
      <div className="flex items-center gap-2">
        <Brain size={18} weight="duotone" className="text-accent" aria-hidden="true" />
        <h2 id="ml-h" className="font-semibold">
          ML insights
        </h2>
        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-dim">decision support</span>
      </div>

      {!setup ? (
        <p className="mt-3 text-sm leading-relaxed text-dim">Select a scanner setup to see similar past trades, what the model sees, and whether the setup is unusual.</p>
      ) : !ins?.available ? (
        <p className="mt-3 text-sm text-dim">{ins?.reason ?? 'No insights for this setup.'}</p>
      ) : (
        <>
          <p className="mt-1 text-xs text-dim">
            {setup.ticker} · {setup.strategy} {setup.type}
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Tile k="Similar trades won" v={pc(ins.similar_win_rate!)} />
            <Tile k="Their avg R" v={sg(ins.similar_avg_r!)} tone={ins.similar_avg_r! >= 0 ? 'text-accent' : 'text-loss'} />
            <Tile k={`${setup.strategy} history`} v={base ? `${pc(base.win_rate)} of ${base.n}` : '–'} />
            <Tile k="Novelty" v={ins.unusual ? 'Unusual' : `Typical · ${Math.round(ins.novelty_pct!)}th`} tone={ins.unusual ? 'text-amber-300' : ''} />
          </div>
          {ins.unusual && (
            <p className="mt-2 text-xs leading-relaxed text-amber-300">Unlike 95% of past {setup.strategy} trades: the rules have little history for setups like this.</p>
          )}

          <h3 className="mt-5 text-sm font-semibold">10 most similar past trades</h3>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[300px] text-xs">
              <caption className="sr-only">Nearest historical trades of the same strategy</caption>
              <thead className="text-left text-dim">
                <tr>
                  <th className="py-1.5 pr-2 font-medium">Ticker</th>
                  <th className="py-1.5 pr-2 font-medium">Entry</th>
                  <th className="py-1.5 pr-2 text-right font-medium">Result</th>
                  <th className="py-1.5 text-right font-medium">R</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {ins.similar!.map((s) => (
                  <tr key={s.ticker + s.entry_time}>
                    <td className="py-1.5 pr-2">{s.ticker.replace('.NS', '')}</td>
                    <td className="num py-1.5 pr-2 text-dim">{s.entry_time.slice(0, 10)}</td>
                    <td className={`py-1.5 pr-2 text-right ${s.win ? 'text-accent' : 'text-loss'}`}>{s.win ? 'win' : 'loss'}</td>
                    <td className="num py-1.5 text-right">{sg(s.r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="mt-5 text-sm font-semibold">What the model sees</h3>
          <p className="mt-1 text-xs text-dim">Percentile vs {setup.strategy} history; bar = logistic-regression lean.</p>
          <ul className="mt-2 space-y-1.5">
            {ins.features!.map((f) => {
              const w = Math.min(Math.abs(f.contribution) * 70, 48)
              return (
                <li key={f.name} className="flex items-center gap-2 text-xs">
                  <span className="min-w-0 flex-1 truncate" title={f.label}>
                    {f.label}
                  </span>
                  <span className="num w-9 text-right text-dim">{Math.round(f.pct)}th</span>
                  <span className="flex w-24 shrink-0" aria-label={`lean ${f.contribution > 0 ? 'positive' : 'negative'} ${Math.abs(f.contribution).toFixed(2)}`}>
                    <span className="flex w-12 justify-end">{f.contribution < 0 && <i className="h-1.5 rounded-full bg-loss" style={{ width: w }} />}</span>
                    <span className="flex w-12 border-l border-line">{f.contribution > 0 && <i className="h-1.5 rounded-full bg-accent" style={{ width: w }} />}</span>
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="mt-4 text-xs leading-relaxed text-dim">
            Explains and compares; does not predict. Seven walk-forward experiments ({desk?.ml_meta.history_rows ?? 328} trades, 2015–2026) found no reliable ML edge over the rules.
          </p>
        </>
      )}
    </section>
  )
}

function Tile({ k, v, tone = '' }: { k: string; v: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-bg px-3 py-2">
      <div className="text-xs text-dim">{k}</div>
      <div className={`num mt-0.5 text-sm ${tone}`}>{v}</div>
    </div>
  )
}
