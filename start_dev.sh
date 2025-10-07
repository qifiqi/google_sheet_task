#!/bin/bash

echo "Starting Google Sheet Task Management System - Development Mode"
echo ""

echo "[1/3] Checking Python environment..."
python3 --version
if [ $? -ne 0 ]; then
    echo "Error: Python not found. Please install Python 3.8+"
    exit 1
fi

echo "[2/3] Starting Flask backend server..."
python3 run.py &
BACKEND_PID=$!

echo "[3/3] Starting Vue frontend development server..."
cd frontend

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo "Starting frontend development server..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo " Development servers are running..."
echo "========================================"
echo " Backend:  http://localhost:5000"
echo " Frontend: http://localhost:8080"
echo "========================================"
echo ""
echo "Press Ctrl+C to stop all servers..."

# 等待用户中断
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
