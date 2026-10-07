# WIT from 2021 under the current defaults (V2 cap 5 + HTF legout-over-wick). Steps: fetch older 60m bars (1,006 requests), pipeline (4 workers, low priority), exit scoring.
Set-Location E:\dz-engine
$env:PYTHONDONTWRITEBYTECODE = '1'
$L = 'data\cache'
python scripts/fetch_kite_60m_long.py *> "$L\wit2021_fetch.log"
if ($LASTEXITCODE -eq 0) {
  python scripts/run_wit_kite.py --from=2021-01-01 --frames=kite_frames_wit_long --workers=4 *> "$L\wit2021.log"
  if ($LASTEXITCODE -eq 0) {
    python scripts/run_wit_kite_replay.py --from=2021-01-01 *> "$L\wit2021_replay.log"
    "DONE" | Out-File "$L\wit2021_done.txt"
  }
}
