@echo off
REM Catalyst-Bot Service Restart Script

echo ====================================
echo Restarting Catalyst-Bot Service
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
    echo ERROR: Service 'CatalystBot' not found.
    echo Please install the service first using: install_service.bat
    pause
    exit /b 1
)

echo Stopping CatalystBot...
net stop CatalystBot

echo Waiting for graceful shutdown...
timeout /t 3 /nobreak

echo Starting CatalystBot...
net start CatalystBot

echo.
if %ERRORLEVEL% EQU 0 (
    echo ====================================
    echo Service restarted successfully!
    echo ====================================
) else (
    echo ====================================
    echo ERROR: Service failed to start
    echo ====================================
    echo.
    echo Check logs for details:
    echo   data\logs\service_stderr.log
    echo   data\logs\bot.jsonl
)

echo.
pause
