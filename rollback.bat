@echo off
REM Catalyst-Bot Rollback Script
REM This script helps you rollback to a previous version safely

echo ====================================
echo Catalyst-Bot Rollback Utility
echo ====================================
echo.

REM Check for administrator privileges (if using service)
net session >nul 2>&1
set ADMIN=%ERRORLEVEL%

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found
    echo Please ensure .venv exists before rolling back
    pause
    exit /b 1
)

echo Available rollback options:
echo.
echo 1. Rollback to a git tag (e.g., v1.2.3)
echo 2. Rollback to a specific commit hash
echo 3. Show recent tags
echo 4. Show current deployment info
echo 5. Cancel
echo.

set /p CHOICE="Enter your choice (1-5): "

if "%CHOICE%"=="1" goto rollback_tag
if "%CHOICE%"=="2" goto rollback_commit
if "%CHOICE%"=="3" goto list_tags
if "%CHOICE%"=="4" goto show_info
if "%CHOICE%"=="5" goto cancel
echo Invalid choice
goto cancel

:list_tags
echo.
echo Recent deployment tags:
echo.
python -m catalyst_bot.deployment list-tags
echo.
pause
goto :eof

:show_info
echo.
echo Current deployment information:
echo.
python -m catalyst_bot.deployment info
echo.
pause
goto :eof

:rollback_tag
echo.
echo Listing recent tags...
python -m catalyst_bot.deployment list-tags
echo.
set /p TAG="Enter tag name to rollback to (or 'cancel'): "

if /i "%TAG%"=="cancel" goto cancel

echo.
echo ====================================
echo ROLLBACK CONFIRMATION
echo ====================================
echo.
echo This will:
echo   1. Stop the bot (if running as service)
echo   2. Checkout git tag: %TAG%
echo   3. Restore .env.backup (if exists)
echo   4. Restart the bot
echo.
echo WARNING: Make sure you have a recent backup!
echo.
set /p CONFIRM="Are you sure you want to rollback? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
    echo Rollback cancelled
    goto cancel
)

echo.
echo [1/4] Stopping bot...
if %ADMIN% EQU 0 (
    net stop CatalystBot >nul 2>&1
    echo Service stopped
) else (
    echo Manual stop required: Press Ctrl+C in the bot terminal
    echo Press any key when bot is stopped...
    pause >nul
)

echo.
echo [2/4] Rolling back to tag %TAG%...
python -m catalyst_bot.deployment rollback %TAG%
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Rollback failed!
    echo Check the error message above
    pause
    exit /b 1
)

echo.
echo [3/4] Reinstalling dependencies...
pip install -q -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Some dependencies may have failed to install
    echo You may need to run: pip install -r requirements.txt
)

echo.
echo [4/4] Restarting bot...
if %ADMIN% EQU 0 (
    net start CatalystBot
    if %ERRORLEVEL% EQU 0 (
        echo Service started successfully
    ) else (
        echo ERROR: Service failed to start
        echo Check logs: data\logs\service_stderr.log
    )
) else (
    echo Manual restart required
    echo Run: start_bot.bat or start_service.bat
)

echo.
echo ====================================
echo Rollback complete!
echo ====================================
echo.
echo Rolled back to: %TAG%
echo Config restored: .env.backup
echo.
echo IMPORTANT: Verify bot is healthy:
echo   curl http://localhost:8080/health/ping
echo   Check logs: data\logs\bot.jsonl
echo.
pause
goto :eof

:rollback_commit
echo.
set /p COMMIT="Enter commit hash to rollback to (or 'cancel'): "

if /i "%COMMIT%"=="cancel" goto cancel

echo.
echo ====================================
echo ROLLBACK CONFIRMATION
echo ====================================
echo.
echo This will:
echo   1. Stop the bot (if running as service)
echo   2. Checkout commit: %COMMIT%
echo   3. Restore .env.backup (if exists)
echo   4. Restart the bot
echo.
echo WARNING: Make sure you have a recent backup!
echo.
set /p CONFIRM="Are you sure you want to rollback? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
    echo Rollback cancelled
    goto cancel
)

echo.
echo [1/4] Stopping bot...
if %ADMIN% EQU 0 (
    net stop CatalystBot >nul 2>&1
    echo Service stopped
) else (
    echo Manual stop required: Press Ctrl+C in the bot terminal
    echo Press any key when bot is stopped...
    pause >nul
)

echo.
echo [2/4] Rolling back to commit %COMMIT%...
python -m catalyst_bot.deployment rollback %COMMIT%
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Rollback failed!
    echo Check the error message above
    pause
    exit /b 1
)

echo.
echo [3/4] Reinstalling dependencies...
pip install -q -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Some dependencies may have failed to install
    echo You may need to run: pip install -r requirements.txt
)

echo.
echo [4/4] Restarting bot...
if %ADMIN% EQU 0 (
    net start CatalystBot
    if %ERRORLEVEL% EQU 0 (
        echo Service started successfully
    ) else (
        echo ERROR: Service failed to start
        echo Check logs: data\logs\service_stderr.log
    )
) else (
    echo Manual restart required
    echo Run: start_bot.bat or start_service.bat
)

echo.
echo ====================================
echo Rollback complete!
echo ====================================
echo.
echo Rolled back to: %COMMIT%
echo Config restored: .env.backup
echo.
echo IMPORTANT: Verify bot is healthy:
echo   curl http://localhost:8080/health/ping
echo   Check logs: data\logs\bot.jsonl
echo.
pause
goto :eof

:cancel
echo.
echo Rollback cancelled
echo.
pause
exit /b 0
