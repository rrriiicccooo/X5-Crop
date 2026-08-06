#!/bin/bash
# Release installer template; packaged under install/.

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

is_supported_python() {
    "$1" -c "import struct, sys; raise SystemExit(not ((3, 12) <= sys.version_info[:2] < (3, 15) and struct.calcsize('P') == 8))" >/dev/null 2>&1
}

find_supported_python() {
    for CANDIDATE in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)"; do
        [ -n "$CANDIDATE" ] || continue
        if is_supported_python "$CANDIDATE"; then
            PYTHON_BASE="$CANDIDATE"
            return 0
        fi
    done
    return 1
}

echo "X5 Crop first-time setup for macOS"
echo "Folder: $(pwd)"
echo

MACOS_MAJOR="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
if [ -z "$MACOS_MAJOR" ] || [ "$MACOS_MAJOR" -lt 14 ] 2>/dev/null; then
    echo "X5 Crop requires macOS 14 or later. No dependency was installed."
    finish 1
fi

for REQUIRED_FILE in install/requirements.txt install/dependency_manager.py; do
    if [ ! -f "$REQUIRED_FILE" ]; then
        echo "Missing setup file: $REQUIRED_FILE"
        finish 1
    fi
done

echo "Preparing launchers for macOS..."
chmod +x "X5_Crop_Mac.command" >/dev/null 2>&1 || true
chmod +x "install/X5_Crop_Mac_install.command" >/dev/null 2>&1 || true
chmod +x "install/X5_Crop_Mac_uninstall.command" >/dev/null 2>&1 || true
if command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine . >/dev/null 2>&1 || true
fi
echo "Launcher permissions prepared."
echo

PYTHON_BASE=""
if ! find_supported_python; then
    echo "Python 3.12-3.14 was not found."
    if command -v brew >/dev/null 2>&1; then
        read -r -p "Homebrew is available. Install a supported Python now? [y/N] " ANSWER
        case "$ANSWER" in
            y|Y|yes|YES)
                brew install python || finish 1
                find_supported_python || finish 1
                ;;
            *)
                echo "Install Python 3.12-3.14 from https://www.python.org/downloads/macos/ and run setup again."
                open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
                finish 1
                ;;
        esac
    else
        echo "Install Python 3.12-3.14 from https://www.python.org/downloads/macos/ and run setup again."
        open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
        finish 1
    fi
fi

echo "Python:"
"$PYTHON_BASE" --version
echo

echo "Installing pinned dependencies for this user..."
"$PYTHON_BASE" -m ensurepip --upgrade >/dev/null 2>&1 || true
if ! "$PYTHON_BASE" "install/dependency_manager.py" install; then
    echo
    echo "Standard user install failed."
    echo "Newer macOS/Homebrew Python may require the externally-managed override."
    read -r -p "Retry with --break-system-packages --user? [y/N] " ANSWER
    case "$ANSWER" in
        y|Y|yes|YES)
            "$PYTHON_BASE" "install/dependency_manager.py" install --break-system-packages || finish 1
            ;;
        *)
            finish 1
            ;;
    esac
fi

echo
echo "Setup finished successfully."
echo "You can now use X5_Crop_Mac.command."
finish 0
