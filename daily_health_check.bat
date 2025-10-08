@echo off
REM Daily Health Check - Run this anytime to see bot performance
echo.
echo ============================================================
echo  Catalyst Bot - Daily Health Report
echo ============================================================
echo.

REM Check if bot is running
echo [1/5] Bot Status...
tasklist | findstr python >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Bot is running
) else (
    echo   [ERROR] Bot is NOT running!
    pause
    exit /b 1
)

echo.

REM Count alerts today
echo [2/5] Alerts Posted Today...
powershell "Get-Content data\logs\bot.jsonl | Select-String 'alert_posted' | Measure-Object | Select-Object -ExpandProperty Count"

echo.

REM Check for errors
echo [3/5] Recent Errors (last 10)...
powershell "Get-Content data\logs\bot.jsonl -Tail 500 | Select-String 'ERROR' -Context 0,1 | Select-Object -First 10"

echo.

REM Check feedback database
echo [4/5] Feedback Tracking...
sqlite3 data/feedback/alert_performance.db "SELECT COUNT(*) as 'Total Alerts Tracked:', SUM(CASE WHEN price_1h IS NOT NULL THEN 1 ELSE 0 END) as '1h Updates:', SUM(CASE WHEN price_4h IS NOT NULL THEN 1 ELSE 0 END) as '4h Updates:', SUM(CASE WHEN price_1d IS NOT NULL THEN 1 ELSE 0 END) as '1d Updates:' FROM alert_performance"

echo.

REM Check average cycle time
echo [5/5] Performance Metrics...
powershell "Get-Content data\logs\bot.jsonl -Tail 100 | Select-String 'CYCLE_DONE' | Measure-Object | Select-Object -ExpandProperty Count" | set /p cycles=
echo   Recent cycles completed: %cycles%

echo.
echo ============================================================
echo  Summary Complete
echo ============================================================
echo.
echo Run this script anytime to check bot health!
echo.
pause
