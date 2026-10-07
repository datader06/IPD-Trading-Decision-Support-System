# Run backup.ps1 now and every 30 minutes until the DIT15 strict run writes its done file, then once more.
$p = Get-Process -Id $PID; $p.PriorityClass = 'BelowNormal'
Set-Location E:\dz-engine
while ($true) {
  & powershell -NoProfile -File E:\dz-engine\scripts\backup.ps1
  if (Test-Path 'E:\dz-engine\data\cache\dit15_sh_done.txt') { & powershell -NoProfile -File E:\dz-engine\scripts\backup.ps1; break }
  Start-Sleep -Seconds 1800
}
