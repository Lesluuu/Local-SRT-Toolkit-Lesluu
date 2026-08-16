@echo off
REM ============================================================
REM  Local-SRT-Toolkit :: 启动字幕转录 (也可由 0_先运行这个.bat 调用)
REM ============================================================
REM ---- 防闪退: 任何退出都等用户 ----
if not defined SRTKIT_REENTRY (
    set "SRTKIT_REENTRY=1"
    "%COMSPEC%" /k ""%~f0" %*"
    exit /b
)

chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit · 字幕转录

echo.
echo ======================================================================
echo   Local-SRT-Toolkit :: 高精度本地字幕转录 (faster-whisper)
echo   日语/影视语气词增强模式 · GPU/CPU 自动检测
echo ======================================================================
echo.
echo  ⚠️ 声明: 这个精度不高, 是摸索 AI 做着玩的东西, 只是记录一下。
echo.

set "VENV_PY=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo ❌ 还没安装依赖!
    echo   请先双击 「0_先运行这个.bat」, 它会自动帮你装好一切, 再回到这里.
    echo.
    pause
    exit /b 1
)

"%VENV_PY%" "%~dp0transcribe.py"
set "EXITCODE=%errorlevel%"
echo.
echo ======================================================================
echo   完成 (退出码=%EXITCODE%).
echo   想转录其他视频或换功能, 双击「0_先运行这个.bat」回到主菜单.
echo ======================================================================
pause
