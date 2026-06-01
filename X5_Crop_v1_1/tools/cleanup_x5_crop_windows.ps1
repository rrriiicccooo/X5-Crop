# X5 Crop residual cleanup for Windows
# Run after uninstalling X5 Crop. This removes app-generated configuration,
# cache, logs, temporary files, shortcuts, and optional registry keys used by
# traditional Windows app packaging.

$ErrorActionPreference = "Continue"

Write-Host "X5 Crop residual cleanup" -ForegroundColor Cyan
Write-Host "This removes X5 Crop app data/cache/logs. It does NOT delete split_output TIFF files." -ForegroundColor Yellow
$answer = Read-Host "Continue? Type YES to proceed"
if ($answer -ne "YES") {
    Write-Host "Canceled."
    exit 0
}

$paths = @()
if ($env:APPDATA)      { $paths += Join-Path $env:APPDATA "X5 Crop" }
if ($env:LOCALAPPDATA) { $paths += Join-Path $env:LOCALAPPDATA "X5 Crop" }
if ($env:TEMP)         { $paths += Join-Path $env:TEMP "X5 Crop" }
if ($env:APPDATA)      { $paths += Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\X5 Crop" }
if ($env:USERPROFILE)  { $paths += Join-Path $env:USERPROFILE "Desktop\X5 Crop.lnk" }
if ($env:PUBLIC)       { $paths += Join-Path $env:PUBLIC "Desktop\X5 Crop.lnk" }

foreach ($path in $paths) {
    if (Test-Path $path) {
        Write-Host "Removing $path"
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Continue
    }
}

$registryKeys = @(
    "HKCU:\Software\X5 Crop",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\X5 Crop"
)
foreach ($key in $registryKeys) {
    if (Test-Path $key) {
        Write-Host "Removing registry key $key"
        Remove-Item -LiteralPath $key -Recurse -Force -ErrorAction Continue
    }
}

Write-Host ""
Write-Host "Optional project cache cleanup:" -ForegroundColor Cyan
Write-Host "X5 Crop may create .x5crop folders inside project folders if project caching is enabled."
$project = Read-Host "Enter a project folder to remove its .x5crop cache, or press Enter to skip"
if ($project) {
    $cache = Join-Path $project ".x5crop"
    if (Test-Path $cache) {
        Write-Host "Removing $cache"
        Remove-Item -LiteralPath $cache -Recurse -Force -ErrorAction Continue
    } else {
        Write-Host "No .x5crop folder found at $cache"
    }
}

Write-Host "Cleanup complete." -ForegroundColor Green
