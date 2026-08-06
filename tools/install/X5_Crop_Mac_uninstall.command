#!/bin/bash
# Release uninstaller template; packaged under install/.

cd "$(dirname "$0")/.." || exit 1

finish() {
    EXITCODE="$1"
    echo
    read -r -p "Press Return to close..."
    exit "$EXITCODE"
}

echo "X5 Crop dependency removal for macOS"
echo

PYTHON_BASE=""
for CANDIDATE in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)"; do
    [ -n "$CANDIDATE" ] || continue
    if "$CANDIDATE" -c "import struct, sys; raise SystemExit(not ((3, 12) <= sys.version_info[:2] < (3, 15) and struct.calcsize('P') == 8))" >/dev/null 2>&1; then
        PYTHON_BASE="$CANDIDATE"
        break
    fi
done

if [ -z "$PYTHON_BASE" ]; then
    echo "Python 3.12-3.14 was not found. No package was removed."
    finish 1
fi

"$PYTHON_BASE" "install/dependency_manager.py" uninstall
finish $?
