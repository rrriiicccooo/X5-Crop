# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for macOS .app bundle.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

ROOT = Path(__file__).resolve().parents[1]

hiddenimports = []
for pkg in ("imagecodecs", "tifffile", "PIL"):
    hiddenimports += collect_submodules(pkg)

binaries = []
binaries += collect_dynamic_libs("imagecodecs")

datas = []
for pkg in ("imagecodecs", "tifffile"):
    datas += collect_data_files(pkg)
datas += [
    (str(ROOT / "resources/icon_1024.png"), "resources"),
    (str(ROOT / "tools/cleanup_x5_crop_macos.command"), "tools"),
]


a = Analysis(
    [str(ROOT / "X5_Crop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="X5 Crop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="X5 Crop",
)
app = BUNDLE(
    coll,
    name="X5 Crop.app",
    icon=str(ROOT / "resources/icon.icns"),
    bundle_identifier="com.x5crop.X5-Crop",
    info_plist={
        "CFBundleName": "X5 Crop",
        "CFBundleDisplayName": "X5 Crop",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1.1.0",
        "NSHighResolutionCapable": True,
    },
)
