@echo off
setlocal

cd /d "%~dp0"

echo X5 Crop first-time setup for Windows
echo Folder: %cd%
echo.

set "PYTHON_BASE="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_BASE=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_BASE=python"
    )
)

if "%PYTHON_BASE%"=="" (
    echo Python 3 was not found.
    where winget >nul 2>nul
    if %errorlevel%==0 (
        echo Installing Python 3.12 with winget...
        winget install -e --id Python.Python.3.12
        if errorlevel 1 (
            echo Python install failed. Install Python 3 manually from https://www.python.org/downloads/windows/
            echo.
            pause
            exit /b 1
        )
        where py >nul 2>nul
        if %errorlevel%==0 (
            set "PYTHON_BASE=py -3"
        ) else (
            where python >nul 2>nul
            if %errorlevel%==0 (
                set "PYTHON_BASE=python"
            )
        )
    ) else (
        echo Open https://www.python.org/downloads/windows/ and install Python 3, then run this setup again.
        start "" "https://www.python.org/downloads/windows/"
        echo.
        pause
        exit /b 1
    )
)

if "%PYTHON_BASE%"=="" (
    echo Python was installed, but this terminal cannot find it yet.
    echo Close this window, open the setup launcher again, and try once more.
    echo.
    pause
    exit /b 1
)

echo Python:
%PYTHON_BASE% --version
echo.

if not exist ".venv-x5crop" (
    echo Creating local environment: .venv-x5crop
    %PYTHON_BASE% -m venv .venv-x5crop
    if errorlevel 1 (
        echo Could not create the local Python environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Using existing local environment: .venv-x5crop
)

set "PYTHON=%~dp0.venv-x5crop\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo Local Python was not created correctly.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    echo.
    pause
    exit /b 1
)
"%PYTHON%" -m pip install -U numpy tifffile imagecodecs Pillow
if errorlevel 1 (
    echo Failed to install dependencies.
    echo.
    pause
    exit /b 1
)

echo.
echo Verifying dependencies...
"%PYTHON%" -c "import numpy, tifffile, imagecodecs; from PIL import Image; print('Dependencies OK')"
if errorlevel 1 (
    echo Dependency verification failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Setup finished successfully.
echo You can now use X5_Crop_win.bat or X5_Crop_win_debug.bat.
echo.
pause
exit /b 0
