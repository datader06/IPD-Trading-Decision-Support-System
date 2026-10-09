export type Strategy = "DIT15" | "WIT" | "MIT";
export type Status = "APPROACHING" | "IN ZONE" | "CONFIRMED" | "NO SETUP";
export type Timeframe = "15m" | "60m" | "1d";

export interface FeedRow {
  ticker: string;
  strategy: Strategy;
  as_of: string;
  price_time: string;
  current_price: number | null;
  status: Status;
  zone_type: string;
  entry: number | null;
  stop: number | null;
  target: number | null;
  risk: number | null;
  risk_reward: number | null;
  distance_to_entry: number | null;
  distance_pct: number | null;
  distance_atr: number | null;
  trend: string;
  htf_proximal: number | null;
  htf_distal: number | null;
  ltf_proximal: number | null;
  ltf_distal: number | null;
  htf_formed_at: string;
  ltf_formed_at: string;
  triggered_at: string;
  open_r: number | null;
  data_note: string;
}

export interface FeedMeta {
  label: string;
  as_of_dates: string[];
  note: string;
  tickers: number;
  strategies: Strategy[];
  rows: number;
  status_by_strategy: Record<string, Record<string, number>>;
  status_total: Record<string, number>;
  problems: number;
  definitions: Record<string, number>;
}

export interface Candle { time: number | string; open: number; high: number; low: number; close: number }
