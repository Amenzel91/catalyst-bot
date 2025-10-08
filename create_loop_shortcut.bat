@echo off
echo Creating "Catalyst Bot - Loop Only" shortcut...
echo.

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Desktop = [Environment]::GetFolderPath('Desktop'); $Shortcut = $WshShell.CreateShortcut(\"$Desktop\Catalyst Bot - Loop Only.lnk\"); $Shortcut.TargetPath = '%~dp0start_bot_loop.bat'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.Description = 'Run main bot in continuous loop'; $Shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,238'; $Shortcut.Save()"

if %errorlevel% == 0 (
    echo SUCCESS - Shortcut created on Desktop!
) else (
    echo FAILED - Error creating shortcut
)

echo.
pause
