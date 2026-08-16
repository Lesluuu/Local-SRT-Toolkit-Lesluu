@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit - Translate

echo.
echo ======================================================================
echo  Local-SRT-Toolkit :: Subtitle Translation to Chinese (NLLB-200)
echo ======================================================================
echo  NOTE: Hobby project, accuracy is limited.
echo.

set "VENV_PY=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ERROR: venv not found!
    echo Please run 0_RUN_FIRST.bat first to install dependencies.
    echo.
    pause
    goto :EOF
)

"%VENV_PY%" "%~dp0translate.py"

echo.
echo ======================================================================
echo  Done. Run 0_RUN_FIRST.bat to go back to main menu.
echo ======================================================================
pause
