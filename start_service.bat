@echo off
REM Catalyst-Bot Service Starter
REM This batch file starts the bot in loop mode with auto-restart
REM Suitable for Task Scheduler or manual startup

cd /d "%~dp0"

:START
echo [%date% %time%] Starting Catalyst Bot...
.venv\Scripts\python.exe -m catalyst_bot.runner --loop

REM If the bot exits, wait 60 seconds and restart
echo [%date% %time%] Bot stopped. Restarting in 60 seconds...
timeout /t 60 /nobreak

goto START
