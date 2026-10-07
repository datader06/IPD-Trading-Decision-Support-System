# Mirror the project to E:\dz_backup (skips .env, tokens, __pycache__). Low priority, incremental (robocopy copies only changed files).
$src = 'E:\dz-engine'; $dst = 'E:\dz_backup'
New-Item -ItemType Directory -Force $dst | Out-Null
$xf = @('.env', '*token*', '*.pyc'); $xd = @('__pycache__')
# code, docs, tests, results, git history: mirror (deletions follow the source)
foreach ($d in 'scripts','src','docs','tests','results','.git','.claude','photos imrove') { robocopy "$src\$d" "$dst\$d" /MIR /XF $xf /XD $xd /MT:2 /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null }
foreach ($f in 'config.py','CLAUDE.md','kite_login.py','test_kite.py','mit review.docx','basecandlefix.docx','.gitignore','.env.example') { if (Test-Path "$src\$f") { Copy-Item "$src\$f" "$dst\$f" -Force } }
# data caches: copy new/changed files, never delete (kite minute cache, frames, checkpoints, logs)
foreach ($d in 'kite','kite_frames','kite_frames_wit_long','kite_frames_dit15_long','yahoo','checkpoints') { robocopy "$src\data\cache\$d" "$dst\data\cache\$d" /E /XF $xf /MT:2 /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null }
robocopy "$src\data\cache" "$dst\data\cache" *.log *.txt /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
"backup finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$dst\LAST_BACKUP.txt"
