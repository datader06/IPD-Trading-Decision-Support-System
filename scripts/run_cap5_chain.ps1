# LTF base cap 5 (HTF stays 5): exact reruns of MIT, WIT, DIT15 with the new base logic, then exit scoring and comparisons.
# Logs: data/cache/cap5_*.log. DIT15 checkpoints per ticker (rerun this script to resume).
Set-Location E:\dz-engine
$env:PYTHONDONTWRITEBYTECODE = '1'
$L = 'data\cache'
python scripts/run_mit_kite.py --new-base --ltf-cap=5 *> "$L\cap5_mit.log"
python scripts/run_mit_kite_replay.py --new-base --ltf-cap=5 *> "$L\cap5_mit_replay.log"
python scripts/run_wit_kite.py --new-base --ltf-cap=5 --workers=5 *> "$L\cap5_wit.log"
python scripts/run_wit_kite_replay.py --new-base --ltf-cap=5 *> "$L\cap5_wit_replay.log"
python scripts/run_dit15_kite.py --new-base --ltf-cap=5 --workers=5 *> "$L\cap5_dit15.log"
python scripts/run_dit15_replay.py --new-base --ltf-cap=5 *> "$L\cap5_dit15_replay.log"
foreach ($c in 'mit','wit','dit15') {
  $new = (Get-ChildItem "results\*\trades_${c}_kite_2024_newbase_cap5_final.csv" | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
  python scripts/compare_newbase.py $c $new "results\53aecde\baseline_v1_$c.csv" *> "$L\cap5_${c}_vs_v1.log"
  $cap8 = "results\e7842da\trades_${c}_kite_2024_newbase_baseline_v1_style.csv"
  if ($c -eq 'mit') { $cap8 = "results\e7842da\baseline_v1_style_mit_newbase.csv" }
  python scripts/compare_newbase.py $c $new $cap8 *> "$L\cap5_${c}_vs_cap8.log"
}
"CHAIN DONE" | Out-File "$L\cap5_done.txt"
