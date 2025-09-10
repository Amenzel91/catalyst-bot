Param(
  [string]$TaskName = "CatalystBot Nightly",
  [string]$StartTime = "02:00"
)

$ErrorActionPreference = "Stop"
$here = (Split-Path -Parent $MyInvocation.MyCommand.Path)
$start = Join-Path $here "Start-CatalystBot.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$start`""
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Parse($StartTime))
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName $TaskName -Description "Run Catalyst Bot nightly" -Force

Write-Host "Registered task '$TaskName' at $StartTime"