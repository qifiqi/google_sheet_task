@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
title Google 参数批量校验 - 启动器

set "APP_ENV=production"
set "FLASK_DEBUG=false"

set "PYTHON_CMD="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_CMD=venv\Scripts\python.exe"
) else if exist "env\Scripts\python.exe" (
    set "PYTHON_CMD=env\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        where py >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] 未找到 Python。
            echo 请先安装 Python，或在项目目录创建 .venv / venv / env 虚拟环境。
            pause
            exit /b 1
        )
        set "PYTHON_CMD=py -3"
    ) else (
        set "PYTHON_CMD=python"
    )
)

if not exist "run.py" (
    echo [ERROR] 当前目录未找到 run.py
    pause
    exit /b 1
)

if not exist "logs" mkdir "logs" >nul 2>nul
if not exist "data" mkdir "data" >nul 2>nul

echo [INFO] 工作目录: %cd%
echo [INFO] Python: %PYTHON_CMD%
echo [INFO] APP_ENV=%APP_ENV%
echo [INFO] FLASK_DEBUG=%FLASK_DEBUG%
echo [INFO] 正在启动应用...
echo.

%PYTHON_CMD% run.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] 应用启动失败，退出码: %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
