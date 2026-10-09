import type { Shared } from "../App";

const P = ({ children }: { children: React.ReactNode }) => <span className="mono">{children}</span>;

export default function Methodology({ shared, goScanner }: { shared: Shared; goScanner: () => void }) {
  const sel = shared.selected;
  return (
    <>
      {sel && (
        <div className="hint">Scanner selection: <b>{sel.ticker.replace(".NS", "")}</b> · {sel.strategy}.{" "}
          <button className="link" onClick={goScanner}>← Back to Scanner row</button></div>
      )}
      <div className="hint">Everything below describes what exists in this repository. Source paths are given so each statement can be traced. Paths are relative to the project root.</div>

      <section className="panel">
        <h3>What the system does</h3>
        <p>A supply and demand zone research platform for Indian equities (a 503-ticker universe). It finds a higher-timeframe (HTF) zone, matches it to a lower-timeframe (LTF) zone, and defines a trade: <b>entry</b> at the LTF proximal line, <b>stop</b> at the LTF distal line, <b>target</b> at entry ± 2 × risk (risk/reward 2.0). Position sizing in the research is Rs 1,000 risk per trade with a Rs 1,00,000 notional cap and no leverage.</p>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Strategy</th><th>HTF</th><th>Entry timeframe</th></tr></thead>
          <tbody>
            <tr><td><b>DIT15</b></td><td>Daily</td><td>15 minute</td></tr>
            <tr><td><b>WIT</b></td><td>Weekly</td><td>2 hour</td></tr>
            <tr><td><b>MIT</b></td><td>Monthly</td><td>Daily</td></tr>
          </tbody>
        </table></div>
        <div className="muted sm">Sources: <P>src/scanner/feed.py</P> (docstring), <P>docs/PHASE_A_FREEZE.md</P>, <P>docs/PHASE_A_PLAN.md</P>. The scanner chart for WIT uses the cached 60m file because no 2h file exists.</div>
      </section>

      <div className="two">
        <section className="panel">
          <h3>Scanner feed and charts</h3>
          <ul className="plain">
            <li>Built by <P>scripts/run_scanner_feed.py</P> via <P>src/scanner/feed.py</P> from <b>cached</b> frames. Nothing is fetched at build or view time.</li>
            <li>It reuses the strict (B0) zone, matching, trend and replay logic from <P>src/candidates.py</P> (DIT15) and <P>src/candidates_mtf.py</P> (WIT, MIT), but keeps zones that have not triggered yet.</li>
            <li>Statuses: <b>CONFIRMED</b> (entry touched before the latest day, trade still live), <b>IN ZONE</b> (entry touched on the latest day), <b>APPROACHING</b> (LTF zone untouched; price within 3 ATR or 10% of entry), <b>NO SETUP</b>.</li>
            <li>This feed: as of <b>2026-10-01</b>, 100 of 503 tickers sampled, 300 rows (3 strategies). Result: 6 APPROACHING, 294 NO SETUP, no IN ZONE or CONFIRMED. Six MIT rows are flagged “insufficient data”.</li>
            <li>Files: <P>results/scanner_demo_smoke/scanner_feed_asof_2026-10-01.csv</P> and <P>scanner_feed_meta.json</P>. The feed is labelled demo output, not a backtest result and not a frozen baseline.</li>
            <li>Charts: candles from <P>data/cache/kite_frames_dit15_long/</P> (Kite data, split/bonus adjusted per <P>docs/PHASE_A_FREEZE.md</P>; no volume). This app bundles candles only for the tickers with a live setup and trims them to the latest bars.</li>
          </ul>
        </section>
        <section className="panel">
          <h3>Phase A: labelling and evaluating history</h3>
          <ul className="plain">
            <li>Entries from 2021-01-01, offline deterministic replay (<P>src/replay.py</P>): 15m bars, then cached 1-minute drill-down, 90-day horizon.</li>
            <li>Outcomes: <b>WIN</b> (+2R target first), <b>LOSS</b> (−1R stop first), <b>AMBIGUOUS</b> (order cannot be determined), <b>OPEN</b>, <b>CENSORED</b>, <b>NOFILL</b>.</li>
            <li>Metrics use WIN + LOSS only. AMBIGUOUS trades are never converted; bounds show the range either way. Gap fills beyond the stop stay AMBIGUOUS (decision D4).</li>
            <li>Point-in-time trend and bar-close timing; daily moves over 35% flag a corporate action and those trades are excluded.</li>
            <li>Costs: gross R, plus 0.10%, 0.20% and 0.30% round-trip scenarios (decision D6; never tuned). Slippage per side is 0.0%.</li>
            <li>Sources: <P>docs/PHASE_A_FREEZE.md</P>, <P>PHASE_A_RESULTS.md</P>, <P>PHASE_A_MTF_RESULTS.md</P>; data <P>results/nogit-145d6302/phase_a/pit/</P>.</li>
          </ul>
        </section>
      </div>

      <section className="panel">
        <h3>Experiment 1: ML as a take-or-skip filter</h3>
        <ul className="plain">
          <li>Question: can a model, given the same Phase A DIT15 candidates, skip the bad ones? It may only take or skip existing candidates (<P>docs/EXPERIMENT_1_PREREGISTRATION.md</P>, written before any model was trained).</li>
          <li>Data: 4,552 labelled candidates (label 1 = WIN, 0 = LOSS; ambiguous/open rows get no label). 18 features that use only information available at the decision time (<P>docs/PHASE_B_FEATURES_REPORT.md</P>, <P>PHASE_B_LABELS_REPORT.md</P>).</li>
          <li>Models: logistic regression, random forest, HistGradientBoosting, XGBoost; fixed grids, seed 42, native probabilities, no calibration.</li>
          <li>Rule T1: take a candidate when p × 2 − (1 − p) × L − cost &gt; 0 at the 0.20% cost, with no tuned parameter.</li>
          <li>Evaluation: walk-forward folds with embargo and purging (<P>docs/PHASE_B_FOLDS_REPORT.md</P>); pooled out-of-fold test stream 2023H1–2025H2.</li>
          <li>Comparisons: B0 (Phase A rule baseline), B1 (take everything), B2 (random filter with matched take counts, 1,000 draws) and a paired month-block bootstrap. A preregistered champion needs at least 100 resolved takes at 0.20%.</li>
          <li>Outcome: <b>no primary champion; no reliable predictive edge established.</b> The strict-HTF run is a sensitivity analysis only.</li>
          <li>Experiment 2 (<P>docs/EXPERIMENT_2_PREREGISTRATION.md</P>, <P>src/ml_core/</P>, <P>results/ml_core/</P>) pools DIT15, WIT and MIT with timeframe-agnostic features and the same frozen models. Outcome: <b>no edge established</b>; see the Experiment 2 tab.</li>
          <li>Data: <P>results/nogit-145d6302/phase_b/experiment_1/</P>.</li>
        </ul>
      </section>

      <section className="panel">
        <h3>Three things that must not be confused</h3>
        <div className="tablewrap inner"><table>
          <thead><tr><th>Term</th><th>What it is</th><th>What it is not</th></tr></thead>
          <tbody>
            <tr><td><b>Scanner candidate</b></td><td>A rule-based setup that exists as of the feed date, with entry/stop/target levels. Outcome unknown.</td><td>A prediction, a recommendation or a triggered trade. <b>APPROACHING</b> means price is near, not that the setup fired.</td></tr>
            <tr><td><b>Historical backtest result</b></td><td>The replayed outcome of past candidates (Phase A), with the stated costs, ambiguity and data limits.</td><td>A forecast. Gross DIT15 B0 is +0.046R; after any of the three cost scenarios it is negative.</td></tr>
            <tr><td><b>Validated ML trading signal</b></td><td>Would require a model that beats baselines out-of-sample after costs.</td><td>Something this project has produced. Experiment 1 found none, and no model output appears in the scanner.</td></tr>
          </tbody>
        </table></div>
      </section>

      <div className="two">
        <section className="panel">
          <h3>Provenance and frozen artifacts</h3>
          <ul className="plain">
            <li>Phase A baselines were frozen on 8 Oct 2026 (<P>docs/PHASE_A_FREEZE.md</P>); strategy code is not to be changed without declaring a new baseline.</li>
            <li>Run <b>nogit-145d6302</b>; the measured code hash of the data in use is <b>e5e09db7</b>, while the registry constant is <b>cd73bf8d</b>. The mismatch is documented in the preregistration and not changed; the data reproduce the frozen DIT15 B0 counts (318 trades; 91 / 167 / 60).</li>
            <li>The freeze document lists the DIT15 folder as <P>phase_a/pit_refetch/</P>. That folder is not present in this working copy, so this app reads <P>phase_a/pit/</P>, whose B0 figures match.</li>
            <li>Experiment 1 inputs are SHA-256 verified against its manifest. The second identical run reproduced all outputs.</li>
            <li>The Phase A, Experiment 1 and scanner files are read-only copies; this app does not change them.</li>
          </ul>
        </section>
        <section className="panel">
          <h3>Major limitations</h3>
          <ul className="plain">
            <li><b>Not live.</b> The scanner is a single as-of snapshot built from cached data on 100 sampled tickers; it is not live trading advice.</li>
            <li><b>Ambiguity.</b> 60 of 318 DIT15 B0 trades remain AMBIGUOUS; results are shown with bounds.</li>
            <li><b>Costs.</b> Fixed round-trip percentages; no broker-specific or market-impact modelling.</li>
            <li><b>Holdout.</b> The 2026 holdout (781 rows) was deliberately not scored in Experiment 1, and 2026 is partly contaminated by chart reviews.</li>
            <li><b>Data.</b> Survivorship (current universe), undetected corporate actions under 35%, no volume in the frames, the 15:15 bar missing since 2026-08-03.</li>
            <li><b>Samples.</b> Small: WIT and MIT baselines rest on few trades; ML arms took 0–4% of rows.</li>
            <li><b>Coverage.</b> Phase A and Experiment 1 tabs here show DIT15 only; WIT/MIT frozen figures exist in the docs but are not displayed.</li>
          </ul>
        </section>
      </div>
    </>
  );
}
