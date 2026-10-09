import { useEffect, useState } from 'react'
import { fetchTrades, type TradesResult } from '../lib/api'
import { inr } from '../lib/sizing'
import Segmented from './Segmented'

const COMBOS = ['dit15', 'wit', 'mit'] as const

export default function TradesTable() {
  const [combo, setCombo] = useState<(typeof COMBOS)[number]>('dit15')
  const [loaded, setLoaded] = useState<TradesResult | null>(null)
  const data = loaded?.combo === combo ? loaded : null

  useEffect(() => {
    const ac = new AbortController()
    fetchTrades(combo, ac.signal)
      .then(setLoaded)
      .catch(() => undefined)
    return () => ac.abort()
  }, [combo])

  return (
    <section className="rounded-2xl glass p-5" aria-labelledby="trades-h">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="trades-h" className="font-semibold">
          Backtest trades
        </h2>
        <Segmented
          label="Combo"
          value={combo}
          onChange={setCombo}
          options={COMBOS.map((c) => ({ id: c, label: c.toUpperCase() }))}
        />
      </div>

      <div className="mt-4 overflow-x-auto" aria-live="polite">
        {data === null ? (
          <p className="py-8 text-sm text-dim">Loading…</p>
        ) : data.error ? (
          <p className="py-8 text-sm leading-relaxed text-loss" role="alert">
            {data.error}
          </p>
        ) : data.rows.length === 0 ? (
          <p className="py-8 text-sm leading-relaxed text-dim">
            No trade file found for {combo.toUpperCase()}. The API reads <span className="num">results/**/*{combo}*final*.csv</span>, which the backtest scripts
            write. Run one, then reload.
          </p>
        ) : (
          <>
            <p className="mb-2 text-xs text-dim">
              {data.rows.length} most recent from <span className="num">{data.source}</span>
            </p>
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-dim">
                <tr>
                  {['Ticker', 'Side', 'Entry time', 'Entry', 'Stop', 'Target', 'Outcome', 'R'].map((h, i) => (
                    <th key={h} className={`py-2 pr-3 font-medium ${i > 2 ? 'text-right' : ''}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {data.rows.map((r, i) => (
                  <tr key={i}>
                    <td className="py-2 pr-3 font-medium">{r.ticker?.replace('.NS', '')}</td>
                    <td className="py-2 pr-3 capitalize">{r.type}</td>
                    <td className="num py-2 pr-3 text-dim">{r.entry_time?.slice(0, 16)}</td>
                    <td className="num py-2 pr-3 text-right">{r.entry_price != null ? inr(r.entry_price, 2) : ''}</td>
                    <td className="num py-2 pr-3 text-right">{r.stop != null ? inr(r.stop, 2) : ''}</td>
                    <td className="num py-2 pr-3 text-right">{r.target != null ? inr(r.target, 2) : ''}</td>
                    <td className={`py-2 pr-3 text-right ${r.outcome?.toUpperCase() === 'WIN' ? 'text-accent' : r.outcome?.toUpperCase() === 'LOSS' ? 'text-loss' : 'text-dim'}`}>
                      {r.outcome}
                    </td>
                    <td className="num py-2 text-right">{r.r != null ? r.r.toFixed(2) : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </section>
  )
}
