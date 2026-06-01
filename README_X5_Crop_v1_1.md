# X5 Crop v1.1 Release Builder

X5 Crop is a PySide6 desktop app for splitting horizontal 135 TIFF film-strip scans into individual TIFF files.

This package contains the full source code plus macOS and Windows packaging scripts. The app uses the current X5 Split v17 core logic: deskew auto, analysis-enhance auto with fast skip, outer-refine, grid-fit, frame-size-fit, TIFF metadata validation, and default 10 px bleed.

## Important packaging note

PyInstaller is not a cross-compiler. Build the macOS app on macOS, and build the Windows app on Windows.

The package includes a GitHub Actions workflow that can build both platform artifacts automatically if you push this folder to a GitHub repository and run the workflow.

## Output artifacts

After a successful local build:

macOS:

```text
dist/X5 Crop.app
release/X5_Crop_macOS_app.zip
release/X5_Crop_macOS.dmg
```

Windows:

```text
dist/X5 Crop/X5 Crop.exe
release/X5_Crop_Windows_app.zip
```

## Runtime data locations

X5 Crop follows traditional desktop app behavior.

macOS:

```text
~/Library/Application Support/X5 Crop
~/Library/Caches/X5 Crop
~/Library/Logs/X5 Crop
```

Windows:

```text
%APPDATA%\X5 Crop
%LOCALAPPDATA%\X5 Crop\Cache
%LOCALAPPDATA%\X5 Crop\Logs
```

The included cleanup scripts remove these app-generated residual folders after uninstalling the app. They do not delete your output TIFFs in `split_output`.

## macOS build

From this project folder on macOS:

```bash
chmod +x tools/build_macos_app.sh
./tools/build_macos_app.sh
```

The script will:

1. Create `.venv-build`.
2. Install requirements.
3. Generate `resources/icon.icns` from the iconset.
4. Run PyInstaller with `packaging/X5_Crop_macos.spec`.
5. Create `release/X5_Crop_macOS_app.zip`.
6. Create `release/X5_Crop_macOS.dmg` when `hdiutil` is available.

Run the app locally:

```bash
open "dist/X5 Crop.app"
```

For distribution outside your own machine, apply your own Apple code-signing and notarization workflow.

## Windows build

From this project folder in Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows_app.ps1
```

The script will:

1. Create `.venv-build`.
2. Install requirements.
3. Run PyInstaller with `packaging\X5_Crop_windows.spec`.
4. Create `release\X5_Crop_Windows_app.zip`.

Run the app locally:

```powershell
.\dist\"X5 Crop"\"X5 Crop.exe"
```

## GitHub Actions build

This package includes:

```text
.github/workflows/build_x5_crop.yml
```

To use it:

1. Create a GitHub repository.
2. Upload this project folder contents.
3. Open the Actions tab.
4. Run **Build X5 Crop Desktop Apps** manually.
5. Download the uploaded artifacts:
   - `X5_Crop_macOS`
   - `X5_Crop_Windows`

## Source run without packaging

macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_X5_Crop_v1_1.txt
python X5_Crop.py
```

Windows PowerShell:

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements_X5_Crop_v1_1.txt
python X5_Crop.py
```

## Cleanup after uninstall

Remove the app first, then run the matching cleanup script.

macOS:

```bash
chmod +x tools/cleanup_x5_crop_macos.command
./tools/cleanup_x5_crop_macos.command
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\cleanup_x5_crop_windows.ps1
```

The cleanup scripts remove app-generated settings, cache, logs, temporary files, and optional `.x5crop` project cache. They intentionally do not delete `split_output` TIFF files.

## Main UI features in v1.1

- Select one TIFF or a folder of TIFF files.
- Choose output folder.
- Analyze / Dry Run.
- Export TIFFs.
- Preview debug image and analysis image.
- Inspect report summary.
- Open output folder.
- Open app data folder.
- Configure count, bleed, deskew, analysis enhancement, outer-refine, grid-fit, frame-size-fit, preset, overwrite, and equal split.

## Notes

- The packaged app still follows the current core design: detection analysis may use enhanced images, but output TIFFs are generated from the processing image data and written with TIFF validation.
- Default bleed is 10 px on all sides.
- Default deskew is auto.
- Default analysis-enhance is auto with fast skip.
