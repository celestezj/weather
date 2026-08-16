@echo off
chcp 65001 >nul
set PYTHONUTF8=1
powershell -ExecutionPolicy Bypass -File run.ps1
echo.
echo Script finished
pause