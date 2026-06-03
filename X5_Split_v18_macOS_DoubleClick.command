#!/bin/bash

cd "$(dirname "$0")" || exit 1

SCRIPT="./X5_Split_v18.py"
REPO_SCRIPT="/Users/zhyoung/Pictures/Photography/X5-Crop/X5_Split_v18.py"
if [ ! -f "$SCRIPT" ] && [ -f "$REPO_SCRIPT" ]; then
    SCRIPT="$REPO_SCRIPT"
fi
if [ ! -f "$SCRIPT" ]; then
    echo "X5_Split_v18.py was not found in this folder."
    echo "Put X5_Split_v18.py in this folder, or update REPO_SCRIPT inside this launcher."
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

echo "X5 Split v18 double-click launcher"
echo "Folder: $(pwd)"
echo
echo "This will process TIFF files in this folder."
echo "Output: split_output"
echo "Existing output files will not be overwritten."
echo

$PYTHON "$SCRIPT" "." --report
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
