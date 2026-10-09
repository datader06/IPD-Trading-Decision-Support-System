import { useEffect, useState } from 'react'
import { loadDesk, type Setup } from '../lib/research'

export default function LiveSetups({ selected, onPick }: { selected: Setup | null; onPick: (s: Setup) => void }) {
  const [rows, setRows] = useState<Setup[] | null>(null)
  useEffect(() => {
    loadDesk().then((d) => setRows(d?.setups ?? []))
  }, [])

  return (
    <section className="rounded-2xl glass p-5" aria-labelledby="setups-h">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="setups-h" className="font-semibold">
          Scanner setups
        </h2>
        <span className="text-xs text-dim">{rows?.[0] ? `Cached snapshot · ${rows[0].as_of}` : ''}</span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-dim">
        Approaching means price is nearing the zone, not that a trade triggered. Select one to load its levels and ML insights.
      </p>
      {rows === null ? (
        <p className="mt-3 text-sm text-dim">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-sm text-dim">No setup data. Run scripts/export_desk_data.py in dz-engine.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Live scanner setups</caption>
            <thead className="text-left text-xs text-dim">
              <tr>
                <th className="py-2 pr-2 font-medium">Ticker</th>
                <th className="py-2 pr-2 font-medium">Combo</th>
                <th className="py-2 pr-2 font-medium">Zone</th>
                <th className="py-2 pr-2 text-right font-medium">Entry</th>
                <th className="py-2 pr-2 text-right font-medium">Distance</th>
                <th className="py-2 text-right font-medium">Similar won</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60">
              {rows.map((s) => {
                const on = selected?.ticker === s.ticker && selected?.strategy === s.strategy && selected?.entry === s.entry
                const w = s.insight?.available ? s.insight.similar_win_rate! : null
                return (
                  <tr
                    key={s.ticker + s.strategy + s.entry}
                    tabIndex={0}
                    aria-selected={on}
                    onClick={() => onPick(s)}
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onPick(s))}
                    className={`cursor-pointer transition-colors duration-150 hover:bg-white/[0.04] focus-visible:bg-white/[0.06] ${on ? 'bg-accent/10' : ''}`}
                  >
                    <td className="py-2.5 pr-2 font-medium">{s.ticker}</td>
                    <td className="py-2.5 pr-2 text-dim">{s.strategy}</td>
                    <td className={`py-2.5 pr-2 ${s.type === 'demand' ? 'text-accent' : 'text-loss'}`}>{s.type}</td>
                    <td className="num py-2.5 pr-2 text-right">{s.entry.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                    <td className="num py-2.5 pr-2 text-right text-dim">{s.dist_pct > 0 ? '+' : ''}{s.dist_pct.toFixed(1)}%</td>
                    <td className="num py-2.5 text-right">{w === null ? '–' : `${Math.round(w * 100)}%`}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
