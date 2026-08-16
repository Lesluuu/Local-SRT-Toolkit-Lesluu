@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================================
echo   Local-SRT-Toolkit  ::  高精度本地字幕转录 (faster-whisper)
echo   High-Accuracy GPU/CPU Transcribe  ·  日语/影视语气词增强模式
echo ======================================================================
echo.
REM  优先用 py -3 (Python Launcher), 找不到再用 python, 都不行就提示
set "PYCMD="
where py >nul 2>nul   && set "PYCMD=py -3"
if "%PYCMD%"=="" where python >nul 2>nul && set "PYCMD=python"
if "%PYCMD%"=="" (
    echo [ERROR] 未检测到 Python.  请先安装 Python 3.10 / 3.11 / 3.12 (勾选 Add to PATH).
    echo         https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
%PYCMD% "%~dp0transcribe.py"
echo.
echo ======================================================================
echo   完成.  按任意键关闭本窗口.
echo ======================================================================
pause >nul
