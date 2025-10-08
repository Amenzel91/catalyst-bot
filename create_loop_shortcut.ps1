# Create Loop Only Shortcut

$BotDir = $PSScriptRoot
$Desktop = [System.Environment]::GetFolderPath('Desktop')
$WshShell = New-Object -ComObject WScript.Shell

Write-Host "Creating 'Catalyst Bot - Loop Only' shortcut..." -ForegroundColor Yellow

try {
    $Shortcut = $WshShell.CreateShortcut("$Desktop\Catalyst Bot - Loop Only.lnk")
    $Shortcut.TargetPath = "$BotDir\start_bot_loop.bat"
    $Shortcut.WorkingDirectory = "$BotDir"
    $Shortcut.Description = "Run main bot in continuous loop"
    $Shortcut.IconLocation = "C:\Windows\System32\shell32.dll,238"
    $Shortcut.Save()
    Write-Host "✓ Created successfully!" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
