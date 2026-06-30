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

ask_partial_count() {
    while true; do
        echo "partial count:"
        echo "  return or auto = auto"
        echo "  allowed: $ALLOWED_COUNTS"
        read -r -p "count: " COUNT_INPUT
        COUNT_INPUT="$(printf '%s' "$COUNT_INPUT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
        case "$COUNT_INPUT" in
            ""|auto)
                PARTIAL_COUNT="auto"
                return 0
                ;;
            *)
                case " $ALLOWED_COUNTS " in
                    *" $COUNT_INPUT "*)
                        PARTIAL_COUNT="$COUNT_INPUT"
                        return 0
                        ;;
                    *)
                        echo "unknown count: $COUNT_INPUT"
                        echo "use auto or one of: $ALLOWED_COUNTS"
                        ;;
                esac
                ;;
        esac
    done
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

VERSION_LABEL="$($PYTHON "$SCRIPT" --version 2>/dev/null)"
if [ -n "$VERSION_LABEL" ]; then
    echo "$VERSION_LABEL diagnostics launcher"
else
    echo "X5 Crop diagnostics launcher"
fi
echo "Folder: $(pwd)"
echo
echo "This is a local development diagnostics launcher."
echo "It always runs dry run + Debug Analysis + diagnostics."
echo "No cropped TIFF files will be exported, and review files will not be copied."
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
            ALLOWED_COUNTS="1 2 3 4 5 6"
            break
            ;;
        dual|135dual|135-dual)
            FORMAT="135-dual"
            COUNT="12"
            ALLOWED_COUNTS="12"
            break
            ;;
        xpan)
            FORMAT="xpan"
            COUNT="3"
            ALLOWED_COUNTS="1 2 3"
            break
            ;;
        half)
            FORMAT="half"
            COUNT="12"
            ALLOWED_COUNTS="1 2 3 4 5 6 7 8 9 10 11 12"
            break
            ;;
        645|120645|120-645)
            FORMAT="120-645"
            COUNT="4"
            ALLOWED_COUNTS="1 2 3 4"
            break
            ;;
        66|12066|120-66)
            FORMAT="120-66"
            COUNT="3"
            ALLOWED_COUNTS="1 2 3"
            break
            ;;
        67|12067|120-67)
            FORMAT="120-67"
            COUNT="3"
            ALLOWED_COUNTS="1 2 3"
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
    ask_partial_count
else
    STRIP="full"
    PARTIAL_COUNT="auto"
fi

echo
echo "diagnostics: enabled"
echo "debug analysis: enabled"
echo "dry run: enabled"
if [ "$STRIP" = "full" ]; then
    echo "strip mode: full"
else
    echo "strip mode: partial"
    echo "count: $PARTIAL_COUNT"
fi
echo

ARGS=("$SCRIPT" "." --format "$FORMAT" --strip "$STRIP" --report --debug-analysis --dry-run --diagnostics --no-copy-review-files --no-reuse-analysis --jobs 4)
if [ "$STRIP" = "full" ]; then
    ARGS+=(--count "$COUNT")
elif [ "$PARTIAL_COUNT" != "auto" ]; then
    ARGS+=(--count "$PARTIAL_COUNT")
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
