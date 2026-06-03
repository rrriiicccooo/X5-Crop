@echo off
setlocal

cd /d "%~dp0"

set "SCRIPT=%~dp0X5_Crop.py"
if not exist "%SCRIPT%" (
    echo X5_Crop.py was not found in this folder.
    echo Put this launcher in the same folder as X5_Crop.py and your TIFF scans.
    echo.
    pause
    exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo Python was not found.
        echo Install Python 3, then install dependencies:
        echo   py -3 -m pip install -U numpy tifffile imagecodecs Pillow
        echo.
        pause
        exit /b 1
    )
)

echo X5 Crop V2 DEBUG ANALYSIS launcher
echo Folder: %cd%
echo.
echo This will analyze TIFF files in this folder and write one adaptive debug-analysis JPG.
echo Output: split_output
echo Debug analysis: split_output\_debug_analysis
echo Dry run: no cropped TIFF files will be written.
echo.

%PYTHON% "%SCRIPT%" "." --report --debug-analysis --dry-run
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" (
    echo Finished with errors. Read the messages above.
) else (
    echo Finished successfully.
)
echo.
pause
exit /b %EXITCODE%
