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

ask_yes_no() {
    PROMPT="$1"
    DEFAULT="$2"
    while true; do
        read -r -p "$PROMPT" ANSWER
        ANSWER="$(printf '%s' "$ANSWER" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
        case "$ANSWER" in
            "")
                printf '%s\n' "$DEFAULT"
                return 0
                ;;
            y|yes)
                printf '%s\n' "yes"
                return 0
                ;;
            n|no)
                printf '%s\n' "no"
                return 0
                ;;
            *)
                echo "use yes/no, y/n, or press return for no." >&2
                ;;
        esac
    done
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
    echo "Run install/X5_Crop_Mac_install.command first, then try again."
    finish 1
fi

echo "X5 Crop V3.3.1 launcher"
echo "Folder: $(pwd)"
echo
echo "This will process TIFF files in this folder."
echo "Existing output files will not be overwritten."
echo

echo "choose film format:"
echo "  return or 135 = 135"
echo "  dual = 135 dual"
echo "  xpan = xpan"
echo "  half = half-frame"
echo "  645 = 120-645"
echo "  66 = 120-66"
echo "  67 = 120-67"
echo
while true; do
    read -r -p "format: " FORMAT_INPUT
    FORMAT_INPUT="$(printf '%s' "$FORMAT_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$FORMAT_INPUT" in
        ""|135)
            FORMAT="135"
            COUNT="6"
            break
            ;;
        dual|135dual|135-dual)
            FORMAT="135-dual"
            COUNT="12"
            break
            ;;
        xpan)
            FORMAT="xpan"
            COUNT="3"
            break
            ;;
        half)
            FORMAT="half"
            COUNT="12"
            break
            ;;
        645|120645|120-645)
            FORMAT="120-645"
            COUNT="4"
            break
            ;;
        66|12066|120-66)
            FORMAT="120-66"
            COUNT="3"
            break
            ;;
        67|12067|120-67)
            FORMAT="120-67"
            COUNT="3"
            break
            ;;
        *)
            echo "unknown format: $FORMAT_INPUT"
            echo "use return/135, dual, xpan, half, 645, 66, or 67."
            ;;
    esac
done

PARTIAL_ANSWER="$(ask_yes_no "partial mode? [y/n, return=no]: " "no")"
if [ "$PARTIAL_ANSWER" = "yes" ]; then
    STRIP="partial"
else
    STRIP="full"
fi

DEBUG_ANSWER="$(ask_yes_no "debug analysis? [y/n, return=no]: " "no")"
if [ "$DEBUG_ANSWER" = "yes" ]; then
    DEBUG="yes"
else
    DEBUG="no"
fi

echo
if [ "$STRIP" = "full" ]; then
    echo "strip mode: full"
else
    echo "strip mode: partial"
    echo "count: auto"
fi
if [ "$DEBUG" = "yes" ]; then
    echo "debug analysis: enabled"
    echo "dry run: no cropped TIFF files will be written."
else
    echo "debug analysis: off"
fi
echo

ARGS=("$SCRIPT" "." --format "$FORMAT" --strip "$STRIP" --report)
if [ "$STRIP" = "full" ]; then
    ARGS+=(--count "$COUNT")
fi
if [ "$DEBUG" = "yes" ]; then
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
