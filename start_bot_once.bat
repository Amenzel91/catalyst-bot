@echo off
REM ============================================================
REM Catalyst Bot - Single Cycle Test
REM ============================================================
REM
REM Runs the bot ONCE for testing purposes.
REM Use this to verify everything works before starting the
REM full production loop.
REM ============================================================

cd /d "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"

echo.
echo ============================================================
echo  Catalyst Bot - Single Cycle Test
echo ============================================================
echo.

REM Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv .venv
    echo.
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Running single cycle test...
echo.

python -m catalyst_bot.runner --once

echo.
echo ============================================================
echo  Test Complete!
echo ============================================================
echo.
pause
