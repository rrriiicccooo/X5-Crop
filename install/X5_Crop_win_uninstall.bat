@echo off
setlocal

cd /d "%~dp0.."

echo X5 Crop uninstall helper for Windows
echo Folder: %cd%
echo.
echo This project is a portable script. Removing the folder removes the script,
echo launchers, reports, and output files in this folder.
echo.
echo This helper can also uninstall the user-level Python packages installed for X5 Crop:
echo numpy tifffile imagecodecs Pillow
echo.
echo Important: those packages may also be used by other Python scripts on this PC.
echo Python itself will NOT be removed by this helper.
echo.

set "PYTHON_BASE="
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_BASE=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_BASE=python"
    )
)

if "%PYTHON_BASE%"=="" (
    echo Python was not found. There are no Python packages to uninstall from here.
    echo You can delete this X5 Crop folder manually.
    echo.
    pause
    exit /b 0
)

echo Python:
%PYTHON_BASE% --version
echo.

set /p ANSWER=Uninstall X5 Crop Python packages from this user account? [y/N] 
if /I "%ANSWER%"=="y" goto uninstall_deps
if /I "%ANSWER%"=="yes" goto uninstall_deps
echo Skipped Python package uninstall.
goto cache_prompt

:uninstall_deps
%PYTHON_BASE% -m pip uninstall -y numpy tifffile imagecodecs Pillow

:cache_prompt
echo.
set /p CACHE_ANSWER=Purge pip download cache for this user? [y/N] 
if /I "%CACHE_ANSWER%"=="y" goto purge_cache
if /I "%CACHE_ANSWER%"=="yes" goto purge_cache
echo Skipped pip cache purge.
goto done

:purge_cache
%PYTHON_BASE% -m pip cache purge

:done
echo.
echo Uninstall helper finished.
echo To remove X5 Crop itself, delete this X5 Crop folder.
echo To keep your cropped TIFF output, move split_output\ somewhere safe before deleting the folder.
echo.
pause
exit /b 0
