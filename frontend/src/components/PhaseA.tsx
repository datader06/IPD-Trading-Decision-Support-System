import { useEffect, useState } from "react";
import type { Shared } from "../App";
import { loadPhaseA } from "../lib/phaseA";
import type { PhaseAData, Stat } from "../lib/phaseA";

const NA = "Not available in source data";
const sg = (v: number, d = 1) => (v > 0 ? "+" : "") + v.toFixed(d);
const col = (v: number) => (v > 0 ? "#34d399" : v < 0 ? "#f87171" : "inherit");
const SCOPES = [["ALL", "All (2021–2026)"], ["TRAIN", "Train (<2026)"], ["HOLDOUT", "Holdout (2026)"]] as const;

const pick = (rows: Stat[] | undefined, key: string) => rows?.find((s) => s.label.replace(/^B0\s+/, "").replace(/CAPPED\s*/, "").startsWith(key));

function Curve({ pts }: { pts: { date: string; cum: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (pts.length < 2) return <div className="chartmsg muted">{NA}</div>;
  const W = 800, H = 280, P = { l: 48, r: 12, t: 12, b: 26 };
  const vals = pts.map((p) => p.cum);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const x = (i: number) => P.l + (i / (pts.length - 1)) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - (v - lo) / (hi - lo || 1)) * (H - P.t - P.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.cum).toFixed(1)}`).join("");
  const ticks = [lo, (lo + hi) / 2, hi];
  const years = [...new Set(pts.map((p) => p.date.slice(0, 4)))].map((yr) => ({ yr, i: pts.findIndex((p) => p.date.startsWith(yr)) }));
  const h = hover === null ? null : pts[hover];
  return (
    <div className="curve">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cumulative R curve"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const f = ((e.clientX - r.left) / r.width) * W;
          setHover(Math.max(0, Math.min(pts.length - 1, Math.round(((f - P.l) / (W - P.l - P.r)) * (pts.length - 1)))));
        }}>
        {ticks.map((t) => (
          <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#1f2a37" /><text x={P.l - 6} y={y(t) + 4} textAnchor="end" fill="#8b97a7" fontSize="11">{t.toFixed(0)}R</text></g>
        ))}
        <line x1={P.l} x2={W - P.r} y1={y(0)} y2={y(0)} stroke="#4b5a6d" strokeDasharray="4 3" />
        {years.map(({ yr, i }) => <text key={yr} x={x(i)} y={H - 8} fill="#8b97a7" fontSize="11">{yr}</text>)}
        <path d={d} fill="none" stroke="#3b82f6" strokeWidth="2" />
        {hover !== null && h && <><line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#8b97a7" /><circle cx={x(hover)} cy={y(h.cum)} r="4" fill="#3b82f6" /></>}
      </svg>
      <div className="muted sm">{h ? `Trade ${hover! + 1} of ${pts.length} · exit ${h.date} · cumulative ${sg(h.cum, 2)} R` : "Hover the curve for trade-by-trade values."}</div>
    </div>
  );
}

function YearBars({ rows }: { rows: Stat[] }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.totR)), 1);
  return (
    <div className="ybars">
      {rows.map((r) => (
        <div key={r.label} className="ybar">
          <div className="yv" style={{ color: col(r.totR) }}>{sg(r.totR)}R</div>
          <div className="ytrack"><div style={{ height: `${(Math.abs(r.totR) / max) * 100}%`, background: col(r.totR), [r.totR >= 0 ? "bottom" : "top"]: 0 } as React.CSSProperties} className="yfill" /></div>
          <div className="l">{r.label.replace("B0 ", "")}</div>
        </div>
      ))}
    </div>
  );
}

const Row = ({ s, name }: { s: Stat | undefined; name: string }) =>
  s ? (
    <tr>
      <td><b>{name}</b></td><td className="r">{s.n}</td><td className="r">{s.w}</td><td className="r">{s.l}</td><td className="r">{s.amb}</td>
      <td className="r">{s.winPct.toFixed(1)}% <span className="muted sm">[{s.ciLo}–{s.ciHi}]</span></td>
      <td className="r" style={{ color: col(s.expR) }}>{sg(s.expR, 3)}</td><td className="r">{s.pf.toFixed(2)}</td>
      <td className="r" style={{ color: col(s.totR) }}>{sg(s.totR)}</td><td className="r">{s.maxDD.toFixed(1)}</td>
      <td className="r muted">{s.ambTotLo === undefined ? NA : `${sg(s.ambTotLo)} … ${sg(s.ambTotHi!)}`}</td>
    </tr>
  ) : <tr><td><b>{name}</b></td><td colSpan={10} className="muted">{NA}</td></tr>;

const Head = ({ first }: { first: string }) => (
  <thead><tr><th>{first}</th><th className="r">n</th><th className="r">W</th><th className="r">L</th><th className="r">Amb</th><th className="r">Win % [CI]</th>
    <th className="r">Exp R</th><th className="r">PF</th><th className="r">Total R</th><th className="r">Max DD R</th><th className="r">Ambiguity-bound total R</th></tr></thead>
);

export default function PhaseA({ shared, goScanner }: { shared: Shared; goScanner: () => void }) {
  const [data, setData] = useState<PhaseAData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<(typeof SCOPES)[number][0]>("ALL");
  useEffect(() => { loadPhaseA().then(setData).catch((e) => setErr(String(e.message ?? e))); }, []);

  const sel = shared.selected;
  const top = sel && (
    <div className="hint">Scanner selection: <b>{sel.ticker.replace(".NS", "")}</b> · {sel.strategy}.{" "}
      <button className="link" onClick={goScanner}>← Back to Scanner row</button></div>
  );

  if (shared.strategy === "WIT" || shared.strategy === "MIT")
    return (
      <>
        {top}
        <div className="placeholder">
          <h2>{NA}</h2>
          <p>The frozen Phase A artifact in use (<code>phase_a/pit</code>) covers the DIT15 combination only; no {shared.strategy} figures are shown.</p>
          <button className="chip on" onClick={() => shared.setStrategy("DIT15")}>Show DIT15</button>
        </div>
      </>
    );
  if (err) return <div className="err">Could not load Phase A artifacts: {err}. Run <code>npm run sync</code> in <code>frontend/</code>.</div>;
  if (!data) return <div className="muted">Loading Phase A…</div>;

  const all = pick(data.gross, "ALL")!;
  const years = data.gross.filter((s) => /^B0 20\d\d$/.test(s.label));
  const grossScope = scope === "ALL" ? all : pick(data.gross, scope === "TRAIN" ? "TRAIN" : "HOLDOUT");
  const cc = data.curveCheck;
  const curveOk = cc.n === all.n && cc.w === all.w && cc.l === all.l && cc.amb === all.amb;
  const tiles: [string, string, string?][] = [
    ["Trades (B0)", String(all.n)], ["WIN", String(all.w), "#34d399"], ["LOSS", String(all.l), "#f87171"], ["AMBIGUOUS", String(all.amb), "#f5a524"],
    ["OPEN", String(all.open)], ["CENSORED", String(all.cens)], ["NOFILL", String(all.nofill)],
  ];

  return (
    <>
      {top}
      <div className="hint">DIT15 B0 baseline (strict, corrected) · gross R unless stated · win rate and expectancy use resolved WIN + LOSS only; AMBIGUOUS trades are never converted.</div>
      <section className="tiles">
        {tiles.map(([k, v, c]) => <div key={k} className="kv"><div className="l">{k}</div><div className="v big" style={{ color: c }}>{v}</div></div>)}
      </section>
      <section className="tiles">
        <div className="kv"><div className="l">Win rate (resolved)</div><div className="v big">{all.winPct.toFixed(1)}%</div><div className="muted sm">CI {all.ciLo}–{all.ciHi}</div></div>
        <div className="kv"><div className="l">Expectancy (gross)</div><div className="v big" style={{ color: col(all.expR) }}>{sg(all.expR, 3)} R</div></div>
        <div className="kv"><div className="l">Profit factor</div><div className="v big">{all.pf.toFixed(2)}</div></div>
        <div className="kv"><div className="l">Total R (gross)</div><div className="v big" style={{ color: col(all.totR) }}>{sg(all.totR)} R</div></div>
        <div className="kv"><div className="l">Max drawdown</div><div className="v big">{all.maxDD.toFixed(1)} R</div></div>
        <div className="kv"><div className="l">Ambiguity bound (total R)</div><div className="v big sm2">{all.ambTotLo === undefined ? NA : `${sg(all.ambTotLo)} … ${sg(all.ambTotHi!)}`}</div></div>
      </section>

      <section className="panel">
        <h3>Cumulative R curve <span className="muted sm">(gross R, not monetary equity)</span></h3>
        <div className="muted sm">Built from B0 resolved trades (WIN + LOSS) in exit-time order. Units are multiples of initial risk; no capital, sizing or compounding is implied. AMBIGUOUS trades are excluded.</div>
        <Curve pts={data.curve} />
        <div className="muted sm">Check against source: curve set n={cc.n}, W/L/Amb {cc.w}/{cc.l}/{cc.amb}, final {sg(cc.totR, 2)} R vs report {sg(all.totR)} R — {curveOk ? "counts match" : "MISMATCH"}.</div>
      </section>

      <section className="panel">
        <h3>Costs: gross vs round-trip scenarios</h3>
        <div className="group" style={{ margin: ".4rem 0" }}>
          {SCOPES.map(([k, t]) => <button key={k} className={scope === k ? "chip on" : "chip"} onClick={() => setScope(k)}>{t}</button>)}
        </div>
        <div className="tablewrap inner"><table>
          <Head first="Scenario" />
          <tbody>
            <Row name="Gross" s={grossScope} />
            {["0.10", "0.20", "0.30"].map((c) => <Row key={c} name={`Net ${c}% round-trip`} s={pick(data.costs[c], scope)} />)}
          </tbody>
        </table></div>
        <div className="muted sm">Slippage per side is 0.0% in every scenario. Net results are costs applied to the same trades; every cost scenario has negative expectancy in the source report.</div>
      </section>

      <section className="panel">
        <h3>Yearly breakdown <span className="muted sm">(gross R, by entry year)</span></h3>
        <YearBars rows={years} />
        <div className="tablewrap inner"><table>
          <Head first="Year" />
          <tbody>
            {years.map((s) => <Row key={s.label} name={s.label.replace("B0 ", "")} s={s} />)}
            <Row name="Train (<2026)" s={pick(data.gross, "TRAIN")} />
            <Row name="Holdout (2026)" s={pick(data.gross, "HOLDOUT")} />
          </tbody>
        </table></div>
      </section>

      <div className="two">
        <section className="panel">
          <h3>Remaining ambiguity</h3>
          <p className="muted sm">{all.amb} of {all.n} B0 trades stay AMBIGUOUS after 1-minute drill-down (never converted to win/loss). Bounds above show the range if all resolved either way.</p>
          <ul className="plain">
            {Object.entries(data.ambReasons).map(([k, v]) => <li key={k}><b>{v}</b> · {k}</li>)}
            {!Object.keys(data.ambReasons).length && <li>{NA}</li>}
          </ul>
        </section>
        <section className="panel">
          <h3>Limitations</h3>
          <ul className="plain">
            <li>Survivorship: the current 503-ticker universe is used.</li>
            <li>Corporate-action moves under 35% are undetected; {data.caExcluded.length} B0 trades were excluded as corporate-action rows.</li>
            <li>The 15:15 bar is missing from the Kite data since 2026-08-03; frames carry no volume.</li>
            <li>2026 is partly contaminated by chart reviews, so the “holdout” is not clean.</li>
            <li>Gross R ignores costs; capital-constrained run (Rs 1L, no leverage) took {data.capped[0]?.n ?? NA} of {all.n} trades.</li>
            <li>Results are historical research output, not a live-trading claim.</li>
          </ul>
        </section>
      </div>

      <section className="panel">
        <h3>Source provenance</h3>
        <ul className="plain mono">
          <li>Run ID: <b>{data.runId}</b> · mode label: pit · code hash <b>{data.codeHash}</b></li>
          <li>{data.header}</li>
          <li>results/nogit-145d6302/phase_a/pit/report.txt · run_info.txt · candidates.csv</li>
          <li>Docs: docs/PHASE_A_FREEZE.md · docs/PHASE_A_RESULTS.md · docs/PHASE_A_PLAN.md</li>
          {data.rupees && <li>{data.rupees} (report footnote, all-signal sizing; not used in the curve)</li>}
        </ul>
        <div className="muted sm">The registry constant <code>SOURCE_CODE_HASH</code> is cd73bf8d; the measured hash of the data in use is e5e09db7 (documented discrepancy in the Experiment 1 preregistration).</div>
      </section>
    </>
  );
}
