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

echo "X5 Crop uninstall helper for macOS"
echo "Folder: $(pwd)"
echo
echo "This project is a portable script. Removing the folder removes the script,"
echo "launchers, reports, and output files in this folder."
echo
echo "This helper can also uninstall the user-level Python packages installed for X5 Crop:"
echo "numpy tifffile imagecodecs Pillow"
echo
echo "Important: those packages may also be used by other Python scripts on this Mac."
echo "Python itself will NOT be removed by this helper."
echo

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BASE="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BASE="python"
else
    echo "Python was not found. There are no Python packages to uninstall from here."
    echo "You can delete this X5 Crop folder manually."
    finish 0
fi

echo "Python:"
$PYTHON_BASE --version
echo

read -r -p "Uninstall X5 Crop Python packages from this user account? [y/N] " ANSWER
case "$ANSWER" in
    y|Y|yes|YES)
        $PYTHON_BASE -m pip uninstall -y numpy tifffile imagecodecs Pillow || true
        ;;
    *)
        echo "Skipped Python package uninstall."
        ;;
esac

echo
read -r -p "Purge pip download cache for this user? [y/N] " CACHE_ANSWER
case "$CACHE_ANSWER" in
    y|Y|yes|YES)
        $PYTHON_BASE -m pip cache purge || true
        ;;
    *)
        echo "Skipped pip cache purge."
        ;;
esac

echo
echo "Uninstall helper finished."
echo "To remove X5 Crop itself, delete this X5 Crop folder."
echo "To keep your cropped TIFF output, move x5_crop_output/ somewhere safe before deleting the folder."
finish 0
