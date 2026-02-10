@echo off
chcp 65001 >nul
echo Starting build process...

REM Map current directory to Z: to handle Unicode paths
subst Z: /d >nul 2>&1
subst Z: "%~dp0."
if errorlevel 1 (
    echo Failed to map virtual drive.
    exit /b 1
)

pushd Z:

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller using the venv python
REM Assuming .venv exists in the project root
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm Guarantees.spec

if errorlevel 1 (
    echo Build failed!
    popd
    subst Z: /d
    exit /b 1
)

echo Build successful!
popd
subst Z: /d