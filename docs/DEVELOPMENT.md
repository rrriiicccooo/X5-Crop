# Development Setup

This document describes the local developer environment for X5 Crop.

## Supported Python

The project currently targets Python:

```text
>=3.13,<3.14
```

This is declared in `pyproject.toml`.

## Dependencies

Runtime dependencies are listed in:

```text
requirements_X5_Crop_v1_1.txt
pyproject.toml
```

Core packages:

- PySide6
- numpy
- tifffile
- imagecodecs
- Pillow

## macOS Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements_X5_Crop_v1_1.txt
python X5_Crop.py
```

If multiple Python versions are installed, use the Python 3.13 executable explicitly.

## Windows Setup

PowerShell:

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements_X5_Crop_v1_1.txt
python X5_Crop.py
```

If script execution is blocked:

```powershell
powershell -ExecutionPolicy Bypass
```

Then activate the venv again.

## App Entry Points

Simple launcher:

```text
X5_Crop.py
```

Main app module:

```text
x5crop/app.py
```

Core bridge:

```text
x5crop/core_bridge.py
```

Detection/export engine:

```text
x5crop/core/x5_split_engine.py
```

Original preserved script:

```text
X5_Split_v17.py
```

Native rewrite shell:

```text
native/
```

The native shell is a C++20 / Qt 6 project. It currently implements the
professional review workspace UI and is intended to grow into the higher
performance version of X5 Crop while the Python app remains available.

macOS native build:

```bash
chmod +x native/scripts/build_macos.sh
./native/scripts/build_macos.sh
open "native/build-$(uname -m)/X5 Crop.app"
```

Windows native build:

```powershell
powershell -ExecutionPolicy Bypass -File .\native\scripts\build_windows.ps1
```

## Local App Data

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

Cleanup scripts:

```text
tools/cleanup_x5_crop_macos.command
tools/cleanup_x5_crop_windows.ps1
```

## Environment Checks

```bash
python --version
python -m pip --version
git --version
git lfs version
gh auth status
```

On the primary macOS machine, Git and Git LFS should resolve to Homebrew paths:

```text
/opt/homebrew/bin/git
/opt/homebrew/bin/git-lfs
```

The macOS system Git at `/usr/bin/git` may still exist. Do not remove it.
