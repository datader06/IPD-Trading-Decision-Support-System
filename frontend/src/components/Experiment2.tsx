import { useEffect, useState } from "react";
import type { Shared } from "../App";
import { parseCsv } from "../lib/data";

const BASE = import.meta.env.BASE_URL + "data/exp2/";
const num = (v: string | undefined) => (v === undefined || v === "" || v === "nan" || v === "NaN" ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const f = (v: number | null, d = 3) => (v === null ? "n/a" : v.toFixed(d));
const sg = (v: number | null, d = 3) => (v === null ? "n/a" : (v > 0 ? "+" : "") + v.toFixed(d));
const col = (v: number | null) => (v === null ? "inherit" : v > 0 ? "#34d399" : v < 0 ? "#f87171" : "inherit");
const SCOPES = ["ALL", "DIT15", "WIT", "MIT"];

async function get(n: string) {
  const r = await fetch(BASE + n);
  const t = await r.text();
  if (!r.ok || /^\s*<!doctype/i.test(t)) throw new Error(`${n}: not found`);
  return t;
}

interface Data { edge: Record<string, string>[]; table: Record<string, string>[]; auc: Record<string, string>[]; summary: any; manifest: any }

export default function Experiment2({ shared, goScanner }: { shared: Shared; goScanner: () => void }) {
  const [d, setD] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState("ALL");
  const [scen, setScen] = useState("rt0.20");
  useEffect(() => {
    Promise.all([get("edge_check.csv"), get("per_strategy.csv"), get("auc.csv"), get("summary.json"), get("dataset_manifest.json")])
      .then(([e, t, a, s, m]) => setD({ edge: parseCsv(e), table: parseCsv(t), auc: parseCsv(a), summary: JSON.parse(s), manifest: JSON.parse(m) }))
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const sel = shared.selected;
  const nav = sel && <div className="hint">Scanner selection: <b>{sel.ticker.replace(".NS", "")}</b> · {sel.strategy}. <button className="link" onClick={goScanner}>← Back to Scanner row</button></div>;
  if (err) return <div className="err">Could not load Experiment 2 artifacts: {err}. Run <code>npm run sync</code> in <code>frontend/</code>.</div>;
  if (!d) return <div className="muted">Loading Experiment 2…</div>;

  const rows = d.table.filter((r) => r.strategy === scope && r.scenario === scen && !r.arm.startsWith("ML_T2"));
  const edge = d.edge;
  const anyEdge = edge.some((r) => r.edge_established === "True");
  const m = d.manifest;
  const yes = (v: string) => (v === "True" ? "Yes" : "No");

  return (
    <>
      {nav}
      <div className={anyEdge ? "verdict warn" : "verdict bad"}>
        <b>{anyEdge ? "At least one model passed the preregistered edge test." : "No edge established."}</b> Experiment 2 pools DIT15, WIT and MIT in one model with timeframe-agnostic features.
        No model met all four preregistered criteria. The few positive-looking numbers rest on 11–16 trades and are not distinguishable from chance. The 2026 holdout ({d.summary.holdout_rows_not_scored} rows) was not scored.
      </div>

      <section className="panel">
        <h3>ML layer: what is implemented</h3>
        <ul className="plain">
          <li>Strategy-agnostic dataset builder (<span className="mono">src/ml_core/dataset.py</span>): reads any frozen candidates file per strategy, labels WIN/LOSS, builds {m.feature_columns.length} features known at the decision time ({m.feature_version}). Source file hashes are stored with each dataset, so re-running after a deterministic-layer change gives a new dataset id.</li>
          <li>Reuses the frozen walk-forward folds, four model families, T1 threshold and evaluation. Models are compared on the same folds, costs and baselines.</li>
          <li>Cross-run leaderboard (<span className="mono">scripts/compare_ml_runs.py</span>) applies one edge test to every run. Dataset <b>{m.dataset_id}</b>: {Object.entries(m.rows_by_strategy as Record<string, number>).map(([k, v]) => `${k} ${v}`).join(" · ")} rows.</li>
        </ul>
      </section>

      <section className="panel">
        <h3>Model comparison: preregistered edge test <span className="muted sm">(net of 0.20% round-trip, pooled out-of-fold 2023–2025)</span></h3>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Run</th><th>Model</th><th className="r">Resolved takes</th><th className="r">Net exp R</th><th className="r">≥100 takes</th><th className="r">Exp &gt; 0</th><th className="r">Random-filter pctile</th><th className="r">&gt; 95th</th><th className="r">Bootstrap vs B1 (low)</th><th className="r">Excl. 0</th><th className="r">Edge</th></tr></thead>
          <tbody>{edge.map((r, i) => (
            <tr key={i}><td>{r.run}</td><td><b>{r.family}</b></td><td className="r">{r.n_resolved}</td><td className="r" style={{ color: col(num(r.expectancy_rt020)) }}>{sg(num(r.expectancy_rt020))}</td>
              <td className="r">{yes(r.min_100_takes)}</td><td className="r">{yes(r.expectancy_positive)}</td><td className="r">{f(num(r.random_filter_percentile), 2)}</td><td className="r">{yes(r.above_95th_random)}</td>
              <td className="r">{sg(num(r.boot_ci_lo_vs_B1))}</td><td className="r">{yes(r.boot_excludes_zero)}</td><td className="r"><b>{yes(r.edge_established)}</b></td></tr>
          ))}</tbody>
        </table></div>
        <div className="muted sm">Edge requires all four: ≥100 resolved takes, positive net expectancy, above the 95th percentile of matched random filters, and a bootstrap interval of ML minus take-all that excludes zero. Rules fixed before the run (<span className="mono">docs/EXPERIMENT_2_PREREGISTRATION.md</span>).</div>
      </section>

      <section className="panel">
        <h3>Results by strategy</h3>
        <div className="group" style={{ margin: ".4rem 0" }}>
          {SCOPES.map((s) => <button key={s} className={scope === s ? "chip on" : "chip"} onClick={() => setScope(s)}>{s}</button>)}
          <span className="muted">|</span>
          {["gross", "rt0.10", "rt0.20", "rt0.30"].map((s) => <button key={s} className={scen === s ? "chip on" : "chip"} onClick={() => setScen(s)}>{s === "gross" ? "Gross" : `Net ${s.slice(2)}%`}</button>)}
        </div>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Arm</th><th className="r">Rows</th><th className="r">Taken</th><th className="r">Resolved</th><th className="r">Win rate</th><th className="r">Exp R</th><th className="r">PF</th><th className="r">Total R</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.arm}><td><b>{r.arm}</b></td><td className="r">{r.n_rows}</td><td className="r">{r.n_taken}</td><td className="r">{r.n_resolved_taken}</td>
              <td className="r">{num(r.win_rate) === null ? "n/a" : (num(r.win_rate)! * 100).toFixed(1) + "%"}</td>
              <td className="r" style={{ color: col(num(r.expectancy)) }}>{sg(num(r.expectancy))}</td><td className="r">{f(num(r.profit_factor), 2)}</td>
              <td className="r" style={{ color: col(num(r.total_r)) }}>{sg(num(r.total_r), 1)}</td></tr>
          ))}</tbody>
        </table></div>
        <div className="muted sm">
          {scope === "WIT" || scope === "MIT" ? `${scope} has only a few dozen test rows and no relaxed pool, so these figures are descriptive and cannot establish anything. For MIT, B0 and B1 are identical because every row is already a strict-rule trade, so a positive number there is the deterministic rule, not the model.` : "n/a = no trades taken."}
        </div>
      </section>

      <div className="two">
        <section className="panel">
          <h3>Ranking power (ROC AUC, resolved out-of-fold rows)</h3>
          <div className="tablewrap inner"><table>
            <thead><tr><th>Scope</th><th>Model</th><th className="r">n</th><th className="r">AUC</th></tr></thead>
            <tbody>{d.auc.filter((r) => r.strategy === scope).map((r, i) => <tr key={i}><td>{r.strategy}</td><td><b>{r.family}</b></td><td className="r">{r.n_resolved}</td><td className="r">{f(num(r.roc_auc))}</td></tr>)}</tbody>
          </table></div>
          <p className="muted sm">0.5 means no ranking ability. All models sit at about 0.50 on the large DIT15 sample; WIT and MIT AUCs rest on 20–59 rows and are noise.</p>
        </section>
        <section className="panel">
          <h3>Limitations</h3>
          <ul className="plain">
            <li>WIT (111 rows) and MIT (36 rows) have no relaxed candidate pool; their test sets are tiny.</li>
            <li>Experiment 2 is the second variant tried after Experiment 1; any further variant needs its own preregistration.</li>
            <li>Costs are fixed round-trip percentages; ambiguous trades are never converted.</li>
            <li>Dataset id <b>{m.dataset_id}</b>, features {m.feature_version}; sources and hashes in <span className="mono">dataset_manifest.json</span>.</li>
          </ul>
        </section>
      </div>
    </>
  );
}
