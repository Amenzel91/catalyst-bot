@echo off
REM Verify pre-market coverage settings

echo.
echo ============================================================
echo  Pre-Market Coverage Verification
echo ============================================================
echo.

REM Check if bot is running
echo [1/4] Checking if bot is running...
tasklist | findstr python >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Bot is running
) else (
    echo   [ERROR] Bot is NOT running - start it before pre-market!
    pause
    exit /b 1
)

echo.

REM Check recent logs for market hours detection
echo [2/4] Checking market hours detection...
powershell "Get-Content data\logs\bot.jsonl -Tail 100 | Select-String 'market_status' | Select-Object -First 5"

echo.

REM Check cycle intervals in logs
echo [3/4] Checking cycle intervals...
powershell "Get-Content data\logs\bot.jsonl -Tail 50 | Select-String 'cycle_complete' | Select-Object -First 5"

echo.

REM Show active feeds
echo [4/4] Checking active feeds...
powershell "Get-Content data\logs\bot.jsonl -Tail 100 | Select-String 'feeds_summary' | Select-Object -First 3"

echo.
echo ============================================================
echo  Recommendations:
echo ============================================================
echo.
echo If market_status shows "closed" during 4am-9:30am ET:
echo   - Check timezone settings (should be America/New_York)
echo   - Verify market hours detection in runner.py
echo.
echo If no feeds during pre-market:
echo   - Ensure SKIP_SOURCES does NOT include Finnhub News
echo   - Check feed fetch logs for errors
echo.
pause
