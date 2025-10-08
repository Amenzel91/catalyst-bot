@echo off
REM ============================================================
REM Catalyst Bot - Complete Production Startup
REM ============================================================
REM
REM This script starts ALL components in separate windows:
REM 1. Ollama (Mistral LLM)
REM 2. QuickChart (Docker)
REM 3. Cloudflare Tunnel
REM 4. Interaction Server (Flask)
REM 5. Main Bot (production loop)
REM
REM Each component opens in its own window for easy monitoring.
REM ============================================================

cd /d "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"

echo.
echo ============================================================
echo  Catalyst Bot - Starting All Services
echo ============================================================
echo.

REM 1. Start Ollama (check if already running first)
echo [1/5] Checking Ollama (Mistral LLM)...
curl -s http://localhost:11434 >nul 2>nul
if errorlevel 1 (
    echo [*] Starting Ollama server...
    start "Ollama - Mistral LLM" cmd /k start_ollama.bat
    timeout /t 3 /nobreak >nul
) else (
    echo [OK] Ollama already running, skipping
)

REM 2. Start QuickChart (if Docker is available)
echo [2/5] Starting QuickChart (Docker)...
docker --version >nul 2>nul
if not errorlevel 1 (
    start "QuickChart - Docker" cmd /k start_quickchart.bat
    timeout /t 3 /nobreak >nul
) else (
    echo [SKIP] Docker not found, QuickChart disabled
)

REM 3. Start Cloudflare Tunnel
echo [3/5] Starting Cloudflare Tunnel...
echo.
echo ============================================================
echo  ACTION REQUIRED:
echo
echo  A new window will open with your Discord Interaction URL.
echo
echo  1. Wait for the URL to appear (looks like: https://XXXX.trycloudflare.com)
echo  2. Copy the URL
echo  3. Go to Discord Developer Portal
echo  4. Paste it in: Your App ^> General Info ^> Interactions Endpoint URL
echo  5. Return here and press any key to continue
echo ============================================================
echo.
pause

start "Cloudflare Tunnel - Discord Endpoint" cmd /k start_tunnel.bat
timeout /t 5 /nobreak >nul

echo.
echo [*] Make sure you copied the Cloudflare URL before continuing!
pause

REM 4. Start Interaction Server
echo [4/5] Starting Discord Interaction Server...
start "Discord Interaction Server" cmd /k start_interaction_server.bat
timeout /t 3 /nobreak >nul

REM 5. Start Main Bot
echo [5/5] Starting Catalyst Bot (main loop)...
echo.
echo ============================================================
echo  All Services Started!
echo ============================================================
echo.
echo Running services:
echo   - Ollama:            http://localhost:11434
echo   - QuickChart:        http://localhost:3400
echo   - Interaction Server: http://localhost:8081
echo   - Cloudflare Tunnel: (see tunnel window)
echo   - Main Bot:          (starting now...)
echo.
echo Press Ctrl+C to stop the bot. Other services will keep running.
echo.
pause

REM Start bot in THIS window (foreground)
call .venv\Scripts\activate.bat
python -m catalyst_bot.runner

REM When bot stops
echo.
echo ============================================================
echo  Bot Stopped
echo ============================================================
echo.
echo Other services are still running in separate windows.
echo Close their windows manually to stop them, or run:
echo   taskkill /FI "WindowTitle eq Ollama*" /F
echo   taskkill /FI "WindowTitle eq QuickChart*" /F
echo   taskkill /FI "WindowTitle eq Cloudflare*" /F
echo   taskkill /FI "WindowTitle eq Discord*" /F
echo.
pause
