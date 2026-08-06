@echo off
rem Release installer template; packaged under install\.
setlocal

cd /d "%~dp0.."

echo X5 Crop first-time setup for Windows
echo Folder: %cd%
echo.

if not exist "install\requirements.txt" (
    echo Missing setup file: install\requirements.txt
    echo.
    pause
    exit /b 1
)
if not exist "install\dependency_manager.py" (
    echo Missing setup file: install\dependency_manager.py
    echo.
    pause
    exit /b 1
)

set "PYTHON_BASE="
call :try_python py -3.14
if not defined PYTHON_BASE call :try_python py -3.13
if not defined PYTHON_BASE call :try_python py -3.12
if not defined PYTHON_BASE call :try_python python

if not defined PYTHON_BASE (
    echo Python 3.12-3.14 was not found.
    where winget >nul 2>nul
    if not errorlevel 1 (
        echo Installing Python 3.12 with winget...
        winget install -e --id Python.Python.3.12
        if errorlevel 1 (
            echo Python install failed. Install Python 3.12-3.14 from https://www.python.org/downloads/windows/
            echo.
            pause
            exit /b 1
        )
        call :try_python py -3.12
        if not defined PYTHON_BASE call :try_python python
    ) else (
        echo Install Python 3.12-3.14 from https://www.python.org/downloads/windows/ and run setup again.
        start "" "https://www.python.org/downloads/windows/"
        echo.
        pause
        exit /b 1
    )
)

if not defined PYTHON_BASE (
    echo Python was installed, but this terminal cannot find it yet.
    echo Close this window, open setup again, and try once more.
    echo.
    pause
    exit /b 1
)

echo Python:
%PYTHON_BASE% --version
echo.

echo Installing pinned dependencies for this user...
%PYTHON_BASE% -m ensurepip --upgrade >nul 2>nul
%PYTHON_BASE% "install\dependency_manager.py" install
if errorlevel 1 (
    echo Failed to install or verify dependencies.
    echo.
    pause
    exit /b 1
)

echo.
echo Setup finished successfully.
echo You can now use X5_Crop_win.bat.
echo.
pause
exit /b 0

:try_python
set "CANDIDATE=%*"
%CANDIDATE% -c "import struct, sys; raise SystemExit(not ((3, 12) <= sys.version_info[:2] < (3, 15) and struct.calcsize('P') == 8))" >nul 2>nul
if not "%errorlevel%"=="0" exit /b 1
set "PYTHON_BASE=%CANDIDATE%"
exit /b 0
