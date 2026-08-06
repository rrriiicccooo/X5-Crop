@echo off
rem Release uninstaller template; packaged under install\.
setlocal

cd /d "%~dp0.."

echo X5 Crop dependency removal for Windows
echo.

set "PYTHON_BASE="
call :try_python py -3.14
if not defined PYTHON_BASE call :try_python py -3.13
if not defined PYTHON_BASE call :try_python py -3.12
if not defined PYTHON_BASE call :try_python python

if not defined PYTHON_BASE (
    echo Python 3.12-3.14 was not found. No package was removed.
    echo.
    pause
    exit /b 1
)

%PYTHON_BASE% "install\dependency_manager.py" uninstall
set "EXITCODE=%errorlevel%"
echo.
pause
exit /b %EXITCODE%

:try_python
set "CANDIDATE=%*"
%CANDIDATE% -c "import struct, sys; raise SystemExit(not ((3, 12) <= sys.version_info[:2] < (3, 15) and struct.calcsize('P') == 8))" >nul 2>nul
if not "%errorlevel%"=="0" exit /b 1
set "PYTHON_BASE=%CANDIDATE%"
exit /b 0
