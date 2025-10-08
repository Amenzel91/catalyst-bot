@echo off
REM ============================================================
REM Discord Interaction Server (Flask)
REM ============================================================
REM
REM Starts the Flask server that handles Discord button clicks.
REM Must be running for Discord interactions to work.
REM Runs on http://localhost:8081
REM ============================================================

cd /d "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"

echo.
echo ============================================================
echo  Starting Discord Interaction Server
echo ============================================================
echo.

REM Check virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if Flask is installed
python -c "import flask" 2>nul
if errorlevel 1 (
    echo [*] Installing Flask...
    pip install flask
)

echo [*] Starting interaction server on port 8081...
echo.

python interaction_server.py

echo.
echo [*] Interaction server stopped.
pause
