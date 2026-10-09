import { parseCsv } from "./data";

const BASE = import.meta.env.BASE_URL + "data/exp1/";
export type Variant = "primary" | "strict_htf";
export const SCENARIOS = ["gross", "rt0.10", "rt0.20", "rt0.30"] as const;
export type Scenario = (typeof SCENARIOS)[number];

export interface Pooled {
  arm: string; scenario: string; nTaken: number | null; nResolved: number | null; takeRate: number | null; winRate: number | null;
  expectancy: number | null; pf: number | null; totalR: number | null; maxDD: number | null; amb: number | null;
  ambWorst: number | null; ambBest: number | null;
}
export interface Yearly { year: string; arm: string; scenario: string; nRows: number | null; nTaken: number | null; nResolved: number | null; winRate: number | null; expectancy: number | null; pf: number | null; totalR: number | null; maxDD: number | null }
export interface Cap { arm: string; scenario: string; nUncapped: number | null; nCapped: number | null; peakOpen: number | null; peakDeployed: number | null; expectancy: number | null; pf: number | null; totalR: number | null; maxDD: number | null }
export interface Boot { family: string; versus: string; scenario: string; metric: string; ml: number | null; baseline: number | null; diff: number | null; lo: number | null; hi: number | null; share: number | null; nValid: number | null; nBoot: number | null }
export interface VariantData { pooled: Pooled[]; year: Yearly[]; cap: Cap[]; boot: Boot[] }
export interface Exp1Data {
  variants: Record<Variant, VariantData>;
  manifest: any;
  shuffled: Record<string, { roc_auc: number; band: [number, number]; passed: boolean; n_pos: number; n_neg: number }>;
  determinism: Record<string, boolean>;
  reading: string[];
}

const n = (v: string | undefined) => (v === undefined || v.trim() === "" || v.toLowerCase() === "nan" ? null : Number.isFinite(Number(v)) ? Number(v) : null);

async function get(name: string) {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  const t = await r.text();
  if (/^\s*<!doctype/i.test(t)) throw new Error(`${name}: not found`);
  return t;
}

async function variant(k: Variant): Promise<VariantData> {
  const [p, y, c, b] = await Promise.all(["pooled", "year", "cap", "boot"].map(async (t) => parseCsv(await get(`${k}_${t}.csv`))));
  return {
    pooled: p.map((r) => ({ arm: r.arm, scenario: r.scenario, nTaken: n(r.n_taken), nResolved: n(r.n_resolved), takeRate: n(r.take_rate), winRate: n(r.win_rate),
      expectancy: n(r.expectancy), pf: n(r.profit_factor), totalR: n(r.total_r), maxDD: n(r.max_dd), amb: n(r.ambiguous), ambWorst: n(r.total_r_amb_worst), ambBest: n(r.total_r_amb_best) })),
    year: y.map((r) => ({ year: r.year, arm: r.arm, scenario: r.scenario, nRows: n(r.n_rows), nTaken: n(r.n_taken), nResolved: n(r.n_resolved), winRate: n(r.win_rate),
      expectancy: n(r.expectancy), pf: n(r.profit_factor), totalR: n(r.total_r), maxDD: n(r.max_dd) })),
    cap: c.map((r) => ({ arm: r.arm, scenario: r.scenario, nUncapped: n(r.n_taken_uncapped), nCapped: n(r.n_taken_capped), peakOpen: n(r.capped_peak_open),
      peakDeployed: n(r.capped_peak_deployed), expectancy: n(r.expectancy), pf: n(r.profit_factor), totalR: n(r.total_r), maxDD: n(r.max_dd) })),
    boot: b.map((r) => ({ family: r.family, versus: r.versus, scenario: r.scenario, metric: r.metric, ml: n(r.ml), baseline: n(r.baseline), diff: n(r.diff),
      lo: n(r.ci_lo), hi: n(r.ci_hi), share: n(r.share_positive), nValid: n(r.n_valid), nBoot: n(r.n_boot) })),
  };
}

export async function loadExp1(): Promise<Exp1Data> {
  const [primary, strict, manifest, shuffled, determinism, md] = await Promise.all([
    variant("primary"), variant("strict_htf"), get("manifest.json").then(JSON.parse), get("shuffled_label_check.json").then(JSON.parse),
    get("determinism.json").then(JSON.parse), get("report.md"),
  ]);
  if (!primary.pooled.length) throw new Error("primary_pooled.csv is empty");
  const sec = md.split(/^## Reading the results\s*$/m)[1] ?? "";
  const reading = sec.split(/\r?\n/).filter((l) => l.startsWith("- ")).map((l) => l.slice(2).trim());
  return { variants: { primary, strict_htf: strict }, manifest, shuffled, determinism, reading };
}
