# Release And Packaging Guide

X5 Crop uses PyInstaller for desktop packaging.

PyInstaller is not a cross-compiler:

- build macOS apps on macOS
- build Windows apps on Windows
- or use GitHub Actions for both

## GitHub Actions

Workflow:

```text
.github/workflows/build_x5_crop.yml
```

The workflow runs on:

- pushes to `main`
- tags matching `x5-crop-v*`
- manual `workflow_dispatch`

Artifacts:

```text
X5_Crop_macOS
X5_Crop_Windows
```

Expected files:

```text
release/X5_Crop_macOS_app.zip
release/X5_Crop_macOS.dmg
release/X5_Crop_Windows_app.zip
```

## Local macOS Build

```bash
chmod +x tools/build_macos_app.sh
./tools/build_macos_app.sh
```

Outputs:

```text
dist/X5 Crop.app
release/X5_Crop_macOS_app.zip
release/X5_Crop_macOS.dmg
```

Local run:

```bash
open "dist/X5 Crop.app"
```

For distribution outside your own machine, code signing and notarization are still separate work.

## Local Windows Build

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows_app.ps1
```

Outputs:

```text
dist\X5 Crop\X5 Crop.exe
release\X5_Crop_Windows_app.zip
```

Local run:

```powershell
.\dist\"X5 Crop"\"X5 Crop.exe"
```

## Downloaded Artifacts

Downloaded GitHub Actions artifacts may be stored locally under:

```text
downloaded_apps/
```

This folder is not the source of truth. It is a convenience cache for local testing.

Do not commit downloaded artifacts unless the user explicitly asks for a release archive to be stored in the repository.

## Release Checklist

Before tagging or sharing an app:

1. Confirm the source branch is clean except expected local-only files.
2. Confirm `X5_Split_v17.py` is still present.
3. Run from source once.
4. Build app artifact locally or with GitHub Actions.
5. Launch the packaged app.
6. Run one normal TIFF through Analyze / Dry Run.
7. Run one difficult TIFF through Analyze / Dry Run.
8. Export a small output set.
9. Confirm the artifact names match this document.
10. Add release notes if behavior changed.

