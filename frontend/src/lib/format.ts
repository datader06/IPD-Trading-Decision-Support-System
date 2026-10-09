import type { Timeframe } from "../types";

export const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "n/a" : v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtTime = (s: string) => (s && s.trim() ? s.replace(/:00$/, "") : "n/a");
export const STATUS_COLORS: Record<string, string> = {
  APPROACHING: "#f5a524", "IN ZONE": "#22d3ee", CONFIRMED: "#34d399", "NO SETUP": "#6b7788",
};
export const STRAT_TEXT: Record<string, string> = {
  DIT15: "Daily HTF, 15m entry", WIT: "Weekly HTF, 2h entry", MIT: "Monthly HTF, daily entry",
};
export const DEFAULT_TF: Record<string, Timeframe> = { DIT15: "15m", WIT: "60m", MIT: "1d" };
