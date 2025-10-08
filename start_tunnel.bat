@echo off
REM ============================================================
REM Cloudflare Tunnel - Discord Interaction Endpoint
REM ============================================================
REM
REM This script starts ONLY the Cloudflare tunnel and displays
REM the public URL you need to copy into Discord.
REM
REM The URL will be shown in CYAN and remain on screen.
REM ============================================================

echo.
echo ============================================================
echo  Starting Cloudflare Tunnel for Discord Interactions
echo ============================================================
echo.

REM Check if cloudflared exists
where cloudflared >nul 2>nul
if errorlevel 1 (
    if exist cloudflare-tunnel-windows-amd64.exe (
        echo [OK] Using local cloudflare-tunnel-windows-amd64.exe
        set CLOUDFLARED_EXE=cloudflare-tunnel-windows-amd64.exe
    ) else (
        echo [ERROR] Cloudflared not found!
        echo.
        echo Download it using this command:
        echo   curl -L -o cloudflare-tunnel-windows-amd64.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
        echo.
        pause
        exit /b 1
    )
) else (
    set CLOUDFLARED_EXE=cloudflared
)

echo [*] Starting tunnel on http://localhost:8081...
echo.
echo ============================================================
echo  COPY THE URL BELOW AND PASTE IT INTO DISCORD:
echo
echo  Discord Developer Portal ^> Your App ^> General Information
echo  ^> Interactions Endpoint URL
echo.
echo  The URL will look like: https://XXXXX.trycloudflare.com
echo ============================================================
echo.

REM Start tunnel (stays in foreground so URL is visible)
%CLOUDFLARED_EXE% tunnel --url http://localhost:8081

REM If tunnel stops
echo.
echo [*] Tunnel stopped.
pause
