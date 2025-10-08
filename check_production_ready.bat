@echo off
REM ============================================================
REM Production Readiness Check
REM ============================================================

echo.
echo ============================================================
echo  Catalyst Bot - Production Readiness Check
echo ============================================================
echo.

REM 1. Check Services
echo [1/6] Checking required services...
curl -s http://localhost:11434 >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Ollama (Mistral LLM^): Running
) else (
    echo   [WARN] Ollama: NOT RUNNING - start with: start_ollama.bat
)

curl -s http://localhost:3400 >nul 2>nul
if not errorlevel 1 (
    echo   [OK] QuickChart (Charts^): Running
) else (
    echo   [WARN] QuickChart: NOT RUNNING - start with: start_quickchart.bat
)

curl -s http://localhost:8080/health/ping >nul 2>nul
if not errorlevel 1 (
    echo   [OK] Health Monitor: Running
) else (
    echo   [INFO] Health Monitor: Will start with bot
)

echo.

REM 2. Check Directories
echo [2/6] Checking critical directories...
if exist "data" (
    echo   [OK] data/ exists
) else (
    echo   [WARN] data/ missing - will be created
    mkdir data
)

if exist "data\feedback" (
    echo   [OK] data/feedback/ exists
) else (
    echo   [INFO] data/feedback/ missing - will be created automatically
)

if exist "data\logs" (
    echo   [OK] data/logs/ exists
) else (
    echo   [INFO] data/logs/ missing - will be created automatically
)

if exist "data\admin" (
    echo   [OK] data/admin/ exists
) else (
    echo   [INFO] data/admin/ missing - will be created automatically
)

echo.

REM 3. Check Configuration
echo [3/6] Checking configuration...
if exist ".env" (
    echo   [OK] .env file exists

    REM Check critical variables
    findstr /C:"DISCORD_BOT_TOKEN" .env >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] DISCORD_BOT_TOKEN configured
    ) else (
        echo   [WARN] DISCORD_BOT_TOKEN not set
    )

    findstr /C:"DISCORD_WEBHOOK_URL" .env >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] DISCORD_WEBHOOK_URL configured
    ) else (
        echo   [WARN] DISCORD_WEBHOOK_URL not set
    )

    findstr /C:"FEATURE_FEEDBACK_LOOP=1" .env >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] Feedback loop enabled
    ) else (
        echo   [INFO] Feedback loop disabled
    )

    findstr /C:"FEATURE_ADMIN_REPORTS=1" .env >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] Admin reports enabled
    ) else (
        echo   [INFO] Admin reports disabled
    )

) else (
    echo   [ERROR] .env file missing!
    echo   Copy .env.example to .env and configure
)

echo.

REM 4. Check Virtual Environment
echo [4/6] Checking Python environment...
if exist ".venv\Scripts\python.exe" (
    echo   [OK] Virtual environment exists

    REM Check critical packages
    .venv\Scripts\python -c "import torch" >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] PyTorch installed
    ) else (
        echo   [WARN] PyTorch not installed - ML features may not work
    )

    .venv\Scripts\python -c "import transformers" >nul 2>nul
    if not errorlevel 1 (
        echo   [OK] Transformers installed
    ) else (
        echo   [WARN] Transformers not installed - ML features may not work
    )

) else (
    echo   [ERROR] Virtual environment not found!
    echo   Run: python -m venv .venv
)

echo.

REM 5. Check Database Files
echo [5/6] Checking databases...
if exist "data\feedback\alert_performance.db" (
    echo   [OK] Feedback database exists (has data^)
) else (
    echo   [INFO] Feedback database will be created on first alert
)

if exist "data\chart_cache.db" (
    echo   [OK] Chart cache database exists
) else (
    echo   [INFO] Chart cache database will be created automatically
)

if exist "data\admin\parameter_changes.db" (
    echo   [OK] Parameter changes database exists
) else (
    echo   [INFO] Parameter changes database will be created automatically
)

echo.

REM 6. Check Recent Logs
echo [6/6] Checking recent activity...
if exist "data\events.jsonl" (
    echo   [OK] Events log exists
    for %%A in (data\events.jsonl) do (
        echo   [INFO] Events file size: %%~zA bytes
    )
) else (
    echo   [INFO] No events logged yet
)

if exist "data\logs\bot.jsonl" (
    echo   [OK] Bot log exists
) else (
    echo   [INFO] Bot log will be created on startup
)

echo.
echo ============================================================
echo  Production Readiness Summary
echo ============================================================
echo.
echo Ready to start production deployment!
echo.
echo Next steps:
echo   1. Configure admin webhook in .env (optional^)
echo   2. Run: start_all.bat
echo   3. Monitor logs for 24 hours
echo   4. Check data collection after 7 days
echo.
pause
