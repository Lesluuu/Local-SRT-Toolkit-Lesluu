@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit

echo.
echo ========================================================================
echo  Local-SRT-Toolkit  -  Start Center
echo ========================================================================
echo  NOTE: This is a hobby project for exploring AI. Accuracy is limited.
echo.

REM --- Step 1: Unblock files downloaded from internet ---
echo [1/4] Unlocking downloaded files ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0' -Recurse | Unblock-File -ErrorAction SilentlyContinue"
echo       Done.

REM --- Step 2: Check Python ---
echo.
echo [2/4] Checking Python ...
set "PYCMD="
where py >nul 2>nul   && set "PYCMD=py -3"
if "%PYCMD%"=="" where python >nul 2>nul && set "PYCMD=python"
if "%PYCMD%"=="" (
    echo.
    echo  ERROR: Python not found!
    echo.
    echo  Please install Python 3.10 / 3.11 / 3.12 (64-bit Windows):
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    goto :EOF
)
for /f "delims=" %%V in ('%PYCMD% --version 2^>^&1') do set "PYVER=%%V"
echo       OK: %PYVER%

REM --- Step 3: Check venv ---
echo.
echo [3/4] Checking virtual environment ...
set "VENV_PY=%~dp0venv\Scripts\python.exe"
set "NEED_INSTALL=0"
if not exist "%VENV_PY%" (
    set "NEED_INSTALL=1"
    echo       venv not found. Will install now (2-5 min, needs internet).
) else (
    echo       venv exists. Verifying dependencies ...
    "%VENV_PY%" -c "import faster_whisper, transformers, torch, av, ctranslate2, sentencepiece" 2>nul
    if errorlevel 1 (
        echo       Dependencies missing. Will reinstall.
        set "NEED_INSTALL=1"
    ) else (
        echo       All dependencies OK.
    )
)

if "%NEED_INSTALL%"=="1" (
    echo.
    echo ========================================================================
    echo  Installing dependencies ... (please wait, no action needed)
    echo ========================================================================
    pause
    call "%~dp0install.bat"
    if not exist "%VENV_PY%" (
        echo.
        echo INSTALL FAILED. Please screenshot the errors above.
        pause
        goto :EOF
    )
)

REM --- Step 4: Menu ---
:MENU
echo.
echo ========================================================================
echo  Ready! Choose a function (type number + Enter):
echo ========================================================================
echo.
echo    [1]  Transcribe video to subtitles
echo    [2]  Translate subtitles to Chinese
echo    [3]  Reinstall / repair dependencies
echo    [4]  Open usage guide (Chinese)
echo    [q]  Quit
echo.
set /p "CHOICE=Choice > "
if "%CHOICE%"=="1" (
    call "%~dp0start_transcribe.bat"
    goto MENU
)
if "%CHOICE%"=="2" (
    call "%~dp0start_translate.bat"
    goto MENU
)
if "%CHOICE%"=="3" (
    call "%~dp0install.bat"
    goto MENU
)
if "%CHOICE%"=="4" (
    notepad "%~dp0USAGE_CN.txt"
    goto MENU
)
if /i "%CHOICE%"=="q" (
    echo Bye.
    pause
    goto :EOF
)
echo Invalid choice. Enter 1 / 2 / 3 / 4 / q
goto MENU
