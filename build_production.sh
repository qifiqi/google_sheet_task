#!/bin/bash

echo "Building Google Sheet Task Management System for Production"
echo ""

echo "[1/3] Checking Node.js environment..."
node --version
if [ $? -ne 0 ]; then
    echo "Error: Node.js not found. Please install Node.js 16+"
    exit 1
fi

echo "[2/3] Installing frontend dependencies..."
cd frontend
npm install
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi

echo "[3/3] Building Vue frontend for production..."
npm run build
if [ $? -ne 0 ]; then
    echo "Error: Failed to build frontend"
    exit 1
fi

cd ..
echo ""
echo "========================================"
echo " Production build completed!"
echo "========================================"
echo " Built files are in: static/dist/"
echo " Start the server with: python3 run.py"
echo " Then visit: http://localhost:5000"
echo "========================================"
echo ""
