# DIT15 (HTF daily, trend 2h, LTF 15m) from 2021: V2 with the strict HTF legout (--strict-htf, removes about 20% of trades), LTF base cap 5, HTF cap default.
# The LTF cap-3 result is the subset of these trades with ltf_base_count <= 3. 3 workers, low priority; per-ticker checkpoints (rerun to resume).
Set-Location E:\dz-engine
$env:PYTHONDONTWRITEBYTECODE = '1'
$L = 'data\cache'
python scripts/run_dit15_long.py --strict-htf --workers=3 *> "$L\dit15_sh.log"
if ($LASTEXITCODE -eq 0) {
  python scripts/run_dit15_replay.py --strict-htf *> "$L\dit15_sh_replay.log"
  "DONE" | Out-File "$L\dit15_sh_done.txt"
}
