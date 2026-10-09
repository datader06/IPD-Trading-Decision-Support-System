import type { Candle, FeedMeta, FeedRow, Timeframe } from "../types";

const BASE = import.meta.env.BASE_URL + "data/";

export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; }
      else cur += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
    else if (c !== "\r") cur += c;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const [head, ...body] = rows;
  return body.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

const num = (v: string | undefined): number | null => {
  if (v === undefined || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

async function get(name: string): Promise<string> {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  const t = await r.text();
  // Vite's dev server answers unknown paths with index.html
  if (/^\s*<!doctype/i.test(t)) throw new Error(`${name}: not found`);
  return t;
}

export async function loadFeed(): Promise<{ rows: FeedRow[]; meta: FeedMeta; available: Record<string, Timeframe[]> }> {
  const man = JSON.parse(await get("ohlc-manifest.json"));
  const meta: FeedMeta = JSON.parse(await get("scanner_feed_meta.json"));
  const rows = parseCsv(await get(man.feed)).map((r) => ({
    ticker: r.ticker, strategy: r.strategy, as_of: r.as_of, price_time: r.price_time, status: r.status,
    zone_type: r.zone_type, trend: r.trend, htf_formed_at: r.htf_formed_at, ltf_formed_at: r.ltf_formed_at,
    triggered_at: r.triggered_at, data_note: r.data_note,
    current_price: num(r.current_price), entry: num(r.entry), stop: num(r.stop), target: num(r.target),
    risk: num(r.risk), risk_reward: num(r.risk_reward), distance_to_entry: num(r.distance_to_entry),
    distance_pct: num(r.distance_pct), distance_atr: num(r.distance_atr), htf_proximal: num(r.htf_proximal),
    htf_distal: num(r.htf_distal), ltf_proximal: num(r.ltf_proximal), ltf_distal: num(r.ltf_distal), open_r: num(r.open_r),
  })) as FeedRow[];
  return { rows, meta, available: man.tickers };
}

// Naive exchange-local timestamps are treated as UTC so the axis shows the original clock times.
const toTime = (s: string, daily: boolean): number | string => {
  if (daily) return s.slice(0, 10);
  const [d, t] = s.split(" ");
  const [y, m, dd] = d.split("-").map(Number);
  const [h, mi] = (t ?? "00:00").split(":").map(Number);
  return Date.UTC(y, m - 1, dd, h, mi) / 1000;
};

const MAX_BARS: Record<Timeframe, number> = { "15m": 600, "60m": 400, "1d": 250 };

export async function loadCandles(ticker: string, tf: Timeframe): Promise<Candle[]> {
  const rows = parseCsv(await get(`ohlc/${ticker}__${tf}.csv`));
  const out: Candle[] = [];
  for (const r of rows) {
    const o = num(r.open), h = num(r.high), l = num(r.low), c = num(r.close);
    if (!r.timestamp || o === null || h === null || l === null || c === null || h < l) continue;
    out.push({ time: toTime(r.timestamp, tf === "1d"), open: o, high: h, low: l, close: c });
  }
  return out.slice(-MAX_BARS[tf]);
}
