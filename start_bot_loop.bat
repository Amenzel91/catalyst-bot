@echo off
REM ============================================================
REM Catalyst Bot - Continuous Production Loop
REM ============================================================
REM
REM Runs the bot in continuous loop mode for production use.
REM Press Ctrl+C to stop gracefully.
REM ============================================================

cd /d "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"

echo.
echo ============================================================
echo  Catalyst Bot - Production Mode
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

echo [*] Starting bot in continuous loop...
echo [*] Press Ctrl+C to stop gracefully
echo.

python -m catalyst_bot.runner

echo.
echo [*] Bot stopped.
pause
