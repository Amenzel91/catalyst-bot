# ============================================================
# Catalyst Bot - Automatic Desktop Shortcut Creator
# ============================================================
#
# This script creates desktop shortcuts for easy bot launching.
# Run this ONCE to set up your shortcuts.
#
# Usage:
#   1. Right-click this file
#   2. Select "Run with PowerShell"
#   3. Shortcuts will appear on your Desktop
#
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Catalyst Bot - Creating Desktop Shortcuts" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Get current directory and Desktop path
$BotDir = $PSScriptRoot
$Desktop = [System.Environment]::GetFolderPath('Desktop')

Write-Host "[*] Bot directory: $BotDir" -ForegroundColor Gray
Write-Host "[*] Desktop path: $Desktop" -ForegroundColor Gray
Write-Host ""

# Create WScript Shell object
$WshShell = New-Object -ComObject WScript.Shell

# ============================================================
# Shortcut 1: Start All (MAIN LAUNCHER)
# ============================================================
Write-Host "[1/4] Creating 'Catalyst Bot - Start All' shortcut..." -ForegroundColor Yellow

$Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Start All.lnk")
$Shortcut.TargetPath = "$BotDir\start_all.bat"
$Shortcut.WorkingDirectory = "$BotDir"
$Shortcut.Description = "Start all Catalyst-Bot services (Ollama, QuickChart, Tunnel, Interaction Server, Main Bot)"
$Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,137"  # Rocket icon
$Shortcut.Save()

Write-Host "      ✓ Created: Catalyst Bot - Start All.lnk" -ForegroundColor Green

# ============================================================
# Shortcut 2: Discord URL (Tunnel Only)
# ============================================================
Write-Host "[2/4] Creating 'Catalyst Bot - Discord URL' shortcut..." -ForegroundColor Yellow

$Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Discord URL.lnk")
$Shortcut.TargetPath = "$BotDir\start_tunnel.bat"
$Shortcut.WorkingDirectory = "$BotDir"
$Shortcut.Description = "Get Discord Interaction Endpoint URL (Cloudflare Tunnel)"
$Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,14"  # Network icon
$Shortcut.Save()

Write-Host "      ✓ Created: Catalyst Bot - Discord URL.lnk" -ForegroundColor Green

# ============================================================
# Shortcut 3: Test Mode (Single Cycle)
# ============================================================
Write-Host "[3/4] Creating 'Catalyst Bot - Test Once' shortcut..." -ForegroundColor Yellow

$Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Test Once.lnk")
$Shortcut.TargetPath = "$BotDir\start_bot_once.bat"
$Shortcut.WorkingDirectory = "$BotDir"
$Shortcut.Description = "Run single bot cycle for testing changes"
$Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,166"  # Test tube icon
$Shortcut.Save()

Write-Host "      ✓ Created: Catalyst Bot - Test Once.lnk" -ForegroundColor Green

# ============================================================
# Shortcut 4: Bot Loop (Main Bot Only)
# ============================================================
Write-Host "[4/4] Creating 'Catalyst Bot - Loop Only' shortcut..." -ForegroundColor Yellow

$Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Loop Only.lnk")
$Shortcut.TargetPath = "$BotDir\start_bot_loop.bat"
$Shortcut.WorkingDirectory = "$BotDir"
$Shortcut.Description = "Run main bot in continuous loop (assumes services already running)"
$Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,238"  # Sync/loop icon
$Shortcut.Save()

Write-Host "      ✓ Created: Catalyst Bot - Loop Only.lnk" -ForegroundColor Green

# ============================================================
# Summary
# ============================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ✅ All Shortcuts Created!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Check your Desktop for these shortcuts:" -ForegroundColor White
Write-Host "  🚀 Catalyst Bot - Start All.lnk" -ForegroundColor White
Write-Host "  🌐 Catalyst Bot - Discord URL.lnk" -ForegroundColor White
Write-Host "  🧪 Catalyst Bot - Test Once.lnk" -ForegroundColor White
Write-Host "  🔄 Catalyst Bot - Loop Only.lnk" -ForegroundColor White
Write-Host ""
Write-Host "Recommended workflow:" -ForegroundColor Yellow
Write-Host "  1. First time: Double-click 'Discord URL' to get your endpoint" -ForegroundColor Yellow
Write-Host "  2. Daily use: Double-click 'Start All' to launch everything" -ForegroundColor Yellow
Write-Host "  3. Testing: Double-click 'Test Once' before deploying changes" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press any key to close..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
