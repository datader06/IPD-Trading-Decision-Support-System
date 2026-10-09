import { useEffect, useState } from "react";
import { loadFeed } from "./lib/data";
import type { FeedMeta, FeedRow, Strategy, Timeframe } from "./types";
import Scanner from "./components/Scanner";
import PhaseA from "./components/PhaseA";
import Experiment1 from "./components/Experiment1";
import Experiment2 from "./components/Experiment2";
import Methodology from "./components/Methodology";

const TABS = ["Scanner", "Phase A", "Experiment 1", "Experiment 2", "Methodology"] as const;
type Tab = (typeof TABS)[number];

export interface Shared {
  strategy: Strategy | "ALL";
  setStrategy: (s: Strategy | "ALL") => void;
  selected: FeedRow | null;
  select: (r: FeedRow | null) => void;
}

interface Loaded { rows: FeedRow[]; meta: FeedMeta; available: Record<string, Timeframe[]> }

export default function App() {
  const [tab, setTab] = useState<Tab>("Scanner");
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<Strategy | "ALL">("ALL");
  const [selected, select] = useState<FeedRow | null>(null);

  useEffect(() => {
    loadFeed().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, []);

  const shared: Shared = { strategy, setStrategy, selected, select };
  const asOf = data?.meta.as_of_dates.at(-1);

  return (
    <div className="app">
      <nav className="topnav" role="navigation" aria-label="Main navigation">
        <div className="brand">
          <div className="brand-icon" aria-hidden="true">Σ</div>
          <span className="brand-name">IPD Terminal</span>
        </div>
        <div className="brand-sep" aria-hidden="true" />
        <div className="nav-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={`nav-tab${tab === t ? " on" : ""}${t === "Scanner" ? " primary" : ""}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="nav-spacer" />
        {asOf && (
          <div className="freshness-badge" title={`Data snapshot as of ${asOf}. Not live market data.`}>
            <span className="dot" aria-hidden="true" />
            <span>Historical snapshot · {asOf}{data ? ` · ${data.meta.tickers} tickers` : ""}</span>
          </div>
        )}
      </nav>

      <main className="main-content">
        {tab === "Scanner" && (
          <>
            <div className="data-notice" role="status">
              <b>DEMO DATA</b>
              <span className="sep">·</span>
              <span>Cached market snapshot — not live. Scanner setups are research candidates only; APPROACHING means price is near the zone, not that a trade has triggered.</span>
            </div>
            {error ? (
              <div className="err-block">Could not load scanner data: {error}. Run <code>npm run sync</code> in <code>frontend/</code>.</div>
            ) : data ? (
              <Scanner {...data} shared={shared} />
            ) : (
              <div className="muted" style={{ padding: "3rem 1rem", textAlign: "center" }}>Loading scanner data…</div>
            )}
          </>
        )}
        {tab === "Phase A"      && <div className="research-wrap"><PhaseA shared={shared} goScanner={() => setTab("Scanner")} /></div>}
        {tab === "Experiment 1" && <div className="research-wrap"><Experiment1 shared={shared} goScanner={() => setTab("Scanner")} goPhaseA={() => setTab("Phase A")} /></div>}
        {tab === "Experiment 2" && <Experiment2 shared={shared} goScanner={() => setTab("Scanner")} />}
        {tab === "Methodology"  && <div className="research-wrap"><Methodology shared={shared} goScanner={() => setTab("Scanner")} /></div>}
      </main>
    </div>
  );
}
