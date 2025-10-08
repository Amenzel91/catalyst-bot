@echo off
echo ============================================
echo Catalyst-Bot Health Check
echo ============================================
echo.

echo [1] Ollama/LLM Status:
curl -s http://localhost:11434/api/tags | findstr "mistral" >nul && (
    echo    [OK] Ollama running with mistral:latest
) || (
    echo    [FAIL] Ollama not responding
)
echo.

echo [2] Interaction Server Status:
curl -s http://localhost:8081/health | findstr "healthy" >nul && (
    echo    [OK] Interaction server healthy
) || (
    echo    [FAIL] Interaction server not responding
)
echo.

echo [3] Cloudflare Tunnel Status:
tasklist | findstr cloudflare >nul && (
    echo    [OK] Cloudflare tunnel running
) || (
    echo    [FAIL] Cloudflare tunnel not running
)
echo.

echo [4] Bot Process Status:
tasklist | findstr "python" >nul && (
    echo    [OK] Python processes running
    tasklist | findstr "python"
) || (
    echo    [FAIL] No Python processes found
)
echo.

echo [5] GPU Status (AMD):
echo    Checking for AMD GPU...
where rocm-smi >nul 2>&1 && (
    rocm-smi --showuse 2>nul | findstr "GPU" >nul && echo    [OK] AMD GPU detected || echo    [WARN] rocm-smi found but no GPU data
) || (
    echo    [INFO] rocm-smi not installed - using basic GPU check
    wmic path win32_VideoController get Name | findstr "AMD\|Radeon" >nul && echo    [OK] AMD GPU detected || echo    [WARN] No AMD GPU found
)
echo.

echo ============================================
echo Health Check Complete
echo ============================================
