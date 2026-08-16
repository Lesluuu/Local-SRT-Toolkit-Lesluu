@echo off
REM ============================================================
REM  Local-SRT-Toolkit :: 唯一入口 / 诊断 & 启动菜单
REM  用户下载 ZIP 后: 第一个就双击这个文件, 一切自动搞定
REM ============================================================

REM ---- 【防闪退一: 任何情况下出错都先等用户看清再关窗口】 ----
if not defined SRTKIT_REENTRY (
    set "SRTKIT_REENTRY=1"
    REM 用 cmd /k 重启自己, 程序结束窗口也不会关
    "%COMSPEC%" /k ""%~f0" %*"
    exit /b
)

chcp 65001 >nul 2>&1
cd /d "%~dp0"
title Local-SRT-Toolkit 启动中心

echo.
echo  8888888 888       888 8888888b.   .d8888b.        8888888b.   .d88888b.  8888888b. 
echo    888   888   o   888 888   Y88b d88P  Y88b       888   Y88b d88P  Y88b 888   Y88b
echo    888   888  d8b  888 888    888 888    888       888    888 888    888 888    888
echo    888   888 d888b 888 888   d88P 888              888   d88P 888    888 888   d88P
echo    888   888d88888b888 8888888P   888              8888888P   888    888 8888888P  
echo    888   88888P Y88888 888 T88b   888    888       888        888    888 888 T88b  
echo    888   8888P   Y8888 888  T88b  Y88b  d88P       888        Y88b  d88P 888  T88b 
echo  8888888 888P     Y888 888   T88b  Y8888P         888         Y88888P  888   T88b
echo.
echo ========================================================================
echo  Local-SRT-Toolkit  启动中心  v2
echo ========================================================================
echo.
echo  声明: 这个精度不高, 是摸索 AI 做着玩的东西, 只是记录一下。
echo.

REM ============================================================
REM  【第一步】自动解除 Windows 的「阻止」标记 (从网上下载ZIP最常见坑)
REM ============================================================
echo [1/4] 解除 Windows 阻止标记 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='%~dp0'; Get-ChildItem -Path $p -Recurse -Include '*.bat','*.py','*.txt','*.md','*.json','*' | Unblock-File -ErrorAction SilentlyContinue"
echo       完成.

REM ============================================================
REM  【第二步】检测 Python
REM ============================================================
echo.
echo [2/4] 检测 Python 环境 ...
set "PYCMD="
where py >nul 2>nul   && set "PYCMD=py -3"
if "%PYCMD%"=="" where python >nul 2>nul && set "PYCMD=python"
if "%PYCMD%"=="" (
    echo.
    echo  ❌ 未检测到 Python !
    echo.
    echo  请先安装 Python 3.10 / 3.11 / 3.12 (只支持 64位 Windows):
    echo.
    echo    步骤 A: 打开下面这个网址下载安装包:
    echo            https://www.python.org/downloads/
    echo.
    echo    步骤 B: 安装时务必勾选 「Add Python to PATH」(添加到系统路径)
    echo            就在安装窗口最下方的复选框, 一定要打勾!
    echo.
    echo    步骤 C: 安装完成后, 关掉这个窗口, 重新双击本文件.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%V in ('%PYCMD% --version 2^>^&1') do set "PYVER=%%V"
echo       ✅ %PYVER%

REM ============================================================
REM  【第三步】检测虚拟环境 venv, 不存在则引导安装
REM ============================================================
echo.
echo [3/4] 检查虚拟环境 venv ...
set "VENV_PY=%~dp0venv\Scripts\python.exe"
set "NEED_INSTALL=0"
if not exist "%VENV_PY%" (
    set "NEED_INSTALL=1"
    echo       ❌ 还没安装依赖. 接下来将自动安装 (约 2-5 分钟, 需联网).
) else (
    echo       ✅ 虚拟环境已存在.
    echo.
    echo [3b] 验证依赖是否完整 ...
    "%VENV_PY%" -c "import faster_whisper, transformers, torch, av, ctranslate2, sentencepiece; print('       OK')" 2>nul
    if errorlevel 1 (
        echo       ⚠️  依赖缺失或损坏, 需要重新安装.
        set "NEED_INSTALL=1"
    ) else (
        echo       ✅ 依赖全部正常.
    )
)

REM --- 需要安装则自动跑一键安装 ---
if "%NEED_INSTALL%"=="1" (
    echo.
    echo ========================================================================
    echo  即将开始安装依赖 (从清华镜像下载, 不需要你操作, 等就行)...
    echo ========================================================================
    pause
    call "%~dp0一键安装.bat"
    REM 安装后再检查一次
    if not exist "%VENV_PY%" (
        echo ❌ 安装失败, 请截图上面的错误信息发给开发者.
        pause
        exit /b 1
    )
)

REM ============================================================
REM  【第四步】启动菜单
REM ============================================================
:MENU
echo.
echo ========================================================================
echo  ✅ 环境准备完成!  请选择要启动的功能 (输入数字回车):
echo ========================================================================
echo.
echo    [1]  开始"转录视频生成字幕"    (start_transcribe.bat)
echo    [2]  开始"翻译字幕为中文"      (start_translate.bat)
echo    [3]  重新安装 / 修复依赖       (一键安装.bat)
echo    [4]  打开使用说明
echo    [q]  退出
echo.
set /p "CHOICE=请选择 > "
if "%CHOICE%"=="1" (
    "%VENV_PY%" "%~dp0transcribe.py"
    goto MENU
)
if "%CHOICE%"=="2" (
    "%VENV_PY%" "%~dp0translate.py"
    goto MENU
)
if "%CHOICE%"=="3" (
    call "%~dp0一键安装.bat"
    goto MENU
)
if "%CHOICE%"=="4" (
    notepad "%~dp0使用说明.txt"
    goto MENU
)
if /i "%CHOICE%"=="q" (
    echo 👋 再见.
    pause
    exit /b 0
)
echo ❌ 无效选择, 请输入 1 / 2 / 3 / 4 / q
goto MENU
