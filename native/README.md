# X5 Crop Native

This folder contains the native C++20 / Qt 6 rewrite shell for X5 Crop.

The current target is Phase 1 from `docs/UI_REDESIGN_CAPTURE_ONE_LIGHTROOM.md`:

```text
existing Python engine kept intact
+ native professional review workspace
+ cross-platform CMake project
+ future CropPlan and engine bridge foundation
```

The Python app remains in the repository as the working reference implementation.

## Requirements

- CMake 3.24 or newer
- C++20 compiler
- Qt 6 with Widgets

Recommended platforms:

- Windows x64
- macOS Apple Silicon arm64
- macOS Intel x86_64
- macOS Universal 2 app bundle

## Configure And Build

macOS:

```bash
cmake -S native -B native/build-arm64 -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build native/build-arm64 --config Release
open "native/build-arm64/X5 Crop.app"
```

Windows PowerShell:

```powershell
cmake -S native -B native\build-windows -DCMAKE_BUILD_TYPE=Release
cmake --build native\build-windows --config Release
.\native\build-windows\Release\"X5 Crop.exe"
```

## macOS Architecture

The default macOS build uses the current machine architecture. This works with
Homebrew Qt, which is usually installed as a single architecture package.

To request a Universal 2 app bundle, configure with:

```bash
cmake -S native -B native/build-universal -DX5CROP_MACOS_UNIVERSAL=ON
```

Universal builds require Qt and future image-processing dependencies to be
available for both `arm64` and `x86_64`. If a dependency is not universal yet,
configure a single architecture explicitly:

```bash
cmake -S native -B native/build-arm64 -DCMAKE_OSX_ARCHITECTURES=arm64
cmake -S native -B native/build-x64 -DCMAKE_OSX_ARCHITECTURES=x86_64
```

## Current Scope

Implemented:

- three-panel dark review workspace
- top mode/action bar
- left library and batch queue
- center review canvas mock with crop overlays
- right inspector tabs
- bottom filmstrip with status badges
- TIFF file/folder import list
- placeholder analyze/approve/export state flow

Not implemented yet:

- Python engine bridge
- real TIFF preview rendering
- persistent CropPlan JSON
- manual crop line editing
- final TIFF export from approved plans
