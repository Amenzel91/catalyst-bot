@echo off
REM ============================================================
REM Test Ollama Connection
REM ============================================================

echo.
echo Testing Ollama server...
echo.

curl -s http://localhost:11434 2>nul
if errorlevel 1 (
    echo [FAIL] Ollama is NOT running on port 11434
    echo.
    echo Start it with: start_ollama.bat
    echo.
) else (
    echo.
    echo [OK] Ollama is running and accessible!
    echo.
)

pause
