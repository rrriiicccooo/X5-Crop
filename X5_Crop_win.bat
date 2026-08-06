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
call :try_python py -3.14
if not defined PYTHON call :try_python py -3.13
if not defined PYTHON call :try_python py -3.12
if not defined PYTHON call :try_python python
if not defined PYTHON if defined LocalAppData (
    for /d %%P in ("%LocalAppData%\Programs\Python\Python*") do (
        if not defined PYTHON if exist "%%~fP\python.exe" call :try_python "%%~fP\python.exe"
    )
)
if not defined PYTHON (
    for %%P in (
        "%ProgramFiles%\Python314\python.exe"
        "%ProgramFiles%\Python313\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "%ProgramFiles(x86)%\Python314\python.exe"
        "%ProgramFiles(x86)%\Python313\python.exe"
        "%ProgramFiles(x86)%\Python312\python.exe"
    ) do (
        if not defined PYTHON if exist %%P call :try_python %%P
    )
)
if not defined PYTHON (
    echo A usable Python was not found.
    echo The launcher needs the pinned X5 Crop dependencies installed.
    echo Run install\X5_Crop_win_install.bat first, then try again.
    echo.
    echo Checked:
    echo %CHECKED_PYTHON%
    echo.
    pause
    exit /b 1
)

%PYTHON% "%SCRIPT%" --interactive
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
%CANDIDATE% -c "import cv2, imagecodecs, numpy, scipy, tifffile; from PIL import Image" >nul 2>nul
if not "%errorlevel%"=="0" exit /b 1
set "PYTHON=%CANDIDATE%"
exit /b 0
