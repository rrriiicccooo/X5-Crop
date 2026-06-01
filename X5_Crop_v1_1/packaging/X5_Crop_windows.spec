# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Windows onedir build.
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

hiddenimports = []
for pkg in ("imagecodecs", "tifffile", "PIL"):
    hiddenimports += collect_submodules(pkg)

binaries = []
binaries += collect_dynamic_libs("imagecodecs")

datas = []
for pkg in ("imagecodecs", "tifffile"):
    datas += collect_data_files(pkg)
datas += [
    ("resources/icon_1024.png", "resources"),
    ("resources/icon.ico", "resources"),
    ("tools/cleanup_x5_crop_windows.ps1", "tools"),
]


a = Analysis(
    ["X5_Crop.py"],
    pathex=[],
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
    icon="resources/icon.ico",
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
