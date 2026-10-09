import { useEffect, useState } from "react";
import type { Shared } from "../App";
import { loadExp1, SCENARIOS } from "../lib/exp1";
import type { Exp1Data, Scenario, Variant } from "../lib/exp1";

const NA = "Not available in source data";
const f = (v: number | null, d = 2) => (v === null ? "n/a" : v.toFixed(d));
const sg = (v: number | null, d = 2) => (v === null ? "n/a" : (v > 0 ? "+" : "") + v.toFixed(d));
const pc = (v: number | null) => (v === null ? "n/a" : (v * 100).toFixed(1) + "%");
const col = (v: number | null) => (v === null ? "inherit" : v > 0 ? "#34d399" : v < 0 ? "#f87171" : "inherit");
const label = (s: string) => (s === "gross" ? "Gross (no costs)" : `Net of ${(Number(s.slice(2))).toFixed(2)}% round-trip`);
const arm = (a: string) => a.replace("ML:", "ML · ");
const METRICS = ["expectancy", "win_rate", "profit_factor", "total_r", "max_dd"];

export default function Experiment1({ shared, goScanner, goPhaseA }: { shared: Shared; goScanner: () => void; goPhaseA: () => void }) {
  const [data, setData] = useState<Exp1Data | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [variant, setVariant] = useState<Variant>("primary");
  const [scen, setScen] = useState<Scenario>("rt0.20");
  const [year, setYear] = useState("2023");
  const [versus, setVersus] = useState("B0");
  const [metric, setMetric] = useState("expectancy");
  useEffect(() => { loadExp1().then(setData).catch((e) => setErr(String(e.message ?? e))); }, []);

  const sel = shared.selected;
  const nav = (
    <div className="hint">
      {sel && <>Scanner selection: <b>{sel.ticker.replace(".NS", "")}</b> · {sel.strategy}. </>}
      <button className="link" onClick={goScanner}>← Scanner{sel ? " (selected row)" : ""}</button> · <button className="link" onClick={goPhaseA}>← Phase A</button>
    </div>
  );

  if (shared.strategy === "WIT" || shared.strategy === "MIT")
    return (
      <>{nav}
        <div className="placeholder"><h2>{NA}</h2>
          <p>Experiment 1 is a DIT15 meta-labeling study; no {shared.strategy} figures exist.</p>
          <button className="chip on" onClick={() => shared.setStrategy("DIT15")}>Show DIT15</button></div></>
    );
  if (err) return <div className="err">Could not load Experiment 1 artifacts: {err}. Run <code>npm run sync</code> in <code>frontend/</code>.</div>;
  if (!data) return <div className="muted">Loading Experiment 1…</div>;

  const v = data.variants[variant];
  const m = data.manifest;
  const strict = variant === "strict_htf";
  const pooled = v.pooled.filter((r) => r.scenario === scen);
  const best = (name: string) => v.pooled.find((r) => r.arm === name && r.scenario === "rt0.20");
  const hgb = best("ML:hist_gb");
  const yearRows = v.year.filter((r) => r.scenario === scen && r.year === year);
  const capRows = v.cap.filter((r) => r.scenario === scen);
  const bootRows = v.boot.filter((r) => r.scenario === scen && r.versus === versus && r.metric === metric);
  const years = [...new Set(v.year.map((r) => r.year))];
  const champion = m.champion?.[strict ? "strict" : "primary"];

  return (
    <>
      {nav}
      <div className="group" style={{ margin: ".4rem 0" }}>
        <button className={variant === "primary" ? "chip on" : "chip"} onClick={() => setVariant("primary")}>Primary dataset</button>
        <button className={strict ? "chip on" : "chip"} onClick={() => setVariant("strict_htf")}>Strict-HTF sensitivity</button>
      </div>

      {!strict ? (
        <div className="verdict bad">
          <b>No reliable predictive edge was established.</b> There is no primary champion: no model reached the preregistered minimum of 100 resolved takes at 0.20% round-trip cost.
          Every model, and both rule-only baselines, has negative expectancy after costs on the 2023–2025 out-of-fold stream.
        </div>
      ) : (
        <div className="verdict warn">
          <b>Sensitivity analysis only (240 flagged rows removed; 196 of them fall in the development stream).</b> <code>hist_gb</code> is the preregistered rule's pick only because it cleared the 100-take eligibility floor;
          its expectancy is still {sg(hgb?.expectancy ?? null, 3)} R at 0.20% — negative. It is <b>not</b> a general or validated champion, and it does not change the primary conclusion.
        </div>
      )}
      <div className="hint">The 2026 holdout (781 rows) was deliberately not scored and is not used anywhere in this tab. Results cover the pooled out-of-fold test stream, 2023H1–2025H2 ({strict ? "2,386" : "2,509"} rows).</div>
      <div className="muted sm" style={{ marginBottom: ".5rem" }}>Champion in source manifest: <b>{champion === null || champion === undefined ? "None" : String(champion)}</b>.</div>

      <section className="panel">
        <h3>Pooled out-of-fold results — {strict ? "strict-HTF" : "primary"}</h3>
        <div className="group" style={{ margin: ".4rem 0" }}>
          {SCENARIOS.map((s) => <button key={s} className={scen === s ? "chip on" : "chip"} onClick={() => setScen(s)}>{s === "gross" ? "Gross" : `Net ${s.slice(2)}%`}</button>)}
        </div>
        <div className="muted sm">{label(scen)}. B0 = Phase A rule baseline (strict set); B1 = take every candidate; ML arms take a candidate when the model probability clears the frozen T1 threshold. R figures are multiples of risk, not money. n/a = no trades taken ({NA.toLowerCase()}).</div>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Arm</th><th className="r">Taken</th><th className="r">Resolved</th><th className="r">Take rate</th><th className="r">Win rate</th><th className="r">Exp R</th><th className="r">PF</th><th className="r">Total R</th><th className="r">Max DD R</th><th className="r">Ambig.</th><th className="r">Total R if ambiguous worst … best</th></tr></thead>
          <tbody>{pooled.map((r) => (
            <tr key={r.arm}><td><b>{arm(r.arm)}</b></td><td className="r">{r.nTaken ?? "n/a"}</td><td className="r">{r.nResolved ?? "n/a"}</td><td className="r">{pc(r.takeRate)}</td><td className="r">{pc(r.winRate)}</td>
              <td className="r" style={{ color: col(r.expectancy) }}>{sg(r.expectancy, 3)}</td><td className="r">{f(r.pf)}</td><td className="r" style={{ color: col(r.totalR) }}>{sg(r.totalR, 1)}</td>
              <td className="r">{f(r.maxDD, 1)}</td><td className="r">{r.amb ?? "n/a"}</td><td className="r muted">{r.ambWorst === null ? "n/a" : `${sg(r.ambWorst, 1)} … ${sg(r.ambBest, 1)}`}</td></tr>
          ))}</tbody>
        </table></div>
        <div className="muted sm">Total R and drawdown for ML arms mostly reflect how few trades they take (skipping a negative-expectancy pool raises total R mechanically); compare expectancy, not total R.</div>
      </section>

      <section className="panel">
        <h3>Yearly breakdown <span className="muted sm">({label(scen)})</span></h3>
        <div className="group" style={{ margin: ".4rem 0" }}>{years.map((y) => <button key={y} className={year === y ? "chip on" : "chip"} onClick={() => setYear(y)}>{y}</button>)}</div>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Arm</th><th className="r">Rows</th><th className="r">Taken</th><th className="r">Resolved</th><th className="r">Win rate</th><th className="r">Exp R</th><th className="r">PF</th><th className="r">Total R</th><th className="r">Max DD R</th></tr></thead>
          <tbody>{yearRows.map((r) => (
            <tr key={r.arm}><td><b>{arm(r.arm)}</b></td><td className="r">{r.nRows ?? "n/a"}</td><td className="r">{r.nTaken ?? "n/a"}</td><td className="r">{r.nResolved ?? "n/a"}</td><td className="r">{pc(r.winRate)}</td>
              <td className="r" style={{ color: col(r.expectancy) }}>{sg(r.expectancy, 3)}</td><td className="r">{f(r.pf)}</td><td className="r" style={{ color: col(r.totalR) }}>{sg(r.totalR, 1)}</td><td className="r">{f(r.maxDD, 1)}</td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <section className="panel">
        <h3>Capital-constrained view <span className="muted sm">(Rs 1,00,000, no leverage; {label(scen)})</span></h3>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Arm</th><th className="r">Taken (uncapped)</th><th className="r">Taken (capped)</th><th className="r">Peak open</th><th className="r">Peak deployed (Rs)</th><th className="r">Exp R</th><th className="r">PF</th><th className="r">Total R</th><th className="r">Max DD R</th></tr></thead>
          <tbody>{capRows.map((r) => (
            <tr key={r.arm}><td><b>{arm(r.arm)}</b></td><td className="r">{r.nUncapped ?? "n/a"}</td><td className="r">{r.nCapped ?? "n/a"}</td><td className="r">{r.peakOpen ?? "n/a"}</td><td className="r">{r.peakDeployed === null ? "n/a" : Math.round(r.peakDeployed).toLocaleString("en-IN")}</td>
              <td className="r" style={{ color: col(r.expectancy) }}>{sg(r.expectancy, 3)}</td><td className="r">{f(r.pf)}</td><td className="r" style={{ color: col(r.totalR) }}>{sg(r.totalR, 1)}</td><td className="r">{f(r.maxDD, 1)}</td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <section className="panel">
        <h3>Month-block bootstrap <span className="muted sm">(paired; ML minus baseline; {label(scen)})</span></h3>
        <div className="group" style={{ margin: ".4rem 0" }}>
          {["B0", "B1"].map((b) => <button key={b} className={versus === b ? "chip on" : "chip"} onClick={() => setVersus(b)}>vs {b}</button>)}
          <span className="muted">|</span>
          {METRICS.map((x) => <button key={x} className={metric === x ? "chip on" : "chip"} onClick={() => setMetric(x)}>{x}</button>)}
        </div>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Model</th><th className="r">ML</th><th className="r">Baseline</th><th className="r">Difference</th><th className="r">95% interval</th><th className="r">Share &gt; 0</th><th className="r">Valid draws</th></tr></thead>
          <tbody>{bootRows.map((r) => (
            <tr key={r.family}><td><b>{r.family}</b></td><td className="r">{f(r.ml, 3)}</td><td className="r">{f(r.baseline, 3)}</td><td className="r" style={{ color: col(r.diff) }}>{sg(r.diff, 3)}</td>
              <td className="r">{r.lo === null ? "n/a" : `${f(r.lo, 3)} … ${f(r.hi, 3)}`}</td><td className="r">{pc(r.share)}</td><td className="r">{r.nValid ?? "n/a"} / {r.nBoot ?? "n/a"}</td></tr>
          ))}</tbody>
        </table></div>
        {(metric === "total_r" || metric === "max_dd") && <div className="hint">Total R and drawdown differences mostly reflect how few trades the ML arms take versus the baseline, not selection skill. Prefer expectancy; the like-for-like control in the source report is a random filter with the same take counts.</div>}
        <div className="muted sm">Intervals that include zero, or rest on few valid draws, carry no evidence of improvement. Resamples whole months ({bootRows[0]?.nBoot ?? 2000} draws, seed {m.seed}).</div>
      </section>

      <div className="two">
        <section className="panel">
          <h3>Shuffled-label sanity check</h3>
          <div className="tablewrap inner"><table>
            <thead><tr><th>Model</th><th className="r">ROC AUC</th><th className="r">Expected band</th><th className="r">Within band</th></tr></thead>
            <tbody>{Object.entries(data.shuffled).map(([k, s]) => (
              <tr key={k}><td><b>{k}</b></td><td className="r">{s.roc_auc.toFixed(3)}</td><td className="r">{s.band[0].toFixed(3)}–{s.band[1].toFixed(3)}</td><td className="r">{s.passed ? "Yes" : "No"}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="muted sm"><b>Establishes:</b> with labels shuffled the pipeline scores about chance (AUC ≈ 0.5), so it is not leaking the answer through features, folds or preprocessing. Determinism check (second identical run): {Object.values(data.determinism).every(Boolean) ? "all outputs identical" : "differences found"}.<br />
            <b>Does not establish:</b> that the models have real skill on true labels — it only rules out one class of leakage bug. The shuffled check is a primary-dataset check; the strict-HTF run has no separate one.</p>
        </section>
        <section className="panel">
          <h3>Key limitations</h3>
          <ul className="plain">
            <li>Small samples: ML arms take 0–4% of rows; intervals are wide.</li>
            <li>Rule baselines are negative after costs on this stream (B0 and B1).</li>
            <li>Ambiguous trades are never converted; ranges are shown where supported.</li>
            <li>Inherited Phase A limits: survivorship, no volume, undetected small corporate actions.</li>
            <li>Costs are fixed round-trip percentages; no market-impact or capacity modelling.</li>
            <li>Descriptive reporting only; nothing was retuned or re-selected after results.</li>
          </ul>
          {data.reading.length > 0 && <details><summary className="muted sm">Reading notes from the source report</summary><ul className="plain sm">{data.reading.map((t, i) => <li key={i}>{t}</li>)}</ul></details>}
        </section>
      </div>

      <section className="panel">
        <h3>Source provenance</h3>
        <ul className="plain mono">
          <li>{m.experiment} · preregistration {m.preregistration} (sha256 {String(m.preregistration_sha256).slice(0, 12)}…)</li>
          <li>Phase A measured code hash {m.phase_a_measured_code_hash} · registry constant {m.registry_source_code_hash}</li>
          <li>Seed {m.seed} · {m.n_draws} random-filter draws · scikit-learn {m.versions?.scikit_learn ?? "see report"}</li>
          <li>results/nogit-145d6302/phase_b/experiment_1/ — report/{variant}_pooled|year|cap|boot.csv, shuffled_label_check.json, determinism.json, manifest.json, report/report.md</li>
        </ul>
        <div className="muted sm">{m.hash_note}</div>
      </section>
    </>
  );
}
