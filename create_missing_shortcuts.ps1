# ============================================================
# Create Missing Shortcuts (Discord URL + Loop Only)
# ============================================================

Write-Host ""
Write-Host "Creating missing shortcuts..." -ForegroundColor Yellow
Write-Host ""

$BotDir = $PSScriptRoot
$Desktop = [System.Environment]::GetFolderPath('Desktop')
$WshShell = New-Object -ComObject WScript.Shell

# ============================================================
# Shortcut: Discord URL (Tunnel Only)
# ============================================================
Write-Host "[1/2] Creating 'Catalyst Bot - Discord URL' shortcut..." -ForegroundColor Yellow

try {
    $Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Discord URL.lnk")
    $Shortcut.TargetPath = "$BotDir\start_tunnel.bat"
    $Shortcut.WorkingDirectory = "$BotDir"
    $Shortcut.Description = "Get Discord Interaction Endpoint URL (Cloudflare Tunnel)"
    $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,14"
    $Shortcut.Save()
    Write-Host "      ✓ Created successfully" -ForegroundColor Green
} catch {
    Write-Host "      ✗ Failed: $_" -ForegroundColor Red
}

# ============================================================
# Shortcut: Bot Loop (Main Bot Only)
# ============================================================
Write-Host "[2/2] Creating 'Catalyst Bot - Loop Only' shortcut..." -ForegroundColor Yellow

try {
    $Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Loop Only.lnk")
    $Shortcut.TargetPath = "$BotDir\start_bot_loop.bat"
    $Shortcut.WorkingDirectory = "$BotDir"
    $Shortcut.Description = "Run main bot in continuous loop (assumes services already running)"
    $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,238"
    $Shortcut.Save()
    Write-Host "      ✓ Created successfully" -ForegroundColor Green
} catch {
    Write-Host "      ✗ Failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Done! Check your Desktop." -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
