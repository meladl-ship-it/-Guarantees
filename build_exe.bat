@echo off
chcp 65001 >nul
echo Starting build process...

REM Map current directory to Z: to handle Unicode paths
subst Z: /d >nul 2>&1
subst Z: "%~dp0."
if errorlevel 1 (
    echo Failed to map virtual drive.
    pause
    exit /b 1
)

pushd Z:

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Determine Python executable
if exist ".venv\Scripts\python.exe" (
    echo Using venv Python...
    set PYTHON_EXE=.venv\Scripts\python.exe
) else (
    echo Using system Python...
    set PYTHON_EXE=python
)

REM Run PyInstaller
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm Guarantees.spec

if errorlevel 1 (
    echo.
    echo ==============================
    echo       BUILD FAILED!
    echo ==============================
    popd
    subst Z: /d
    pause
    exit /b 1
)

echo.
echo ==============================
echo       BUILD SUCCESSFUL!
echo ==============================
popd
subst Z: /d
pause
