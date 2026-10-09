import { useGSAP } from '@gsap/react'
import { Brain, ChartLineUp, Flask, MagnifyingGlass, ShieldCheck, Warning } from '@phosphor-icons/react'
import gsap from 'gsap'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Nav from '../components/Nav'
import { COMBO_LABEL, loadDesk, type DeskData, type Stat } from '../lib/research'
import { inr } from '../lib/sizing'

const sg = (v: number | null, d = 2) => (v === null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(d)}`)

export default function Research() {
  const root = useRef<HTMLDivElement>(null)
  const [d, setD] = useState<DeskData | null | undefined>(undefined)
  useEffect(() => {
    loadDesk().then(setD)
  }, [])
  useGSAP(
    () => {
      if (!d) return
      gsap.matchMedia().add('(prefers-reduced-motion: no-preference)', () => {
        gsap.from('.panel', { opacity: 0, y: 24, duration: 0.6, stagger: 0.07, ease: 'power3.out' })
      })
    },
    { scope: root, dependencies: [d] },
  )

  return (
    <div ref={root} className="min-h-dvh">
      <div className="ambient" aria-hidden="true" />
      <Nav />
      <main className="mx-auto max-w-[1200px] space-y-4 px-4 py-8 sm:px-6">
        <header className="panel">
          <p className="text-xs uppercase tracking-[0.18em] text-accent">Research · ML layer</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Rules decide. ML explains, compares and checks.</h1>
          <p className="mt-3 max-w-[70ch] text-sm leading-relaxed text-dim">
            The deterministic engine picks every trade. The ML layer was tested as a trade filter in seven preregistered walk-forward experiments and did not beat the rules
            reliably, so it ships as decision support on the desk and as a validation bench for every algorithm change.
          </p>
        </header>

        {d === undefined ? (
          <p className="text-sm text-dim">Loading…</p>
        ) : d === null ? (
          <p className="text-sm text-dim">Research data not found. Run scripts/export_desk_data.py in dz-engine.</p>
        ) : (
          <>
            <section className="panel grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="How ML is used">
              <Use icon={<MagnifyingGlass size={20} weight="duotone" />} title="Similar past trades">
                Nearest {d.ml_meta.history_rows} historical v6 trades to a live setup, with their outcomes.
              </Use>
              <Use icon={<Brain size={20} weight="duotone" />} title="Setup explanation">
                Where each input ranks against history, and which way the model leans.
              </Use>
              <Use icon={<Warning size={20} weight="duotone" />} title="Unusual-setup flag">
                Warns when a zone is unlike 95% of past trades: little evidence behind the rules there.
              </Use>
              <Use icon={<ShieldCheck size={20} weight="duotone" />} title="Validation bench">
                Any algorithm version goes through the same walk-forward test, random control and power check.
              </Use>
            </section>

            <section className="panel rounded-2xl glass p-5" aria-labelledby="oos-h">
              <h2 id="oos-h" className="font-semibold">
                Final baseline v6: chosen years vs unseen years
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-dim">
                v6 cutoffs were chosen on 2021+ trades. 2015–2020 trades come from the same frozen rules re-run on older Kite bars, so they are the honest out-of-sample check. Gross,
                Rs 1,000 risk per trade.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <caption className="sr-only">Win rate and R by combo, 2021+ vs 2015-2020</caption>
                  <thead className="text-left text-xs text-dim">
                    <tr>
                      <th className="py-2 pr-2 font-medium">Combo</th>
                      <th className="py-2 pr-2 text-right font-medium">2021+ trades</th>
                      <th className="py-2 pr-2 text-right font-medium">Win rate</th>
                      <th className="py-2 pr-2 text-right font-medium">Avg R</th>
                      <th className="py-2 pr-2 text-right font-medium">2015–20 trades</th>
                      <th className="py-2 pr-2 text-right font-medium">Win rate</th>
                      <th className="py-2 text-right font-medium">Avg R</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {(['DIT15', 'WIT', 'MIT', 'ALL'] as const).map((c) => {
                      const a = c === 'ALL' ? d.baselines.v6.all : d.baselines.v6.rows.find((r) => r.combo === c)!
                      const b = c === 'ALL' ? d.baselines.oos.all : d.baselines.oos.rows.find((r) => r.combo === c)!
                      return (
                        <tr key={c} className={c === 'ALL' ? 'font-medium' : ''}>
                          <td className="py-2.5 pr-2">
                            {c === 'ALL' ? 'All' : c}
                            {c !== 'ALL' && <div className="text-xs font-normal text-dim">{COMBO_LABEL[c]}</div>}
                          </td>
                          <Cells s={a} />
                          <Cells s={b} last />
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-dim">
                Reading: the rules stay profitable on unseen years (avg R {sg(d.baselines.oos.all.avg_r)}, {inr(d.baselines.oos.all.pnl)} gross) but the win rate drops from{' '}
                {d.baselines.v6.all.win_rate}% to {d.baselines.oos.all.win_rate}%. DIT15 holds best; WIT is near breakeven; MIT stays positive through its 3R target. Treat 44% as optimistic.
              </p>
            </section>

            <section className="panel rounded-2xl glass p-5" aria-labelledby="exp-h">
              <div className="flex items-center gap-2">
                <Flask size={18} weight="duotone" className="text-accent" aria-hidden="true" />
                <h2 id="exp-h" className="font-semibold">
                  Can ML beat the rules? Preregistered experiments
                </h2>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-dim">
                Each design and pass rule was written down before the model ran. Walk-forward by year, purged and embargoed; the 2026 holdout was never scored. Pass = enough lift,
                beats random selection after multiple-testing correction, and consistent across years.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[720px] text-sm">
                  <caption className="sr-only">Experiment results</caption>
                  <thead className="text-left text-xs text-dim">
                    <tr>
                      <th className="py-2 pr-2 font-medium">Experiment</th>
                      <th className="py-2 pr-2 font-medium">Approach</th>
                      <th className="py-2 pr-2 font-medium">Data</th>
                      <th className="py-2 pr-2 font-medium">Best model</th>
                      <th className="py-2 pr-2 text-right font-medium">Best result</th>
                      <th className="py-2 pr-2 text-right font-medium">p vs random</th>
                      <th className="py-2 text-right font-medium">Pass</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line/60">
                    {d.experiments.map((e) => (
                      <tr key={e.name + e.what}>
                        <td className="py-2.5 pr-2 font-medium">{e.name}</td>
                        <td className="py-2.5 pr-2">{e.what}</td>
                        <td className="py-2.5 pr-2 text-xs text-dim">{e.data}</td>
                        <td className="num py-2.5 pr-2 text-xs">{e.best}</td>
                        <td className="num py-2.5 pr-2 text-right">{e.metric}</td>
                        <td className="num py-2.5 pr-2 text-right text-dim">{e.p.toFixed(2)}</td>
                        <td className="py-2.5 text-right">
                          <span className={`rounded-full px-2 py-0.5 text-xs ${e.passed ? 'bg-accent/15 text-accent' : 'bg-muted text-dim'}`}>{e.passed ? 'Yes' : 'No'}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl glass p-5">
                <div className="flex items-center gap-2">
                  <ChartLineUp size={18} weight="duotone" className="text-accent" aria-hidden="true" />
                  <h2 className="font-semibold">Why no model passed</h2>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-dim">
                  With {d.power.test_trades} test trades and a {d.power.base}% base win rate, a filter has to lift the win rate by about{' '}
                  <span className="num text-fg">{d.power.min_detectable} points</span> before it can be told apart from luck. Realistic lifts are 3–5 points, which needs roughly
                  900+ selected trades. The best results (about +3 to +4 points) sit inside chance.
                </p>
              </div>
              <div className="rounded-2xl glass p-5">
                <h2 className="font-semibold">What would change the answer</h2>
                <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-dim">
                  <li>· Richer inputs: volume, sector strength, opposing-zone distance.</li>
                  <li>· More trades: relaxed candidate pools, more symbols.</li>
                  <li>· Forward data after October 2026, with every cutoff frozen.</li>
                </ul>
                <Link to="/desk" className="mt-4 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-on-accent transition-opacity duration-200 hover:opacity-90">
                  See ML insights on the desk
                </Link>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function Use({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl glass p-5">
      <div className="text-accent" aria-hidden="true">
        {icon}
      </div>
      <h2 className="mt-3 font-semibold">{title}</h2>
      <p className="mt-1 text-sm leading-relaxed text-dim">{children}</p>
    </div>
  )
}

function Cells({ s, last = false }: { s: Stat; last?: boolean }) {
  return (
    <>
      <td className="num py-2.5 pr-2 text-right">{s.n}</td>
      <td className="num py-2.5 pr-2 text-right">
        {s.win_rate?.toFixed(1)}%
        <div className="text-xs text-dim">
          [{s.ci[0]}–{s.ci[1]}]
        </div>
      </td>
      <td className={`num py-2.5 ${last ? '' : 'pr-2'} text-right ${(s.avg_r ?? 0) >= 0 ? 'text-accent' : 'text-loss'}`}>{sg(s.avg_r, 3)}</td>
    </>
  )
}
