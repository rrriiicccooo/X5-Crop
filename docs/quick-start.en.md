# X5 Crop Quick Start

The current stable release is **v4.2.8**. V4.9 in this repository is still
under development and validation.

## 1. Download And Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive. Unzip it and run once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer prepares `numpy`, `tifffile`, `imagecodecs`, and `Pillow`.

## 2. Add TIFFs And Launch

Keep the TIFFs and launch files in one folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

- macOS: double-click `X5_Crop_Mac.command`
- Windows: double-click `X5_Crop_win.bat`

If macOS blocks double-click launch, run this in that folder:

```bash
/bin/bash X5_Crop_Mac.command
```

## 3. Choose Format, Mode, And Count

Supported formats are `135`, `135-dual`, `half`, `xpan`, `120-645`,
`120-66`, and `120-67`.

- `full`: use the format's fixed holder count.
- `partial` with an integer: strictly use that output-slot count.
- `partial` with `auto`: write every valid slot for the matched holder and
  format; it does not guess the true photo count.
- `135-dual` supports `full` only.

Examples:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

Defaults are `--layout auto` and `--jobs 2`. For every option:

```bash
python3 X5_Crop.py --help
```

## 4. Read The Result

- `approved_auto`: official photo TIFFs are written.
- `needs_review`: no official photo TIFF is written; the source is copied to
  `needs_review/` by default.
- `--no-copy-review-files`: disable the review copy.
- `--diagnostics`: write the report and Debug Analysis only; no photo TIFF or
  review copy is created.

The default output folder is `x5_crop_output/`. With `--report`, it also
contains:

```text
x5_crop_report.jsonl
x5_crop_summary.csv
x5_crop_run_manifest.jsonl
```

## 5. TIFF Safety

The source TIFF is never modified. Every approved output is sampled from the
source and read back after writing to check pixels, bit depth, channels, ICC,
resolution, metadata, and supported lossless compression. Read, write, or
read-back failures remain errors; they are never disguised as `needs_review`.

## 6. Remove

Delete the X5 Crop folder. Python packages may be shared with other programs,
so the release does not include a bulk dependency uninstaller.
