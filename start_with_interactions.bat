@echo off
REM ============================================================
REM Catalyst Bot Startup Script with Cloudflare Tunnel
REM ============================================================
REM
REM This script starts all required components:
REM 1. Cloudflare Tunnel (exposes interaction server)
REM 2. Interaction Server (handles Discord buttons)
REM 3. Catalyst Bot (main bot)
REM
REM Press Ctrl+C to stop all components
REM ============================================================

echo.
echo ============================================================
echo  Catalyst Bot - Starting All Components
echo ============================================================
echo.

REM Check if Flask is installed
.venv\Scripts\python -c "import flask" 2>nul
if errorlevel 1 (
    echo [ERROR] Flask not found. Installing...
    .venv\Scripts\pip install flask
)

REM Check if cloudflared is installed
where cloudflared >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Cloudflared not found!
    echo Please install it first:
    echo   1. Download from: https://github.com/cloudflare/cloudflared/releases
    echo   2. Or use: choco install cloudflared
    echo.
    pause
    exit /b 1
)

echo [*] Starting Cloudflare Tunnel...
echo [*] This will give you a public URL for Discord interactions
echo.

REM Start cloudflared in background
start "Cloudflare Tunnel" cloudflared tunnel --url http://localhost:8081

REM Wait for tunnel to start
timeout /t 3 /nobreak >nul

echo.
echo ============================================================
echo  IMPORTANT: Copy the trycloudflare.com URL above
echo  and set it as your Discord Interaction Endpoint URL
echo ============================================================
echo.
pause

REM Start interaction server in background
echo [*] Starting Interaction Server...
start "Interaction Server" .venv\Scripts\python interaction_server.py

REM Wait for server to start
timeout /t 3 /nobreak >nul

echo.
echo [*] Starting Catalyst Bot...
echo.

REM Start main bot (foreground)
.venv\Scripts\python -m catalyst_bot.runner

REM When bot stops, cleanup
echo.
echo [*] Shutting down all components...
taskkill /FI "WindowTitle eq Cloudflare Tunnel*" /T /F >nul 2>nul
taskkill /FI "WindowTitle eq Interaction Server*" /T /F >nul 2>nul

echo [*] Cleanup complete
pause
