@echo off
setlocal

chcp 65001 >nul
cd /d "%~dp0"
title DingTalk Stream Service

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
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_CMD=py -3"
        ) else (
            echo [ERROR] Python was not found.
            echo Install Python or create .venv, venv, or env first.
            pause
            exit /b 1
        )
    )
)

if not exist "ding_stream_service\__main__.py" (
    echo [ERROR] ding_stream_service was not found in the current directory.
    pause
    exit /b 1
)

if not exist "logs" mkdir "logs" >nul 2>nul

echo [INFO] Workdir: %cd%
echo [INFO] Python: %PYTHON_CMD%
echo [INFO] APP_ENV=%APP_ENV%
echo [INFO] Starting DingTalk Stream microservice...
echo.

call %PYTHON_CMD% -m ding_stream_service %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] DingTalk Stream microservice stopped. Exit code: %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
