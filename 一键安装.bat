@echo off
REM ============================================================
REM  Local-SRT-Toolkit :: 一键安装依赖 (也可由 0_先运行这个.bat 调用)
REM ============================================================
if not defined SRTKIT_REENTRY (
    set "SRTKIT_REENTRY=1"
    "%COMSPEC%" /k ""%~f0" %*"
    exit /b
)

chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit · 安装依赖

echo.
echo ======================================================================
echo   Local-SRT-Toolkit :: 一键安装依赖
echo   (自动创建 venv 虚拟环境 + 从清华镜像安装所有 pip 包)
echo ======================================================================
echo.

set "PYCMD="
where py >nul 2>nul   && set "PYCMD=py -3"
if "%PYCMD%"=="" where python >nul 2>nul && set "PYCMD=python"
if "%PYCMD%"=="" (
    echo [错误] 未检测到 Python!
    echo 请先安装 Python 3.10 / 3.11 / 3.12, 勾选 "Add Python to PATH":
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo [1/4] Python:
%PYCMD% --version
echo.

REM --- 创建 venv ---
if exist "%~dp0venv\Scripts\python.exe" (
    echo [2/4] 虚拟环境 venv 已存在, 跳过创建.
) else (
    echo [2/4] 正在创建虚拟环境 venv ...
    %PYCMD% -m venv "%~dp0venv"
    if errorlevel 1 (
        echo ❌ 创建虚拟环境失败!
        pause
        exit /b 1
    )
)
echo.

REM --- 升级 pip ---
echo [3/4] 升级 pip ...
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

REM --- 安装依赖, 失败自动换镜像 ---
echo [4/4] 正在安装所有依赖 ...
echo       镜像 1/2: 清华大学 ...
"%~dp0venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo   清华镜像失败, 尝试镜像 2/2: 阿里云 ...
    "%~dp0venv\Scripts\pip.exe" install -r "%~dp0requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/
)
if errorlevel 1 (
    echo.
    echo ❌ 两个镜像都安装失败!
    echo 请检查网络, 或手动执行:
    echo   venv\Scripts\pip install -r requirements.txt -i ^<你的镜像^>
    echo.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   ✅ 安装完成!
echo.
echo   现在回到启动中心 (双击 0_先运行这个.bat) 选择功能开始使用.
echo   首次使用会自动下载模型 (转录 ~1.6GB + 翻译 ~3GB), 之后永久离线.
echo ======================================================================
echo.
pause
