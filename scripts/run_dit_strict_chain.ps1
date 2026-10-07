# Original DIT from 2021, V2 with HTF cap 3 and LTF cap 3 (experiment), 3 workers at low priority. Pipeline then exit scoring.
Set-Location E:\dz-engine
$env:PYTHONDONTWRITEBYTECODE = '1'
$L = 'data\cache'
python scripts/run_dit_kite.py --htf-cap=3 --ltf-cap=3 --workers=3 *> "$L\dit_strict.log"
if ($LASTEXITCODE -eq 0) {
  python scripts/run_dit_kite_replay.py --htf-cap=3 --ltf-cap=3 *> "$L\dit_strict_replay.log"
  "DONE" | Out-File "$L\dit_strict_done.txt"
}
