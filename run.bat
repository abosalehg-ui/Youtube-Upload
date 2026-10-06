@echo off
chcp 65001 >nul 2>nul
title YouTube Upload
cd /d "%~dp0"

echo.
echo  YouTube Upload - Channel Manager
echo  =================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed!
    echo  Download from: https://python.org/downloads
    pause
    exit /b 1
)

:: Virtual environment (does not touch the system Python)
if not exist ".venv\Scripts\python.exe" (
    echo  Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo  Checking requirements...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error

echo  Starting application...
echo.
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo  Application exited with error.
pause
exit /b 1
