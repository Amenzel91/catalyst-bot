# Catalyst-Bot Windows Service Installer
# Uses NSSM (Non-Sucking Service Manager) to create a Windows service
#
# Prerequisites:
#   1. Download NSSM from https://nssm.cc/download
#   2. Extract nssm.exe to a folder (e.g., C:\Tools\nssm)
#   3. Add to PATH or specify full path below
#
# Usage:
#   Install:   .\install-service.ps1 -Action install
#   Start:     .\install-service.ps1 -Action start
#   Stop:      .\install-service.ps1 -Action stop
#   Remove:    .\install-service.ps1 -Action remove
#   Status:    .\install-service.ps1 -Action status

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "start", "stop", "restart", "remove", "status")]
    [string]$Action,

    [string]$ServiceName = "CatalystBot",
    [string]$NssmPath = "nssm"  # Assumes nssm.exe is in PATH
)

$ErrorActionPreference = "Stop"

# Get repository root
$RepoRoot = $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$RunnerModule = "catalyst_bot.runner"
$LogFile = Join-Path $RepoRoot "data\logs\service.log"

# Ensure log directory exists
$LogDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Service {
    Write-Host "Installing $ServiceName service..." -ForegroundColor Cyan

    if (-not (Test-Path $VenvPython)) {
        Write-Error "Virtual environment not found at $VenvPython. Run setup first."
        return
    }

    # Check if service already exists
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warning "Service $ServiceName already exists. Remove it first with: -Action remove"
        return
    }

    # Install service using NSSM
    $nssmArgs = @(
        "install",
        $ServiceName,
        $VenvPython,
        "-m", $RunnerModule,
        "--loop"
    )

    Write-Host "Executing: $NssmPath $nssmArgs" -ForegroundColor Gray
    & $NssmPath $nssmArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Error "NSSM install failed with exit code $LASTEXITCODE"
        return
    }

    # Configure service parameters
    Write-Host "Configuring service parameters..." -ForegroundColor Cyan

    # Set working directory
    & $NssmPath set $ServiceName AppDirectory $RepoRoot

    # Set startup type to automatic
    & $NssmPath set $ServiceName Start SERVICE_AUTO_START

    # Configure stdout/stderr logging
    & $NssmPath set $ServiceName AppStdout $LogFile
    & $NssmPath set $ServiceName AppStderr $LogFile

    # Rotate logs daily (10MB max per file, keep 7 days)
    & $NssmPath set $ServiceName AppRotateFiles 1
    & $NssmPath set $ServiceName AppRotateBytes 10485760

    # Auto-restart on failure (after 60 seconds delay)
    & $NssmPath set $ServiceName AppThrottle 60000
    & $NssmPath set $ServiceName AppExit Default Restart

    # Set display name and description
    & $NssmPath set $ServiceName DisplayName "Catalyst Trading Bot"
    & $NssmPath set $ServiceName Description "Automated penny stock catalyst detection and alerting system"

    Write-Host "`n✅ Service installed successfully!" -ForegroundColor Green
    Write-Host "   Service name: $ServiceName" -ForegroundColor Gray
    Write-Host "   Log file: $LogFile" -ForegroundColor Gray
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "  1. Start service: .\install-service.ps1 -Action start" -ForegroundColor Gray
    Write-Host "  2. Check status: .\install-service.ps1 -Action status" -ForegroundColor Gray
}

function Start-ServiceWrapper {
    Write-Host "Starting $ServiceName service..." -ForegroundColor Cyan
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 2
    Get-ServiceStatus
}

function Stop-ServiceWrapper {
    Write-Host "Stopping $ServiceName service..." -ForegroundColor Cyan
    Stop-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 2
    Get-ServiceStatus
}

function Restart-ServiceWrapper {
    Write-Host "Restarting $ServiceName service..." -ForegroundColor Cyan
    Restart-Service -Name $ServiceName -Force
    Start-Sleep -Seconds 2
    Get-ServiceStatus
}

function Remove-ServiceWrapper {
    Write-Host "Removing $ServiceName service..." -ForegroundColor Cyan

    # Stop service first
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 2
    }

    # Remove using NSSM
    & $NssmPath remove $ServiceName confirm

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Service removed successfully!" -ForegroundColor Green
    } else {
        Write-Error "Failed to remove service (exit code: $LASTEXITCODE)"
    }
}

function Get-ServiceStatus {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    if (-not $svc) {
        Write-Host "`n❌ Service '$ServiceName' not installed" -ForegroundColor Red
        Write-Host "   Install with: .\install-service.ps1 -Action install" -ForegroundColor Gray
        return
    }

    Write-Host "`n📊 Service Status:" -ForegroundColor Cyan
    Write-Host "   Name: $($svc.Name)" -ForegroundColor Gray
    Write-Host "   Display Name: $($svc.DisplayName)" -ForegroundColor Gray

    $statusColor = switch ($svc.Status) {
        "Running" { "Green" }
        "Stopped" { "Red" }
        default { "Yellow" }
    }
    Write-Host "   Status: $($svc.Status)" -ForegroundColor $statusColor
    Write-Host "   Startup Type: $($svc.StartType)" -ForegroundColor Gray

    # Show recent logs
    if (Test-Path $LogFile) {
        Write-Host "`n📄 Recent Logs (last 10 lines):" -ForegroundColor Cyan
        Get-Content $LogFile -Tail 10 | ForEach-Object {
            Write-Host "   $_" -ForegroundColor Gray
        }
    }
}

# Main execution
if (-not (Test-Admin)) {
    Write-Error "This script requires Administrator privileges. Run PowerShell as Administrator."
    exit 1
}

# Check if NSSM is available
$nssmCheck = Get-Command $NssmPath -ErrorAction SilentlyContinue
if (-not $nssmCheck) {
    Write-Error @"
NSSM not found. Please install NSSM:
  1. Download from: https://nssm.cc/download
  2. Extract nssm.exe to a folder (e.g., C:\Tools\nssm)
  3. Add to PATH or specify full path with -NssmPath parameter
"@
    exit 1
}

switch ($Action) {
    "install" { Install-Service }
    "start" { Start-ServiceWrapper }
    "stop" { Stop-ServiceWrapper }
    "restart" { Restart-ServiceWrapper }
    "remove" { Remove-ServiceWrapper }
    "status" { Get-ServiceStatus }
}
