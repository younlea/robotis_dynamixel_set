#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# build.sh — Build standalone executable (Linux / macOS)
# ──────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo " Dynamixel ID Setter — PyInstaller Build"
echo "============================================"

# Ensure requirements are installed
echo "[*] Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Ensure pyinstaller is available
if ! command -v pyinstaller &>/dev/null; then
    echo "[!] PyInstaller not found. Installing..."
    pip install pyinstaller
fi

pyinstaller \
    --onefile \
    --noconsole \
    --name DynamixelIDSetter \
    --clean \
    main.py

echo ""
echo "✔ Build complete!"
echo "  Executable: dist/DynamixelIDSetter"
echo ""
