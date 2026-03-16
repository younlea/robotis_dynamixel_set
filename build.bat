@echo off
setlocal

echo ============================================
echo  Dynamixel ID Setter - PyInstaller Build
echo ============================================

REM 1. Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Python not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)

REM 2. Install dependencies
echo [*] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [!] Failed to install dependencies.
    pause
    exit /b 1
)

REM 3. Run PyInstaller
echo [*] Running PyInstaller...
python -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name DynamixelIDSetter ^
    --clean ^
    main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Build failed!
    pause
    exit /b 1
)

echo.
echo  Build complete!
echo   Executable: dist\DynamixelIDSetter.exe
echo.
pause

