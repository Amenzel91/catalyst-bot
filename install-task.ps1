# Catalyst-Bot Task Scheduler Setup
# Creates a Windows Scheduled Task that runs on startup and auto-restarts on failure
#
# Usage:
#   Install:   .\install-task.ps1 -Action install
#   Remove:    .\install-task.ps1 -Action remove
#   Status:    .\install-task.ps1 -Action status

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "remove", "status", "start", "stop")]
    [string]$Action,

    [string]$TaskName = "CatalystBot"
)

$ErrorActionPreference = "Stop"

# Get repository root
$RepoRoot = $PSScriptRoot
$BatchFile = Join-Path $RepoRoot "start_service.bat"

function Test-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Task {
    Write-Host "Installing $TaskName scheduled task..." -ForegroundColor Cyan

    if (-not (Test-Path $BatchFile)) {
        Write-Error "Batch file not found at $BatchFile"
        return
    }

    # Check if task already exists
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warning "Task $TaskName already exists. Remove it first with: -Action remove"
        return
    }

    # Create action - run batch file
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatchFile`"" -WorkingDirectory $RepoRoot

    # Create trigger - run at startup
    $trigger = New-ScheduledTaskTrigger -AtStartup

    # Create settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -RestartCount 999 `
        -ExecutionTimeLimit (New-TimeSpan -Days 0)  # No limit

    # Create principal (run as current user with highest privileges)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest

    # Register task
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Catalyst Trading Bot - Automated catalyst detection system"

    Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null

    Write-Host "`n✅ Task installed successfully!" -ForegroundColor Green
    Write-Host "   Task name: $TaskName" -ForegroundColor Gray
    Write-Host "   Will run at: System startup" -ForegroundColor Gray
    Write-Host "   Auto-restart: Every 1 minute on failure" -ForegroundColor Gray
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "  1. Start task now: .\install-task.ps1 -Action start" -ForegroundColor Gray
    Write-Host "  2. Check status: .\install-task.ps1 -Action status" -ForegroundColor Gray
    Write-Host "  3. Or restart your computer to start automatically" -ForegroundColor Gray
}

function Start-TaskWrapper {
    Write-Host "Starting $TaskName task..." -ForegroundColor Cyan

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Error "Task $TaskName not found. Install it first with: -Action install"
        return
    }

    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
    Get-TaskStatus
}

function Stop-TaskWrapper {
    Write-Host "Stopping $TaskName task..." -ForegroundColor Cyan

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Error "Task $TaskName not found."
        return
    }

    Stop-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
    Get-TaskStatus
}

function Remove-TaskWrapper {
    Write-Host "Removing $TaskName task..." -ForegroundColor Cyan

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Warning "Task $TaskName not found."
        return
    }

    # Stop task first if running
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false

    Write-Host "✅ Task removed successfully!" -ForegroundColor Green
}

function Get-TaskStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if (-not $task) {
        Write-Host "`n❌ Task '$TaskName' not installed" -ForegroundColor Red
        Write-Host "   Install with: .\install-task.ps1 -Action install" -ForegroundColor Gray
        return
    }

    Write-Host "`n📊 Task Status:" -ForegroundColor Cyan
    Write-Host "   Name: $($task.TaskName)" -ForegroundColor Gray
    Write-Host "   Description: $($task.Description)" -ForegroundColor Gray

    $stateColor = switch ($task.State) {
        "Running" { "Green" }
        "Ready" { "Yellow" }
        "Disabled" { "Red" }
        default { "Gray" }
    }
    Write-Host "   State: $($task.State)" -ForegroundColor $stateColor

    # Get task info
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "   Last Run: $($info.LastRunTime)" -ForegroundColor Gray
    Write-Host "   Next Run: $($info.NextRunTime)" -ForegroundColor Gray

    $resultColor = if ($info.LastTaskResult -eq 0) { "Green" } else { "Red" }
    Write-Host "   Last Result: $($info.LastTaskResult)" -ForegroundColor $resultColor

    # Check if batch file exists
    if (Test-Path $BatchFile) {
        Write-Host "`n✅ Batch file found: $BatchFile" -ForegroundColor Green
    } else {
        Write-Host "`n❌ Batch file missing: $BatchFile" -ForegroundColor Red
    }
}

# Main execution
if (-not (Test-Admin)) {
    Write-Error "This script requires Administrator privileges. Run PowerShell as Administrator."
    exit 1
}

switch ($Action) {
    "install" { Install-Task }
    "start" { Start-TaskWrapper }
    "stop" { Stop-TaskWrapper }
    "remove" { Remove-TaskWrapper }
    "status" { Get-TaskStatus }
}
