@echo off
cd /d "%~dp0"
echo.
echo === Deploying updates to Railway ===
echo.

git add .
git commit -m "Update web interface and tools (Password toggle + User management)"
git push origin main

if errorlevel 1 (
    echo.
    echo Deployment failed. Please check your internet connection or Git settings.
) else (
    echo.
    echo Deployment successful!
    echo The site will be updated automatically in a few minutes.
)

pause