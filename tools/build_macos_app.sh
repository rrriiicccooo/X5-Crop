#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."

APP_NAME="X5 Crop"
RELEASE_ZIP="X5_Crop_macOS_app.zip"
RELEASE_DMG="X5_Crop_macOS.dmg"

python3 -m venv .venv-build
source .venv-build/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements_X5_Crop_v1_1.txt

if command -v iconutil >/dev/null 2>&1; then
  iconutil -c icns resources/icon.iconset -o resources/icon.icns
else
  echo "warning: iconutil not found; app will build without custom .icns if PyInstaller cannot use resources/icon.icns"
fi

rm -rf build dist
python3 -m PyInstaller --clean --noconfirm packaging/X5_Crop_macos.spec

mkdir -p release
if [[ -d "dist/${APP_NAME}.app" ]]; then
  ditto -c -k --sequesterRsrc --keepParent "dist/${APP_NAME}.app" "release/${RELEASE_ZIP}"
  if command -v hdiutil >/dev/null 2>&1; then
    rm -f "release/${RELEASE_DMG}"
    hdiutil create -volname "${APP_NAME}" -srcfolder "dist/${APP_NAME}.app" -ov -format UDZO "release/${RELEASE_DMG}"
  fi
  echo "Build complete: dist/${APP_NAME}.app"
  echo "Release zip: release/${RELEASE_ZIP}"
  [[ -f "release/${RELEASE_DMG}" ]] && echo "Release dmg: release/${RELEASE_DMG}"
else
  echo "error: dist/${APP_NAME}.app was not created" >&2
  exit 1
fi

echo "Note: sign/notarize separately before distributing outside your own machine."
