import { parseCsv } from "./data";

const BASE = import.meta.env.BASE_URL + "data/phase_a/";

export interface Stat {
  label: string;
  n: number; w: number; l: number; amb: number; open: number; cens: number; nofill: number;
  winPct: number; ciLo: number; ciHi: number; expR: number; pf: number; totR: number; maxDD: number;
  ambWinLo?: number; ambWinHi?: number; ambTotLo?: number; ambTotHi?: number;
}
export interface CurvePoint { date: string; cum: number }
export interface PhaseAData {
  header: string;
  codeHash: string;
  runId: string;
  gross: Stat[];                       // B0 ALL, per-year, TRAIN, HOLDOUT
  costs: Record<string, Stat[]>;       // "0.10" | "0.20" | "0.30" -> ALL, TRAIN, HOLDOUT
  capped: Stat[];
  ambReasons: Record<string, number>;
  rupees: string | null;
  caExcluded: string[];
  curve: CurvePoint[];
  curveCheck: { n: number; w: number; l: number; amb: number; totR: number };
}

const STAT = /^\s*(.+?)\s+n=\s*(\d+) W=\s*(\d+) L=\s*(\d+) AMB=\s*(\d+) OPEN=\s*(\d+) CENS=\s*(\d+) NOFILL=\s*(\d+) win%=\s*([\d.]+)\s+\[(\d+)-(\d+)\] expR=([+-][\d.]+) PF=([\d.]+) totR=\s*([+-][\d.]+) maxDD_R=\s*([\d.]+)/;
const BOUNDS = /AMBIGUOUS bounds: win% ([\d.]+)\.\.([\d.]+), totR ([+-][\d.]+)\.\.([+-][\d.]+)/;

function parseReport(text: string) {
  const lines = text.split(/\r?\n/);
  const gross: Stat[] = [], capped: Stat[] = [];
  const costs: Record<string, Stat[]> = {};
  let section: "pre" | "gross" | "cost" | "cap" | "relaxed" = "pre";
  let scen = "";
  let last: Stat | null = null;
  let ambReasons: Record<string, number> = {};
  let rupees: string | null = null;
  const caExcluded: string[] = [];
  for (const ln of lines) {
    if (ln.startsWith("=== B0")) section = "gross";
    else if (ln.startsWith("=== RELAXED")) section = "relaxed";
    else if (ln.startsWith("-- B0 net of costs")) {
      const m = ln.match(/rt(\d\.\d\d)/);
      scen = m ? m[1] : "";
      section = "cost";
      costs[scen] = [];
    } else if (ln.startsWith("-- B0 capital-constrained")) section = "cap";
    else if (ln.includes("CA-excluded:")) caExcluded.push(ln.replace("CA-excluded:", "").trim());
    else if (ln.startsWith("AMBIGUOUS reasons (B0):")) {
      try { ambReasons = JSON.parse(ln.slice(ln.indexOf("{")).replace(/'/g, '"')); } catch { ambReasons = {}; }
    } else if (ln.startsWith("rupees")) rupees = ln.trim();

    const m = ln.match(STAT);
    if (m && section !== "relaxed" && section !== "pre") {
      const s: Stat = {
        label: m[1], n: +m[2], w: +m[3], l: +m[4], amb: +m[5], open: +m[6], cens: +m[7], nofill: +m[8],
        winPct: +m[9], ciLo: +m[10], ciHi: +m[11], expR: +m[12], pf: +m[13], totR: +m[14], maxDD: +m[15],
      };
      (section === "gross" ? gross : section === "cap" ? capped : costs[scen]).push(s);
      last = s;
      continue;
    }
    const b = ln.match(BOUNDS);
    if (b && last) {
      last.ambWinLo = +b[1]; last.ambWinHi = +b[2]; last.ambTotLo = +b[3]; last.ambTotHi = +b[4];
    }
  }
  return { header: lines[0] ?? "", gross, costs, capped, ambReasons, rupees, caExcluded };
}

async function text(name: string): Promise<string> {
  const r = await fetch(BASE + name);
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  const t = await r.text();
  if (/^\s*<!doctype/i.test(t)) throw new Error(`${name}: not found`);
  return t;
}

export async function loadPhaseA(): Promise<PhaseAData> {
  const [rep, info, cand] = await Promise.all([text("report.txt"), text("run_info.txt"), text("candidates.csv")]);
  const parsed = parseReport(rep);
  if (!parsed.gross.length) throw new Error("report.txt: B0 results not found");
  const run = parsed.header.match(/run=(\S+)/)?.[1] ?? "unknown";
  const codeHash = info.match(/code_hash=(\S+)/)?.[1] ?? "unknown";

  // B0 strict set: is_b0, not corporate-action excluded, entries from 2021-01-01 (as in the report).
  const b0 = parseCsv(cand)
    .filter((r) => r.is_b0 === "True" && r.ca_excluded !== "True" && r.entry_time >= "2021-01-01")
    .sort((a, b) => (a.exit_time || "").localeCompare(b.exit_time || ""));
  let cum = 0, w = 0, l = 0, amb = 0;
  const curve: CurvePoint[] = [];
  for (const r of b0) {
    if (r.outcome === "AMBIGUOUS") amb++;
    else if (r.outcome === "WIN" || r.outcome === "LOSS") {
      const v = Number(r.r);
      if (!Number.isFinite(v)) continue;
      cum += v;
      if (r.outcome === "WIN") w++; else l++;
      curve.push({ date: r.exit_time.slice(0, 10), cum });
    }
  }
  return { ...parsed, codeHash, runId: run, curve, curveCheck: { n: b0.length, w, l, amb, totR: cum } };
}
