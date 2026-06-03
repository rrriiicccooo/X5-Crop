#!/bin/bash

cd "$(dirname "$0")" || exit 1

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

SCRIPT="./X5_Split_v18.py"
if [ ! -f "$SCRIPT" ]; then
    echo "X5_Split_v18.py was not found in this folder."
    echo "Put this launcher in the same folder as X5_Split_v18.py and your TIFF scans."
    finish 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Python was not found."
    echo "Install Python 3, then install dependencies:"
    echo "  python3 -m pip install -U numpy tifffile imagecodecs Pillow"
    finish 1
fi

echo "X5 Split v18 DEBUG double-click launcher"
echo "Folder: $(pwd)"
echo
echo "This will analyze TIFF files in this folder and write debug crop previews."
echo "Output: split_output"
echo "Debug: split_output/_debug"
echo "Dry run: no cropped TIFF files will be written."
echo

$PYTHON "$SCRIPT" "." --report --debug --dry-run
EXITCODE=$?

echo
if [ "$EXITCODE" -ne 0 ]; then
    echo "Finished with errors. Read the messages above."
else
    echo "Finished successfully."
fi
finish "$EXITCODE"
