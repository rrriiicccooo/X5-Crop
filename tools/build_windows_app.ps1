$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$AppName = "X5 Crop"
$ReleaseZip = "X5_Crop_Windows_app.zip"

py -3 -m venv .venv-build
. .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements_X5_Crop_v1_1.txt

if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
python -m PyInstaller --clean --noconfirm packaging\X5_Crop_windows.spec

if (!(Test-Path release)) { New-Item -ItemType Directory release | Out-Null }
$distPath = Join-Path "dist" $AppName
if (Test-Path $distPath) {
    $zipPath = Join-Path "release" $ReleaseZip
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path $distPath -DestinationPath $zipPath -Force
    Write-Host "Build complete: dist\$AppName\X5 Crop.exe" -ForegroundColor Green
    Write-Host "Release zip: release\$ReleaseZip" -ForegroundColor Green
} else {
    throw "dist\$AppName was not created"
}
