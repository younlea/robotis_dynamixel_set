@echo off
REM ──────────────────────────────────────────────────────────────
REM build.bat — Build standalone executable (Windows)
REM ──────────────────────────────────────────────────────────────

echo ============================================
echo  Dynamixel ID Setter — PyInstaller Build
echo ============================================

echo [*] Installing dependencies from requirements.txt...
pip install -r requirements.txt

where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] PyInstaller not found. Installing...
    pip install pyinstaller
)

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name DynamixelIDSetter ^
    --clean ^
    main.py

echo.
echo  Build complete!
echo   Executable: dist\DynamixelIDSetter.exe
echo.
pause
