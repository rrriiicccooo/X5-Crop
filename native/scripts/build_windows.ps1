$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

$BuildDir = "native\build-windows"

cmake -S native -B $BuildDir -DCMAKE_BUILD_TYPE=Release
cmake --build $BuildDir --config Release

Write-Host "Built $BuildDir\Release\X5 Crop.exe" -ForegroundColor Green
