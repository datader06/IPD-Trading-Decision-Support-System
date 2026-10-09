import { useEffect, useState } from "react";
import type { Candle, FeedRow, Timeframe } from "../types";
import { loadCandles } from "../lib/data";
import { DEFAULT_TF, fmt, fmtTime, STATUS_COLORS, STRAT_TEXT } from "../lib/format";
import CandleChart from "./CandleChart";

const ORDER: Timeframe[] = ["15m", "60m", "1d"];

function LevelCell({ cls, label, value }: { cls: string; label: string; value: string }) {
  return (
    <div className={`level-cell ${cls}`}>
      <div className="lk">{label}</div>
      <div className="lv">{value}</div>
    </div>
  );
}

function KVRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="kv-row">
      <span className="kk">{k}</span>
      <span className="vv">{v}</span>
    </div>
  );
}

export default function Detail({ row, available }: { row: FeedRow | null; available: Record<string, Timeframe[]> }) {
  const tfs = row ? ORDER.filter((t) => available[row.ticker]?.includes(t)) : [];
  const [tf, setTf] = useState<Timeframe | null>(null);
  const [candles, setCandles] = useState<Candle[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const key = row ? row.ticker + row.strategy : "";
  const want = row ? (tfs.includes(DEFAULT_TF[row.strategy]) ? DEFAULT_TF[row.strategy] : tfs[0] ?? null) : null;
  useEffect(() => setTf(want), [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setCandles(null);
    setErr(null);
    if (!row || !tf) return;
    let live = true;
    loadCandles(row.ticker, tf).then((c) => live && setCandles(c)).catch((e) => live && setErr(String(e.message ?? e)));
    return () => { live = false; };
  }, [row?.ticker, tf]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!row) {
    return (
      <aside className="detail" aria-label="Trade detail">
        <div className="detail-empty">
          <div className="detail-empty-icon" aria-hidden="true">◎</div>
          <div>Select a row to see the trade plan and chart</div>
        </div>
      </aside>
    );
  }

  const hasPlan = row.entry !== null && row.stop !== null && row.target !== null;
  const distPctStr = row.distance_pct !== null ? fmt(row.distance_pct) + "%" : "n/a";
  const distAtrStr = row.distance_atr !== null ? fmt(row.distance_atr) + " ATR" : "n/a";

  return (
    <aside className="detail" aria-label="Trade detail">
      {/* Header */}
      <div className="detail-header">
        <div>
          <div className="detail-ticker">{row.ticker.replace(".NS", "")}</div>
          <div className="detail-strat">{row.strategy} · {STRAT_TEXT[row.strategy]}</div>
        </div>
        <span className="pill" style={{ background: STATUS_COLORS[row.status] }}>{row.status}</span>
      </div>

      {/* Status caveats */}
      {row.status === "APPROACHING" && (
        <div className="approach-hint">
          ⚠ Price is approaching the entry zone — the setup has <strong>not</strong> triggered or been confirmed.
        </div>
      )}
      {!hasPlan && (
        <div className="no-plan-hint">
          {row.data_note && !row.data_note.startsWith("DEMO") ? row.data_note : "No live setup for this ticker."}
        </div>
      )}

      {/* Chart */}
      <div className="chart-wrap">
        <div className="chartbar">
          <span className="detail-section-label">Chart</span>
          <div style={{ display: "flex", gap: ".25rem" }}>
            {tfs.map((t) => (
              <button key={t} className={t === tf ? "chip on" : "chip"} onClick={() => setTf(t)}>{t}</button>
            ))}
          </div>
        </div>
        {tfs.length === 0 ? (
          <div className="chartmsg">No cached candle data available (candles are only bundled for tickers with a live setup).</div>
        ) : err ? (
          <div className="chartmsg" style={{ color: "var(--err-txt)" }}>Could not load {tf} candles: {err}</div>
        ) : !candles ? (
          <div className="chartmsg">Loading {tf} candles…</div>
        ) : candles.length === 0 ? (
          <div className="chartmsg">The {tf} file contains no valid candles.</div>
        ) : (
          <CandleChart candles={candles} row={row} />
        )}
        <div className="legend xs muted" style={{ marginTop: ".4rem" }}>
          <i style={{ background: "#60a5fa" }} />Entry
          <i style={{ background: "#f87171" }} />Stop
          <i style={{ background: "#4ade80" }} />Target
          <i style={{ background: "#a78bfa" }} />HTF zone
          <i style={{ background: "#f5a524" }} />LTF zone
        </div>
      </div>

      {/* Trade levels */}
      {hasPlan && (
        <div className="detail-section">
          <div className="detail-section-label">Trade Levels</div>
          <div className="levels-grid">
            <LevelCell cls="entry"  label="Entry"  value={fmt(row.entry)} />
            <LevelCell cls="stop"   label="Stop"   value={fmt(row.stop)} />
            <LevelCell cls="target" label="Target" value={fmt(row.target)} />
            <LevelCell cls="rr"     label="R : R"  value={row.risk_reward !== null ? fmt(row.risk_reward, 1) + "×" : "n/a"} />
            <LevelCell cls="risk"   label="Risk"   value={fmt(row.risk)} />
            <LevelCell cls=""       label="Current" value={fmt(row.current_price)} />
          </div>
        </div>
      )}

      {/* Zone bands */}
      <div className="detail-section">
        <div className="detail-section-label">Zone Bands</div>
        <div className="kv-list">
          <KVRow k="HTF proximal" v={fmt(row.htf_proximal)} />
          <KVRow k="HTF distal"   v={fmt(row.htf_distal)} />
          <KVRow k="LTF proximal" v={fmt(row.ltf_proximal)} />
          <KVRow k="LTF distal"   v={fmt(row.ltf_distal)} />
          <KVRow k="Zone type"    v={row.zone_type || "n/a"} />
        </div>
      </div>

      {/* Setup context */}
      <div className="detail-section">
        <div className="detail-section-label">Setup Context</div>
        <div className="kv-list">
          <KVRow k="Trend"      v={row.trend || "n/a"} />
          <KVRow k="HTF formed" v={fmtTime(row.htf_formed_at)} />
          <KVRow k="LTF formed" v={fmtTime(row.ltf_formed_at)} />
          <KVRow k="Triggered"  v={fmtTime(row.triggered_at)} />
          <KVRow k="Price time" v={fmtTime(row.price_time)} />
        </div>
      </div>

      {/* Explainability — real fields only, no invented scores */}
      <div className="detail-section">
        <div className="detail-section-label">Setup Metrics</div>
        <div className="signal-grid">
          <div className="signal-cell">
            <div className="sk">Dist to entry</div>
            <div className="sv">{fmt(row.distance_to_entry)}</div>
          </div>
          <div className="signal-cell">
            <div className="sk">Dist %</div>
            <div className="sv">{distPctStr}</div>
          </div>
          <div className="signal-cell">
            <div className="sk">Dist (ATR)</div>
            <div className="sv">{distAtrStr}</div>
          </div>
          <div className="signal-cell">
            <div className="sk">Open R</div>
            <div className="sv">{fmt(row.open_r)}</div>
          </div>
        </div>
        {row.data_note && !row.data_note.startsWith("DEMO") && (
          <div className="xs muted" style={{ marginTop: ".4rem" }}>Note: {row.data_note}</div>
        )}
      </div>
    </aside>
  );
}
