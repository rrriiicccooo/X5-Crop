#!/bin/bash

cd "$(dirname "$0")" || exit 1

SCRIPT="./X5_Split_v18.py"
if [ ! -f "$SCRIPT" ]; then
    echo "X5_Split_v18.py was not found in this folder."
    echo "Put this launcher in the same folder as X5_Split_v18.py and your TIFF scans."
    echo
    read -r -p "Press Return to close..."
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Python was not found."
    echo "Install Python 3, then install dependencies:"
    echo "  python3 -m pip install -U numpy tifffile imagecodecs Pillow"
    echo
    read -r -p "Press Return to close..."
    exit 1
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
echo
read -r -p "Press Return to close..."
exit "$EXITCODE"
