@echo off
REM Catalyst-Bot Windows Service Installation Script
REM This script installs the bot as a Windows service using NSSM (Non-Sucking Service Manager)

echo ====================================
echo Catalyst-Bot Service Installer
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

REM Check if NSSM is installed
echo [1/5] Checking for NSSM...
where nssm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo NSSM not found. Installing via Chocolatey...
    where choco >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Chocolatey is not installed.
        echo.
        echo Please install Chocolatey first:
        echo https://chocolatey.org/install
        echo.
        echo Or manually download NSSM from:
        echo https://nssm.cc/download
        echo Extract nssm.exe to C:\Windows\System32
        pause
        exit /b 1
    )
    choco install nssm -y
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to install NSSM via Chocolatey
        pause
        exit /b 1
    )
)
echo NSSM found!

REM Set paths
echo.
echo [2/5] Configuring paths...
set BOT_DIR=%~dp0
set PYTHON_EXE=%BOT_DIR%.venv\Scripts\python.exe
set BOT_MODULE=catalyst_bot.runner

REM Verify Python environment exists
if not exist "%PYTHON_EXE%" (
    echo ERROR: Python virtual environment not found at:
    echo %PYTHON_EXE%
    echo.
    echo Please create a virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)
echo Python environment found: %PYTHON_EXE%

REM Verify .env exists
if not exist "%BOT_DIR%.env" (
    echo WARNING: .env file not found!
    echo The service may fail to start without proper configuration.
    echo.
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

REM Check if service already exists
echo.
echo [3/5] Checking for existing service...
nssm status CatalystBot >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Service 'CatalystBot' already exists!
    set /p REINSTALL="Do you want to reinstall? (y/n): "
    if /i "%REINSTALL%"=="y" (
        echo Removing existing service...
        nssm stop CatalystBot
        timeout /t 2 /nobreak >nul
        nssm remove CatalystBot confirm
    ) else (
        echo Installation cancelled.
        pause
        exit /b 0
    )
)

REM Install the service
echo.
echo [4/5] Installing CatalystBot service...
nssm install CatalystBot "%PYTHON_EXE%" -m "%BOT_MODULE%" --loop
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install service
    pause
    exit /b 1
)

REM Configure service parameters
echo Configuring service parameters...

REM Set working directory
nssm set CatalystBot AppDirectory "%BOT_DIR%"

REM Set auto-restart on failure
nssm set CatalystBot AppExit Default Restart

REM Set startup mode to automatic
nssm set CatalystBot Start SERVICE_AUTO_START

REM Configure logging
nssm set CatalystBot AppStdout "%BOT_DIR%data\logs\service_stdout.log"
nssm set CatalystBot AppStderr "%BOT_DIR%data\logs\service_stderr.log"

REM Rotate logs
nssm set CatalystBot AppStdoutCreationDisposition 4
nssm set CatalystBot AppStderrCreationDisposition 4

REM Set display name and description
nssm set CatalystBot DisplayName "Catalyst Trading Bot"
nssm set CatalystBot Description "Real-time penny stock catalyst alert bot for Discord"

REM Set restart throttle (restart after 60 seconds if crash)
nssm set CatalystBot AppThrottle 60000

REM Set restart delay (wait 10 seconds before restart)
nssm set CatalystBot AppRestartDelay 10000

echo Service configured successfully!

REM Create logs directory if it doesn't exist
if not exist "%BOT_DIR%data\logs" (
    mkdir "%BOT_DIR%data\logs"
)

echo.
echo [5/5] Installation complete!
echo.
echo ====================================
echo Service Name: CatalystBot
echo Display Name: Catalyst Trading Bot
echo Status: Installed (not started)
echo ====================================
echo.
echo To start the service, run:
echo   net start CatalystBot
echo.
echo Or use the provided batch files:
echo   start_service.bat    - Start the service
echo   restart_service.bat  - Restart the service
echo   uninstall_service.bat - Remove the service
echo.
echo Logs will be written to:
echo   %BOT_DIR%data\logs\service_stdout.log
echo   %BOT_DIR%data\logs\service_stderr.log
echo   %BOT_DIR%data\logs\bot.jsonl
echo.

set /p START_NOW="Do you want to start the service now? (y/n): "
if /i "%START_NOW%"=="y" (
    echo.
    echo Starting service...
    net start CatalystBot
    echo.
    echo Service started! Check status with: nssm status CatalystBot
)

echo.
pause
