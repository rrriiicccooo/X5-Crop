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

set "PYTHON="
set "CHECKED_PYTHON="
call :try_python py -3
if not defined PYTHON call :try_python python
if not defined PYTHON call :try_python python3
if not defined PYTHON if defined LocalAppData (
    for /d %%P in ("%LocalAppData%\Programs\Python\Python*") do (
        if not defined PYTHON if exist "%%~fP\python.exe" call :try_python "%%~fP\python.exe"
    )
)
if not defined PYTHON (
    for %%P in (
        "%ProgramFiles%\Python312\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles%\Python310\python.exe"
        "%ProgramFiles(x86)%\Python312\python.exe"
        "%ProgramFiles(x86)%\Python311\python.exe"
        "%ProgramFiles(x86)%\Python310\python.exe"
    ) do (
        if not defined PYTHON if exist %%P call :try_python %%P
    )
)
if not defined PYTHON (
    echo A usable Python was not found.
    echo The launcher needs Python with numpy, Pillow, and tifffile installed.
    echo Run install\X5_Crop_win_install.bat first, then try again.
    echo.
    echo Checked:
    echo %CHECKED_PYTHON%
    echo.
    pause
    exit /b 1
)

for /f "usebackq delims=" %%V in (`%PYTHON% "%SCRIPT%" --version 2^>nul`) do set "VERSION_LABEL=%%V"
if defined VERSION_LABEL (
    echo %VERSION_LABEL% launcher
) else (
    echo X5 Crop launcher
)
echo Folder: %cd%
echo.
echo This will process TIFF files in this folder.
echo Existing output files will not be overwritten.
echo.

echo choose film format:
echo   return or 135 = 135
echo   dual = 135 dual
echo   xpan = xpan
echo   half = half-frame
echo   645 = 120-645
echo   66 = 120-66
echo   67 = 120-67
echo.
:ask_format
set "FORMAT_INPUT=135"
set /p "FORMAT_INPUT=format: "
set "FORMAT_INPUT=%FORMAT_INPUT: =%"
if /i "%FORMAT_INPUT%"=="135" (
    set "FORMAT=135"
    set "COUNT=6"
) else if /i "%FORMAT_INPUT%"=="dual" (
    set "FORMAT=135-dual"
    set "COUNT=12"
) else if /i "%FORMAT_INPUT%"=="135dual" (
    set "FORMAT=135-dual"
    set "COUNT=12"
) else if /i "%FORMAT_INPUT%"=="135-dual" (
    set "FORMAT=135-dual"
    set "COUNT=12"
) else if /i "%FORMAT_INPUT%"=="xpan" (
    set "FORMAT=xpan"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="half" (
    set "FORMAT=half"
    set "COUNT=12"
) else if /i "%FORMAT_INPUT%"=="645" (
    set "FORMAT=120-645"
    set "COUNT=4"
) else if /i "%FORMAT_INPUT%"=="120645" (
    set "FORMAT=120-645"
    set "COUNT=4"
) else if /i "%FORMAT_INPUT%"=="120-645" (
    set "FORMAT=120-645"
    set "COUNT=4"
) else if /i "%FORMAT_INPUT%"=="66" (
    set "FORMAT=120-66"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="12066" (
    set "FORMAT=120-66"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="120-66" (
    set "FORMAT=120-66"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="67" (
    set "FORMAT=120-67"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="12067" (
    set "FORMAT=120-67"
    set "COUNT=3"
) else if /i "%FORMAT_INPUT%"=="120-67" (
    set "FORMAT=120-67"
    set "COUNT=3"
) else (
    echo unknown format: %FORMAT_INPUT%
    echo use return/135, dual, xpan, half, 645, 66, or 67.
    echo.
    goto ask_format
)

:ask_partial
set "PARTIAL_INPUT=no"
set /p "PARTIAL_INPUT=partial mode? [y/n, return=no]: "
set "PARTIAL_INPUT=%PARTIAL_INPUT: =%"
if /i "%PARTIAL_INPUT%"=="n" (
    set "STRIP=full"
) else if /i "%PARTIAL_INPUT%"=="no" (
    set "STRIP=full"
) else if /i "%PARTIAL_INPUT%"=="y" (
    set "STRIP=partial"
) else if /i "%PARTIAL_INPUT%"=="yes" (
    set "STRIP=partial"
) else (
    echo use yes/no, y/n, or press enter for no.
    goto ask_partial
)

:ask_debug
set "DEBUG_INPUT=no"
set /p "DEBUG_INPUT=debug analysis? [y/n, return=no]: "
set "DEBUG_INPUT=%DEBUG_INPUT: =%"
if /i "%DEBUG_INPUT%"=="n" (
    set "DEBUG=no"
) else if /i "%DEBUG_INPUT%"=="no" (
    set "DEBUG=no"
) else if /i "%DEBUG_INPUT%"=="y" (
    set "DEBUG=yes"
) else if /i "%DEBUG_INPUT%"=="yes" (
    set "DEBUG=yes"
) else (
    echo use yes/no, y/n, or press enter for no.
    goto ask_debug
)

echo.
if /i "%STRIP%"=="full" (
    echo strip mode: full
) else (
    echo strip mode: partial
    echo count: auto
)
if /i "%DEBUG%"=="yes" (
    echo debug analysis: enabled
    echo dry run: no cropped TIFF files will be written.
) else (
    echo debug analysis: off
)
echo.

if /i "%STRIP%"=="full" (
    if /i "%DEBUG%"=="yes" (
        %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%" --count "%COUNT%" --report --debug-analysis --dry-run
    ) else (
        %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%" --count "%COUNT%"
    )
) else (
    if /i "%DEBUG%"=="yes" (
        %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%" --report --debug-analysis --dry-run
    ) else (
        %PYTHON% "%SCRIPT%" "." --format "%FORMAT%" --strip "%STRIP%"
    )
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

:try_python
set "CANDIDATE=%*"
if not defined CANDIDATE exit /b 1
set "CHECKED_PYTHON=%CHECKED_PYTHON% %CANDIDATE%;"
%CANDIDATE% -c "import numpy, PIL, tifffile" >nul 2>nul
if not "%errorlevel%"=="0" exit /b 1
set "PYTHON=%CANDIDATE%"
exit /b 0
