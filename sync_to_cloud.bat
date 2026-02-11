@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo Using venv Python...
    set PYTHON_EXE=.venv\Scripts\python.exe
) else (
    echo Using system Python...
    set PYTHON_EXE=python
)

echo.
echo === Starting Cloud Sync ===
echo.
"%PYTHON_EXE%" cloud_sync.py
echo.

if errorlevel 1 (
    echo Sync failed. Please check the errors above.
    echo You might need to install requests: pip install requests
) else (
    echo Operation completed successfully.
)

pause