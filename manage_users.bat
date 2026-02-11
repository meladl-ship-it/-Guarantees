@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo Using venv Python...
    set PYTHON_EXE=.venv\Scripts\python.exe
) else (
    echo Using system Python...
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" manage_users.py
pause
