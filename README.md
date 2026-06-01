# X5 Crop

X5 Crop is a PySide6 desktop app for splitting TIFF film-strip scans from Hasselblad/Imacon X5 style long scans into individual TIFF frames.

The project keeps the original standalone script as an archive while continuing development in the packaged app:

```text
X5_Split_v17.py
README_X5_Split_v17.md
x5crop/
```

The current app is intentionally more than a thin GUI wrapper. The product direction is a review-oriented workflow for difficult scans:

```text
analyze quickly
score confidence
review uncertain files
manually correct crop plans
export approved TIFFs
```

Start here when moving between computers or Codex sessions:

- [Codex sync guide](docs/CODEX_SYNC.md)
- [Development setup](docs/DEVELOPMENT.md)
- [Testing guide](docs/TESTING.md)
- [Release and packaging guide](docs/RELEASE_BUILD.md)
- [Project context and roadmap](docs/PROJECT_CONTEXT.md)

The earlier roadmap from the ChatGPT web discussion is preserved in [PROJECT_P_ROADMAP.md](PROJECT_P_ROADMAP.md).

## Quick Start

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

## Build Apps

PyInstaller is not a cross-compiler. Build macOS on macOS and Windows on Windows, or use GitHub Actions.

macOS:

```bash
chmod +x tools/build_macos_app.sh
./tools/build_macos_app.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_windows_app.ps1
```

GitHub Actions workflow:

```text
.github/workflows/build_x5_crop.yml
```

## Repository Hygiene

The app source, packaging scripts, docs, and original v17 script belong in Git.

Large local test TIFFs, generated debug images, downloaded app artifacts, virtual environments, build outputs, and `__pycache__` folders are local working files unless explicitly promoted into tracked fixtures.

