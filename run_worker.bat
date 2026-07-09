@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
title XPL Analysis Worker
chcp 65001 >nul

if "%APP_ENV%"=="" set "APP_ENV=production"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
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

if not exist "xpl_worker\main.py" (
    echo [ERROR] xpl_worker\main.py was not found.
    pause
    exit /b 1
)

if not exist "logs" mkdir "logs" >nul 2>nul
if not exist "data" mkdir "data" >nul 2>nul

if "%XPL_WORKER_EXECUTOR%"=="" set "XPL_WORKER_EXECUTOR=process"
if "%XPL_WORKER_CONCURRENCY%"=="" set "XPL_WORKER_CONCURRENCY=2"
if "%XPL_WORKER_BATCH_SIZE%"=="" set "XPL_WORKER_BATCH_SIZE=4"
if "%XPL_WORKER_POLL_INTERVAL%"=="" set "XPL_WORKER_POLL_INTERVAL=2"
if "%XPL_WORKER_STALE_AFTER%"=="" set "XPL_WORKER_STALE_AFTER=300"

echo [INFO] Workdir: %cd%
echo [INFO] Python: %PYTHON_CMD%
echo [INFO] APP_ENV=%APP_ENV%
echo [INFO] XPL_WORKER_EXECUTOR=%XPL_WORKER_EXECUTOR%
echo [INFO] XPL_WORKER_CONCURRENCY=%XPL_WORKER_CONCURRENCY%
echo [INFO] XPL_WORKER_BATCH_SIZE=%XPL_WORKER_BATCH_SIZE%
echo [INFO] XPL_WORKER_POLL_INTERVAL=%XPL_WORKER_POLL_INTERVAL%
echo [INFO] XPL_WORKER_STALE_AFTER=%XPL_WORKER_STALE_AFTER%
echo [INFO] Starting XPL analysis worker...
echo.

call %PYTHON_CMD% -m xpl_worker.main --executor %XPL_WORKER_EXECUTOR% --concurrency %XPL_WORKER_CONCURRENCY% --batch-size %XPL_WORKER_BATCH_SIZE% --poll-interval %XPL_WORKER_POLL_INTERVAL% --stale-after %XPL_WORKER_STALE_AFTER% %*
set "EXIT_CODE=!ERRORLEVEL!"

if not "!EXIT_CODE!"=="0" (
    echo.
    echo [ERROR] XPL worker failed. Exit code: !EXIT_CODE!
    pause
)

exit /b !EXIT_CODE!
