@echo off
setlocal
call "%~dp0X5_Crop_verify.bat" platform %*
exit /b %ERRORLEVEL%
