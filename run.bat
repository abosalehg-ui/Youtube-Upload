@echo off
chcp 65001 >nul 2>nul
title YouTube Upload

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
    exit /b
)

:: Fix Qt platform plugin path
for /f "delims=" %%i in ('python -c "import os, PyQt5; print(os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms'))"') do set QT_QPA_PLATFORM_PLUGIN_PATH=%%i

if not exist "%QT_QPA_PLATFORM_PLUGIN_PATH%" (
    for /f "delims=" %%i in ('python -c "import os, PyQt5; print(os.path.join(os.path.dirname(PyQt5.__file__), 'Qt', 'plugins', 'platforms'))"') do set QT_QPA_PLATFORM_PLUGIN_PATH=%%i
)

echo  Starting application...
echo.
python main.py

if errorlevel 1 (
    echo.
    echo  Application exited with error.
    pause
)
pause
