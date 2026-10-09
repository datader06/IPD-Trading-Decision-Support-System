import { useMemo, useState } from "react";
import type { Shared } from "../App";
import type { FeedMeta, FeedRow, Status, Strategy, Timeframe } from "../types";
import { fmt, STATUS_COLORS, STRAT_TEXT } from "../lib/format";
import Detail from "./Detail";

const STRATS: Strategy[] = ["DIT15", "WIT", "MIT"];
const STATUSES: Status[] = ["APPROACHING", "IN ZONE", "CONFIRMED", "NO SETUP"];
type SortKey = "distance_atr" | "distance_pct" | "risk_reward";

interface Props { rows: FeedRow[]; meta: FeedMeta; available: Record<string, Timeframe[]>; shared: Shared }

const sameRow = (a: FeedRow | null, b: FeedRow) => !!a && a.ticker === b.ticker && a.strategy === b.strategy;

export default function Scanner({ rows, meta, available, shared }: Props) {
  const { strategy, setStrategy, selected, select } = shared;
  const [statuses, setStatuses] = useState<Status[]>(["APPROACHING", "IN ZONE", "CONFIRMED"]);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("distance_atr");
  const [asc, setAsc] = useState(true);

  const toggleStatus = (s: Status) =>
    setStatuses((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const view = useMemo(() => {
    const q = query.trim().toUpperCase();
    const keep = rows.filter(
      (r) => (strategy === "ALL" || r.strategy === strategy) && statuses.includes(r.status) && (!q || r.ticker.includes(q)),
    );
    const val = (r: FeedRow) => {
      const v = r[sortKey];
      return v === null ? null : sortKey === "risk_reward" ? v : Math.abs(v);
    };
    return keep.sort((a, b) => {
      const x = val(a), y = val(b);
      if (x === null && y === null) return a.ticker.localeCompare(b.ticker);
      if (x === null) return 1;
      if (y === null) return -1;
      return asc ? x - y : y - x;
    });
  }, [rows, strategy, statuses, query, sortKey, asc]);

  const countOf = (s: Strategy, st: Status) => meta.status_by_strategy[s]?.[st] ?? 0;
  const problems = rows.filter((r) => r.data_note && !r.data_note.startsWith("DEMO"));

  return (
    <>
      {/* Strategy summary cards */}
      <section className="strat-cards" aria-label="Strategy overview">
        {STRATS.map((s) => (
          <button
            key={s}
            className={"strat-card" + (strategy === s ? " active" : "")}
            onClick={() => setStrategy(strategy === s ? "ALL" : s)}
            aria-pressed={strategy === s}
          >
            <div className="strat-card-name">{s}</div>
            <div className="strat-card-sub">{STRAT_TEXT[s]}</div>
            <div className="strat-card-counts">
              {STATUSES.map((st) => (
                <div key={st} className="strat-count">
                  <div className="n" style={{ color: STATUS_COLORS[st] }}>{countOf(s, st)}</div>
                  <div className="l">{st === "NO SETUP" ? "none" : st === "IN ZONE" ? "in zone" : st.toLowerCase()}</div>
                </div>
              ))}
            </div>
          </button>
        ))}
      </section>

      {/* Filter toolbar */}
      <div className="toolbar" role="toolbar" aria-label="Scanner filters">
        <div className="toolbar-group">
          <button className={strategy === "ALL" ? "chip on" : "chip"} onClick={() => setStrategy("ALL")}>All</button>
          {STRATS.map((s) => (
            <button key={s} className={strategy === s ? "chip on" : "chip"} onClick={() => setStrategy(s)}>{s}</button>
          ))}
        </div>
        <div className="toolbar-sep" aria-hidden="true" />
        <div className="toolbar-group">
          {STATUSES.map((s) => (
            <button
              key={s}
              className={statuses.includes(s) ? "chip on" : "chip"}
              style={statuses.includes(s) ? { borderColor: STATUS_COLORS[s], color: STATUS_COLORS[s] } : undefined}
              onClick={() => toggleStatus(s)}
              aria-pressed={statuses.includes(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="toolbar-sep" aria-hidden="true" />
        <input
          className="search-input"
          placeholder="Search ticker…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search by ticker"
        />
        <div className="toolbar-group">
          <select
            className="sort-select"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            aria-label="Sort by"
          >
            <option value="distance_atr">Sort: Dist ATR</option>
            <option value="distance_pct">Sort: Dist %</option>
            <option value="risk_reward">Sort: R:R</option>
          </select>
          <button className="chip" onClick={() => setAsc(!asc)} aria-label="Toggle sort direction">
            {asc ? "↑ Asc" : "↓ Desc"}
          </button>
        </div>
      </div>

      {/* Split: table + detail */}
      <div className="scanner-split">
        <section className="tablewrap" aria-label="Scanner results">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Strat</th>
                <th>Status</th>
                <th>Zone</th>
                <th className="r">Price</th>
                <th className="r">Entry</th>
                <th className="r">Dist ATR</th>
                <th className="r">Dist %</th>
                <th className="r">R:R</th>
              </tr>
            </thead>
            <tbody>
              {view.map((r) => (
                <tr
                  key={r.ticker + r.strategy}
                  className={sameRow(selected, r) ? "sel" : ""}
                  onClick={() => select(sameRow(selected, r) ? null : r)}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && select(sameRow(selected, r) ? null : r)}
                  aria-selected={sameRow(selected, r)}
                >
                  <td>
                    <div className="tbl-ticker">{r.ticker.replace(".NS", "")}</div>
                  </td>
                  <td><span className="tbl-strat">{r.strategy}</span></td>
                  <td>
                    <span className="pill" style={{ background: STATUS_COLORS[r.status] }}>{r.status}</span>
                  </td>
                  <td className="muted">{r.zone_type || "—"}</td>
                  <td className="r tbl-price">{fmt(r.current_price)}</td>
                  <td className="r tbl-price">{fmt(r.entry)}</td>
                  <td className="r tbl-price">{r.distance_atr !== null ? fmt(r.distance_atr) : "—"}</td>
                  <td className="r tbl-price">{r.distance_pct !== null ? fmt(r.distance_pct) + "%" : "—"}</td>
                  <td className="r tbl-price">{r.risk_reward !== null ? fmt(r.risk_reward, 1) : "—"}</td>
                </tr>
              ))}
              {view.length === 0 && (
                <tr><td colSpan={9} className="empty-row">No rows match the current filters.</td></tr>
              )}
            </tbody>
          </table>
          <div className="table-foot">
            {view.length} of {rows.length} rows · {meta.problems} flagged "insufficient data"
            {problems.length ? ` (${problems.map((p) => p.ticker.replace(".NS", "")).join(", ")})` : ""}
          </div>
        </section>

        <Detail row={selected} available={available} />
      </div>
    </>
  );
}
