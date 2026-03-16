#!/usr/bin/env bash
# build.sh — Build standalone executable (Linux / macOS)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo " Dynamixel ID Setter — PyInstaller Build"
echo "============================================"

# Detect python command
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "[!] Python not found. Please install Python."
    exit 1
fi

echo "[*] Using $PYTHON"

# Ensure requirements are installed
echo "[*] Installing dependencies..."
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install -r requirements.txt

# Run PyInstaller
echo "[*] Running PyInstaller..."
$PYTHON -m PyInstaller \
    --onefile \
    --noconsole \
    --name DynamixelIDSetter \
    --clean \
    main.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✔ Build complete!"
    echo "  Executable: dist/DynamixelIDSetter"
    echo ""
else
    echo "[!] Build failed!"
    exit 1
fi

