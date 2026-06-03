@echo off
setlocal

cd /d "%~dp0"

set "FORMAT=%~1"
set "STRIP=%~2"
set "MODE=%~3"
if "%STRIP%"=="" set "STRIP=full"
if "%MODE%"=="" set "MODE=normal"

if "%FORMAT%"=="" (
    echo Missing format.
    echo.
    pause
    exit /b 1
)

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

echo X5 Crop V2 %FORMAT% %STRIP% launcher
echo Folder: %cd%
echo.
echo This will process TIFF files in this folder.
echo Output: split_output
echo Existing output files will not be overwritten.
if /i "%MODE%"=="debug" (
    echo Debug analysis: split_output\_debug_analysis
    echo Dry run: no cropped TIFF files will be written.
)
echo.

if /i "%MODE%"=="debug" (
    %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%" --report --debug-analysis --dry-run
) else (
    %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%" --report
)
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
