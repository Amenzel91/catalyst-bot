@echo off
REM Catalyst-Bot Windows Service Uninstallation Script

echo ====================================
echo Catalyst-Bot Service Uninstaller
echo ====================================
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: This script requires administrator privileges.
    echo Please run this script as Administrator.
    pause
    exit /b 1
)

REM Check if service exists
nssm status CatalystBot >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Service 'CatalystBot' not found.
    echo Nothing to uninstall.
    pause
    exit /b 0
)

echo Service found. This will:
echo  - Stop the CatalystBot service
echo  - Remove the service from Windows
echo  - NOT delete any data or logs
echo.

set /p CONFIRM="Are you sure you want to uninstall? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Uninstallation cancelled.
    pause
    exit /b 0
)

echo.
echo Stopping CatalystBot service...
nssm stop CatalystBot
timeout /t 3 /nobreak >nul

echo Removing CatalystBot service...
nssm remove CatalystBot confirm

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================
    echo Service removed successfully!
    echo ====================================
    echo.
    echo Your data and logs are still intact in:
    echo   data\logs\
    echo.
    echo To reinstall, run: install_service.bat
) else (
    echo.
    echo ERROR: Failed to remove service
    echo Please check nssm status and try manually:
    echo   nssm remove CatalystBot confirm
)

echo.
pause
