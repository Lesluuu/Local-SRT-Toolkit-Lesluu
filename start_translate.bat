@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================================
echo   Local-SRT-Toolkit  ::  本地多语言 SRT 字幕翻译  →  中文
echo   (日文 / 英文 / 韩文  →  中文)   模型: NLLB-200, 完全离线
echo ======================================================================
echo.
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
%PYCMD% "%~dp0translate.py"
echo.
echo ======================================================================
echo   完成.  按任意键关闭本窗口.
echo ======================================================================
pause >nul
