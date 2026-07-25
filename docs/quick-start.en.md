# X5 Crop Quick Start

This page covers the first Release run only. See `README_English.txt` for the
complete guide.

## 1. Download

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

## 2. Install

After unzipping, run:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

If macOS blocks double-click launch, run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

## 3. Add TIFFs And Launch

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

The launcher, `X5_Crop.py`, and TIFF files must stay in the same folder.

## 4. Choose Format

| Input | Format | Full count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

## 5. Full, Partial, And Debug

- Film fills the holder: `partial mode = no`.
- Head, tail, short, or unfilled scan: `partial mode = yes`.
- In partial mode, press Return or enter `auto` for automatic count.
- `debug analysis = yes` writes JPG/report artifacts without exporting final crops.

Detection auto-calibrates a known canvas, joins the real shared photo edges before
frame solving, and reuses that evidence for mandatory deskew and the shared short
axis. Unknown or insufficient evidence remains in REVIEW.

## 6. Output

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  needs_review/
  _debug_analysis/
```

Only safely resolved results are exported. `needs_review/` contains source-TIFF
copies; originals are never modified. Output preserves bit depth, channels, ICC,
resolution metadata, and other metadata.

## 7. Uninstall

Delete the X5 Crop folder to remove the program. To remove user-level dependencies:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
