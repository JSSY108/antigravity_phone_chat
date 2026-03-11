@echo off
setlocal enabledelayedexpansion
title Antigravity Phone Connect

:: Navigate to the script's directory
cd /d "%~dp0"

:: Check for .env file
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env file not found. Creating from .env.example...
        copy .env.example .env >nul
        echo [SUCCESS] .env created from template!
        echo [ACTION] Please update .env if you wish to change defaults.
        echo.
    )
)

echo ===================================================
echo   Antigravity Phone Connect Launcher
echo ===================================================
echo.

echo [INFO] .env configuration found.

echo [DEBUG] Checking if port 9000 is available for Antigravity Remote Debugging...
netstat -ano | findstr :9000

echo [STARTING] Launching via Unified Launcher...
echo [DEBUG] Starting Antigravity with Remote Debugging on port 9000...
python launcher.py --mode local

:: Keep window open if server crashes
echo.
echo [INFO] Server stopped. Press any key to exit.
pause >nul

