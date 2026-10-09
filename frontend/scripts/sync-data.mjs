// Read-only copy of the scanner feed and the cached OHLC for tickers with a live setup into public/data.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const out = path.resolve(here, "..", "public", "data");
const srcDir = path.join(root, "results", "scanner_demo_smoke");
const framesDir = path.join(root, "data", "cache", "kite_frames_dit15_long");
const feedName = "scanner_feed_asof_2026-10-01.csv";
const TFS = ["15m", "60m", "1d"];

fs.mkdirSync(path.join(out, "ohlc"), { recursive: true });
for (const f of [feedName, "scanner_feed_meta.json"]) {
  if (!fs.existsSync(path.join(srcDir, f))) throw new Error(`Missing source: ${path.join(srcDir, f)}`);
  fs.copyFileSync(path.join(srcDir, f), path.join(out, f));
}

const lines = fs.readFileSync(path.join(srcDir, feedName), "utf8").trim().split(/\r?\n/);
const head = lines[0].split(",");
const ti = head.indexOf("ticker"), si = head.indexOf("status");
const tickers = [...new Set(lines.slice(1).map((l) => l.split(",")).filter((c) => c[si] !== "NO SETUP").map((c) => c[ti]))];

const manifest = {};
for (const t of tickers) {
  manifest[t] = [];
  for (const tf of TFS) {
    const src = path.join(framesDir, `${t}__${tf}.csv`);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(out, "ohlc", `${t}__${tf}.csv`));
      manifest[t].push(tf);
    }
  }
}
fs.writeFileSync(path.join(out, "ohlc-manifest.json"), JSON.stringify({ feed: feedName, tickers: manifest }, null, 1));
console.log(`synced feed + OHLC for ${tickers.length} tickers: ${tickers.join(", ")}`);

// Phase A frozen artifacts (read-only copies)
const pit = path.join(root, "results", "nogit-145d6302", "phase_a", "pit");
fs.mkdirSync(path.join(out, "phase_a"), { recursive: true });
for (const f of ["report.txt", "run_info.txt", "candidates.csv"]) {
  const src = path.join(pit, f);
  if (!fs.existsSync(src)) throw new Error(`Missing source: ${src}`);
  fs.copyFileSync(src, path.join(out, "phase_a", f));
}
console.log("synced Phase A pit artifacts");

// Experiment 1 frozen artifacts (read-only copies)
const exp1 = path.join(root, "results", "nogit-145d6302", "phase_b", "experiment_1");
fs.mkdirSync(path.join(out, "exp1"), { recursive: true });
const exp1Files = ["manifest.json", "shuffled_label_check.json", "determinism.json", "report/report.md", "report/report_manifest.json",
  ...["primary", "strict_htf"].flatMap((k) => ["pooled", "year", "cap", "boot"].map((t) => `report/${k}_${t}.csv`))];
for (const f of exp1Files) {
  const src = path.join(exp1, f);
  if (!fs.existsSync(src)) throw new Error(`Missing source: ${src}`);
  fs.copyFileSync(src, path.join(out, "exp1", path.basename(f)));
}
console.log("synced Experiment 1 artifacts");

// Experiment 2 / ML layer artifacts (read-only copies)
const mlcore = path.join(root, "results", "ml_core");
const run2 = fs.readdirSync(mlcore).filter((d) => /^exp2_/.test(d)).sort().pop();
fs.mkdirSync(path.join(out, "exp2"), { recursive: true });
const exp2Files = [[run2, "summary.json"], [run2, "dataset_manifest.json"], [run2, "per_strategy.csv"], [run2, "auc.csv"], [run2, "bootstrap.csv"], [".", "edge_check.csv"]];
for (const [d, f] of exp2Files) {
  const src = path.join(mlcore, d, f);
  if (!fs.existsSync(src)) throw new Error(`Missing source: ${src}`);
  fs.copyFileSync(src, path.join(out, "exp2", f));
}
console.log(`synced Experiment 2 artifacts (${run2})`);
