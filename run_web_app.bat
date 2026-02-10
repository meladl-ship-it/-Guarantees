@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Guarantees Web Server
echo ===================================================
echo      Guarantees System - Web Server Starting
echo ===================================================
echo.
echo Please wait while the server starts...
echo.

:: Open browser after a slight delay
timeout /t 3 /nobreak >nul
start http://sagan.irc.com

:: Run the application using the virtual environment
call .venv\Scripts\activate
python web_app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: The server crashed or failed to start.
    pause
)
