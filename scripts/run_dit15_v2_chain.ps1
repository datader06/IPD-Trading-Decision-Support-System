# DIT15 under base logic V2 (LTF cap 5 default): pipeline (2 workers, low priority), exit scoring, comparison with Baseline v1.
# Checkpoints per ticker (data/cache/checkpoints/dit15_v2_cap5): rerun this script to resume after a crash.
Set-Location E:\dz-engine
$env:PYTHONDONTWRITEBYTECODE = '1'
$L = 'data\cache'
python scripts/run_dit15_kite.py --workers=2 *> "$L\v2_dit15.log"
if ($LASTEXITCODE -eq 0) {
  python scripts/run_dit15_replay.py *> "$L\v2_dit15_replay.log"
  $new = (Get-ChildItem "results\*\trades_dit15_kite_2024_v2_cap5_final.csv" | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
  python scripts/compare_newbase.py dit15 $new "results\53aecde\baseline_v1_dit15.csv" *> "$L\v2_dit15_vs_v1.log"
  "DONE $new" | Out-File "$L\v2_dit15_done.txt"
}
