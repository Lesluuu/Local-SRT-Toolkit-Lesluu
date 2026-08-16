@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit - Install

echo.
echo ========================================================================
echo  Local-SRT-Toolkit :: Install Dependencies
echo  (Creates venv + installs all pip packages from Chinese mirrors)
echo ======================================================================
echo.

set "PYCMD="
where py >nul 2>nul   && set "PYCMD=py -3"
if "%PYCMD%"=="" where python >nul 2>nul && set "PYCMD=python"
if "%PYCMD%"=="" (
    echo ERROR: Python not found!
    echo Please install Python 3.10/3.11/3.12: https://www.python.org/downloads/
    echo Check "Add Python to PATH" during installation!
    pause
    goto :EOF
)
echo [1/4] Python: 
%PYCMD% --version
echo.

REM --- Create venv ---
if exist "%~dp0venv\Scripts\python.exe" (
    echo [2/4] venv already exists, skipping creation.
) else (
    echo [2/4] Creating virtual environment venv ...
    %PYCMD% -m venv "%~dp0venv"
    if errorlevel 1 (
        echo ERROR: Failed to create venv!
        pause
        goto :EOF
    )
)
echo.

REM --- Upgrade pip ---
echo [3/4] Upgrading pip ...
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

REM --- Install dependencies ---
echo [4/4] Installing all dependencies ...
echo       Mirror 1/2: Tsinghua ...
"%~dp0venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo       Tsinghua mirror failed. Trying mirror 2/2: Aliyun ...
    "%~dp0venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/
)
if errorlevel 1 (
    echo.
    echo ERROR: Both mirrors failed!
    echo Check your network, or try manually:
    echo   venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    goto :EOF
)

echo.
echo ======================================================================
echo  Install complete!
echo  Now run 0_RUN_FIRST.bat to start using the tools.
echo  First use will auto-download models (~1.6GB + ~3GB).
echo ======================================================================
echo.
pause
