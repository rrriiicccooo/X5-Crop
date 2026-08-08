@echo off
setlocal
where bash >nul 2>nul
if errorlevel 1 (
  echo Git Bash is required to run the X5 Crop repository verifier. 1>&2
  exit /b 2
)
bash "%~dp0..\verify" %*
exit /b %ERRORLEVEL%
