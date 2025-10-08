@echo off
REM Catalyst-Bot Watchdog Runner
REM This script continuously monitors the bot and restarts it if needed

echo ====================================
echo Catalyst-Bot Watchdog
echo ====================================
echo.

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found
    echo Using system Python
)

echo Starting watchdog monitor...
echo Press Ctrl+C to stop
echo.

:loop
python -m catalyst_bot.watchdog
echo.
echo Watchdog stopped. Restarting in 10 seconds...
echo Press Ctrl+C to cancel
timeout /t 10
goto loop
