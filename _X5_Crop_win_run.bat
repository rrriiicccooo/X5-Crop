@echo off
setlocal

cd /d "%~dp0"

set "STRIP=%~1"
set "MODE=%~2"
if "%STRIP%"=="" set "STRIP=full"
if "%MODE%"=="" set "MODE=normal"

set "SCRIPT=%~dp0X5_Crop.py"
if not exist "%SCRIPT%" (
    echo X5_Crop.py was not found in this folder.
    echo Put this launcher in the same folder as X5_Crop.py and your TIFF scans.
    echo.
    pause
    exit /b 1
)

if exist "%~dp0.venv-x5crop\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv-x5crop\Scripts\python.exe"
) else (
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo Python was not found.
        echo Run X5_Crop_win_install.bat first, then try again.
        echo.
        pause
        exit /b 1
    )
)
)

echo X5 Crop V2 %STRIP% launcher
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

echo Choose film format:
echo   [Enter] or 135 = 135
echo   xpan = XPAN
echo   half = half-frame
echo   645 = 120-645
echo   66 = 120-66
echo   67 = 120-67
echo.
set /p "FORMAT_INPUT=Format [135]: "
set "FORMAT_INPUT=%FORMAT_INPUT: =%"
if "%FORMAT_INPUT%"=="" set "FORMAT_INPUT=135"
if /i "%FORMAT_INPUT%"=="135" (
    set "FORMAT=135"
) else if /i "%FORMAT_INPUT%"=="xpan" (
    set "FORMAT=xpan"
) else if /i "%FORMAT_INPUT%"=="half" (
    set "FORMAT=half"
) else if /i "%FORMAT_INPUT%"=="645" (
    set "FORMAT=120-645"
) else if /i "%FORMAT_INPUT%"=="120645" (
    set "FORMAT=120-645"
) else if /i "%FORMAT_INPUT%"=="120-645" (
    set "FORMAT=120-645"
) else if /i "%FORMAT_INPUT%"=="66" (
    set "FORMAT=120-66"
) else if /i "%FORMAT_INPUT%"=="12066" (
    set "FORMAT=120-66"
) else if /i "%FORMAT_INPUT%"=="120-66" (
    set "FORMAT=120-66"
) else if /i "%FORMAT_INPUT%"=="67" (
    set "FORMAT=120-67"
) else if /i "%FORMAT_INPUT%"=="12067" (
    set "FORMAT=120-67"
) else if /i "%FORMAT_INPUT%"=="120-67" (
    set "FORMAT=120-67"
) else (
    echo Unknown format: %FORMAT_INPUT%
    echo Use Enter/135, xpan, half, 645, 66, or 67.
    echo.
    pause
    exit /b 1
)
echo Selected format: %FORMAT%
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
