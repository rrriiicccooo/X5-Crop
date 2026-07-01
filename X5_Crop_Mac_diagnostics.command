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

SCRIPT="./X5_Crop.py"
if [ ! -f "$SCRIPT" ]; then
    echo "X5_Crop.py was not found in this folder."
    echo "Put this diagnostics launcher in the same folder as X5_Crop.py and your TIFF scans."
    finish 1
fi

find_python() {
    REQUIRED_IMPORTS="import numpy, PIL, tifffile"
    CHECKED=""

    try_python() {
        CANDIDATE="$1"
        [ -n "$CANDIDATE" ] || return 1
        case "
$CHECKED
" in
            *"
$CANDIDATE
"*) return 1 ;;
        esac
        CHECKED="${CHECKED}
$CANDIDATE"
        "$CANDIDATE" -c "$REQUIRED_IMPORTS" >/dev/null 2>&1 || return 1
        PYTHON="$CANDIDATE"
        return 0
    }

    if [ -n "${X5_CROP_PYTHON:-}" ]; then
        try_python "$X5_CROP_PYTHON" && return 0
    fi
    try_python "/opt/homebrew/bin/python3" && return 0
    try_python "/usr/local/bin/python3" && return 0
    try_python "$(command -v python3 2>/dev/null)" && return 0
    try_python "$(command -v python 2>/dev/null)" && return 0
    try_python "/usr/bin/python3" && return 0

    return 1
}

if ! find_python; then
    echo "A usable Python was not found."
    echo "The launcher needs Python with numpy, Pillow, and tifffile installed."
    echo "Run install/X5_Crop_Mac_install.command first, then try again."
    echo
    echo "Checked:"
    printf '%s\n' "$CHECKED" | sed '/^$/d'
    finish 1
fi

$PYTHON "$SCRIPT" --interactive-diagnostics
EXITCODE=$?

echo
if [ "$EXITCODE" -ne 0 ]; then
    echo "Finished with errors. Read the messages above."
else
    echo "Finished successfully."
fi
finish "$EXITCODE"
