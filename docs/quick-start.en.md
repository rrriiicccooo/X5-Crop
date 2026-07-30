# X5 Crop Quick Start

This page covers the current V4.9 source-core safety baseline. The product aims
to crop conservatively from a user-supplied format without cutting real photo
content. Full uses its fixed count, while partial is intended to support either
an explicit or automatic count. The goal is not to uniquely measure photo
boundaries. See `README_English.txt` for the full guide.

## 1. Download And Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases), unzip it,
then run:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer prepares `numpy`, `tifffile`, `imagecodecs`, and `Pillow`.

## 2. Add TIFFs And Launch

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

## 3. Choose Format

Supported inputs are `135`, `135-dual`, `half`, `xpan`, `645`, `66`, and `67`.
Full means the complete design count; a partial count still describes complete
design slots. Current V4.9 still requires an explicit partial count; automatic
count belongs to the not-yet-implemented Grid/output contract.

## 4. Current Result

The current development build has no approved independent Frame Grid phase
authority. Every TIFF therefore:

- completes scan-canvas, independent-axis scale, and positive-content audit;
- returns `needs_review / frame_grid_authority_unavailable`;
- exports no frame TIFF such as `*_01.tif`;
- may write a review copy, current report, and Debug Analysis.

This is not a fallback. The current source core has no active Grid proposal
builder, so content, design width, or an old detector cannot directly create
frames. This does not mean that future auto-approval must uniquely prove the
true boundary.

Examples:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip full --diagnostics
```

The default is `--jobs 2`. Old pixel-bleed, `--export-review`, and `--dry-run`
options have been removed.

## 5. Output

```text
x5_crop_output/
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

Source TIFFs are never modified. The current runtime does not claim automatic
cropping, physical deskew accuracy, or certified real-output performance.

## 6. Uninstall

Delete the X5 Crop folder to remove the program. To remove user-level
dependencies:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
