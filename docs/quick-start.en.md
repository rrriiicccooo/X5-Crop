# X5 Crop Quick Start

The latest public stable release is v4.2.8. V5 in this repository has not been
released. Download `X5-Crop-vX.X.zip` from GitHub Releases, not GitHub's
generated Source code archive.

## 1. Install

Extract the release archive and run the platform installer:

- macOS: `install/X5_Crop_Mac_install.command`
- Windows: `install/X5_Crop_win_install.bat`

Setup finds Python 3.12–3.14, reuses suitable dependencies, and installs only
missing items. Unknown or unsafe ownership stops before any change. Homebrew is
not required, and no private environment is created.

## 2. Add TIFFs And Launch

Put supported X5 scan TIFFs beside the launcher:

- macOS: double-click `X5_Crop_Mac.command`
- Windows: double-click `X5_Crop_win.bat`

Or use the command line:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

V5 accepts single-page 16-bit RGB TIFFs with supported lossless compression.
See the [English User Guide](user-guide.en.md) for the complete input contract.

## 3. Choose Format, Mode, And Count

- `full` uses the matched holder's complete filled layout and slot count.
- `partial --count N` is for a non-filling strip; `N` includes intermediate
  blank exposures.
- `135-dual` is full-only: 12 slots total, six per lane.
- `--layout auto` selects horizontal or vertical from the scan; either may be
  specified explicitly.
- `--debug-analysis` writes diagnostic JPGs and reports, but no official TIFFs
  or review copy.

The program does not infer count from filenames or pixels and does not suppress
blank slots. Partial receives no filled-layout centering authority even when its
count equals the complete count. An unresolved holder or placement enters
`needs_review` rather than producing guessed TIFFs.

To inspect detection before cropping, use two different fresh output paths:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --strip full --output /path/to/x5_crops
```

The normal run always detects from the source TIFF and never reuses the Debug
report. Each output path must not exist before the run.

## 4. Read The Result

Photos are written directly in the output root:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

`needs_review/` and `_debug_analysis/` are created only when needed. If the
target already exists, X5 Crop stops and never replaces or deletes it.

See the [English User Guide](user-guide.en.md) for full details.
