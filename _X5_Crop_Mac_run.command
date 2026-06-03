#!/bin/bash

cd "$(dirname "$0")" || exit 1

STRIP="${1:-full}"
MODE="${2:-normal}"

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

SCRIPT="./X5_Crop.py"
if [ ! -f "$SCRIPT" ]; then
    echo "X5_Crop.py was not found in this folder."
    echo "Put this launcher in the same folder as X5_Crop.py and your TIFF scans."
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

echo "X5 Crop V2 ${STRIP} launcher"
echo "Folder: $(pwd)"
echo
echo "This will process TIFF files in this folder."
echo "Output: split_output"
echo "Existing output files will not be overwritten."
if [ "$MODE" = "debug" ]; then
    echo "Debug analysis: split_output/_debug_analysis"
    echo "Dry run: no cropped TIFF files will be written."
fi
echo

echo "Choose film format:"
echo "  [Return] or 135 = 135"
echo "  xpan = XPAN"
echo "  half = half-frame"
echo "  645 = 120-645"
echo "  66 = 120-66"
echo "  67 = 120-67"
echo
read -r -p "Format [135]: " FORMAT_INPUT
FORMAT_INPUT="$(printf '%s' "$FORMAT_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
case "$FORMAT_INPUT" in
    ""|135)
        FORMAT="135"
        ;;
    xpan)
        FORMAT="xpan"
        ;;
    half)
        FORMAT="half"
        ;;
    645|120645|120-645)
        FORMAT="120-645"
        ;;
    66|12066|120-66)
        FORMAT="120-66"
        ;;
    67|12067|120-67)
        FORMAT="120-67"
        ;;
    *)
        echo "Unknown format: $FORMAT_INPUT"
        echo "Use Return/135, xpan, half, 645, 66, or 67."
        finish 1
        ;;
esac
echo "Selected format: $FORMAT"
echo

ARGS=("$SCRIPT" "." --format "$FORMAT" --strip "$STRIP" --report)
if [ "$MODE" = "debug" ]; then
    ARGS+=(--debug-analysis --dry-run)
fi

$PYTHON "${ARGS[@]}"
EXITCODE=$?

echo
if [ "$EXITCODE" -ne 0 ]; then
    echo "Finished with errors. Read the messages above."
else
    echo "Finished successfully."
fi
finish "$EXITCODE"
