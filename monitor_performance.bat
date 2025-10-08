@echo off
echo ============================================
echo Performance Monitor - CPU/Memory/GPU
echo Press Ctrl+C to stop
echo ============================================
echo.

:loop
echo [%TIME%] Performance Snapshot:
echo.

echo CPU Usage:
wmic cpu get loadpercentage | findstr /r "[0-9]"

echo.
echo Memory Usage:
wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value | findstr "="

echo.
echo Python Processes:
tasklist | findstr "python.exe" | findstr /v "findstr"

echo.
echo GPU (AMD):
wmic path win32_VideoController get Name,AdapterRAM,CurrentRefreshRate 2>nul | findstr "AMD\|Radeon" || echo No AMD GPU data available

echo.
echo ----------------------------------------
echo.
timeout /t 10 /nobreak >nul
goto loop
