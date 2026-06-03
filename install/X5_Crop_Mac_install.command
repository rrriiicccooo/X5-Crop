#!/bin/bash

cd "$(dirname "$0")/.." || exit 1

close_terminal_window() {
    case "${TERM_PROGRAM:-}" in
        Apple_Terminal)
            nohup sh -c 'sleep 0.25; osascript -e "tell application \"Terminal\" to close front window"' >/dev/null 2>&1 &
            ;;
        iTerm.app)
            nohup sh -c 'sleep 0.25; osascript -e "tell application \"iTerm2\" to close current window"' >/dev/null 2>&1 &
            ;;
    esac
}

finish() {
    EXITCODE="$1"
    echo
    read -r -p "Press Return to close..."
    close_terminal_window
    exit "$EXITCODE"
}

echo "X5 Crop first-time setup for macOS"
echo "Folder: $(pwd)"
echo

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BASE="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BASE="python"
else
    echo "Python 3 was not found."
    if command -v brew >/dev/null 2>&1; then
        read -r -p "Homebrew is available. Install Python with Homebrew now? [y/N] " ANSWER
        case "$ANSWER" in
            y|Y|yes|YES)
                brew install python || finish 1
                PYTHON_BASE="python3"
                ;;
            *)
                echo "Open https://www.python.org/downloads/macos/ and install Python 3, then run this setup again."
                open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
                finish 1
                ;;
        esac
    else
        echo "Open https://www.python.org/downloads/macos/ and install Python 3, then run this setup again."
        open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
        finish 1
    fi
fi

echo "Python:"
$PYTHON_BASE --version
echo

echo
echo "Installing dependencies for this user..."
$PYTHON_BASE -m ensurepip --upgrade >/dev/null 2>&1 || true
if ! $PYTHON_BASE -m pip install --user -U numpy tifffile imagecodecs Pillow; then
    echo
    echo "Standard user install failed."
    echo "On newer macOS/Homebrew Python this can be caused by externally-managed Python protection."
    read -r -p "Retry with --break-system-packages --user? [y/N] " ANSWER
    case "$ANSWER" in
        y|Y|yes|YES)
            $PYTHON_BASE -m pip install --user --break-system-packages -U numpy tifffile imagecodecs Pillow || finish 1
            ;;
        *)
            finish 1
            ;;
    esac
fi

echo
echo "Verifying dependencies..."
if ! $PYTHON_BASE - <<'PY'
import numpy
import tifffile
import imagecodecs
from PIL import Image
print("Dependencies OK")
PY
then
    finish 1
fi

echo
echo "Setup finished successfully."
echo "You can now use X5_Crop_Mac.command."
finish 0
