@echo off
chcp 65001 >nul
set PYTHONUTF8=1
powershell -ExecutionPolicy Bypass -File install.ps1
if errorlevel 1 (
    echo.
    echo [ERROR] Install failed. See messages above.
    pause
    exit /b 1
)
echo.
echo Script finished
pause
