@echo off
REM ============================================================
REM Ollama - LLM Server for Mistral Sentiment
REM ============================================================
REM
REM Starts Ollama server with Mistral model for sentiment
REM classification.
REM ============================================================

echo.
echo ============================================================
echo  Starting Ollama (Mistral LLM)
echo ============================================================
echo.

REM Check if Ollama is installed
where ollama >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Ollama not found!
    echo.
    echo Install it from: https://ollama.ai/download
    echo.
    pause
    exit /b 1
)

REM Check if Ollama is already running
curl -s http://localhost:11434 >nul 2>nul
if not errorlevel 1 (
    echo [OK] Ollama is already running on http://localhost:11434
    echo.
    echo No need to start it again.
    echo.
    pause
    exit /b 0
)

echo [*] Starting Ollama server...
echo [*] Server will run on http://localhost:11434
echo.

REM Start Ollama (stays in foreground)
ollama serve

echo.
echo [*] Ollama stopped.
pause
