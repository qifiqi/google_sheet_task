@echo off
echo Starting Google Sheet Task Management System - Development Mode
echo.

echo [1/3] Checking Python environment...
python --version
if %ERRORLEVEL% neq 0 (
    echo Error: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo [2/3] Starting Flask backend server...
start "Flask Backend" cmd /k "python run.py"

echo [3/3] Starting Vue frontend development server...
cd frontend
if not exist node_modules (
    echo Installing frontend dependencies...
    npm install
)

echo Starting frontend development server...
start "Vue Frontend" cmd /k "npm run dev"

echo.
echo ========================================
echo  Development servers are starting...
echo ========================================
echo  Backend:  http://localhost:5000
echo  Frontend: http://localhost:8080
echo ========================================
echo.
echo Press any key to exit...
pause >nul
