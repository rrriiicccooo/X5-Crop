# X5 Crop v1.1 Release Builder

Changes from v1 MVP:

- Added platform-specific PyInstaller specs for macOS and Windows.
- Added app icon resources.
- Added macOS build script that creates `.app`, `.app.zip`, and optional `.dmg`.
- Added Windows build script that creates a runnable app folder and release zip.
- Added GitHub Actions workflow for building both macOS and Windows artifacts.
- Cleaned pycache from the release source package.
- Updated requirements for Python 3.14 and current PySide6 / PyInstaller packaging.
