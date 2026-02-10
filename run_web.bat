@echo off
cd /d "%~dp0"
echo Starting Guarantees Web App...
".venv\Scripts\python.exe" web_app.py
pause