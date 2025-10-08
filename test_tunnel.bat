@echo off
REM ============================================================
REM Test Cloudflare Tunnel Manually
REM ============================================================

echo.
echo ============================================================
echo  Testing Cloudflare Tunnel
echo ============================================================
echo.

REM Check if cloudflared exists
where cloudflared >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Cloudflared not found in PATH!
    echo.
    echo Trying chocolatey location...
    if exist "C:\ProgramData\chocolatey\bin\cloudflared.exe" (
        set CLOUDFLARED_EXE=C:\ProgramData\chocolatey\bin\cloudflared.exe
        echo [OK] Found: %CLOUDFLARED_EXE%
    ) else (
        echo [FAIL] Not found. Install it or use cloudflare-tunnel-windows-amd64.exe
        pause
        exit /b 1
    )
) else (
    set CLOUDFLARED_EXE=cloudflared
    echo [OK] Found cloudflared in PATH
)

echo.
echo Starting tunnel to http://localhost:8081...
echo.
echo ============================================================
echo  LOOK FOR THE URL BELOW (starts with https://)
echo ============================================================
echo.

REM Start tunnel (stays in foreground)
%CLOUDFLARED_EXE% tunnel --url http://localhost:8081

echo.
echo Tunnel stopped.
pause
