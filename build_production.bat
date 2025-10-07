@echo off
echo Building Google Sheet Task Management System for Production
echo.

echo [1/3] Checking Node.js environment...
node --version
if %ERRORLEVEL% neq 0 (
    echo Error: Node.js not found. Please install Node.js 16+
    pause
    exit /b 1
)

echo [2/3] Installing frontend dependencies...
cd frontend
npm install
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

echo [3/3] Building Vue frontend for production...
npm run build
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to build frontend
    pause
    exit /b 1
)

cd ..
echo.
echo ========================================
echo  Production build completed!
echo ========================================
echo  Built files are in: static/dist/
echo  Start the server with: python run.py
echo  Then visit: http://localhost:5000
echo ========================================
echo.
pause
