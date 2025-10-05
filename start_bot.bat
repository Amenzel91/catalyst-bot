@echo off
cd /d "C:\Users\menza\OneDrive\Desktop\Catalyst-Bot\catalyst-bot"
call .venv\Scripts\activate.bat
python -m catalyst_bot.runner --loop
