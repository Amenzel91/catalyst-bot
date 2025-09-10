Param(
  [switch]$Once = $false,
  [int]$LoopSeconds = 60
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location -Path (Resolve-Path "$PSScriptRoot\..\..") | Out-Null

# Activate venv if present
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

New-Item -ItemType Directory -Force -Path "out\logs" | Out-Null
$env:FEATURE_HEARTBEAT = $env:FEATURE_HEARTBEAT -bor "1"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "out\logs\catalyst_$ts.log"

if ($Once) {
  python -m catalyst_bot.runner --once *>> $log
} else {
  $env:LOOP_SECONDS = "$LoopSeconds"
  python -m catalyst_bot.runner *>> $log
}

Write-Host "Logs: $log"