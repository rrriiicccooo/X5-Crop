# X5 Crop Quick Start

The latest public stable release is v4.2.8. V5 in this repository has not been
released. Download `X5-Crop-vX.X.zip` from GitHub Releases, not GitHub's
generated Source code archive.

## 1. Install

Extract the release archive and run the platform installer:

- macOS: `install/X5_Crop_Mac_install.command`
- Windows: `install/X5_Crop_win_install.bat`

Setup finds Python 3.12–3.14 and reuses dependencies that already satisfy the
version contract. Only missing items are installed; unknown or unsafe ownership
stops before any change. Homebrew is not required, and no private environment is
created.

## 2. Add TIFFs And Launch

Put supported X5 scan TIFFs beside the launcher:

- macOS: double-click `X5_Crop_Mac.command`
- Windows: double-click `X5_Crop_win.bat`

Or use the command line:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

V5 accepts single-page, unsigned 16-bit, three-channel RGB TIFFs with contiguous
planar layout and a supported lossless compression. Other structures fail
safely instead of being guessed.

## 3. Choose Format, Mode, And Count

- `full` confirms that the strip uses the matched holder's complete filled
  layout; the program then uses that holder's complete slot count.
- `partial --count N` confirms a non-filling strip. `N` includes intermediate
  blank exposures and may satisfy `1 <= N <= full_count`. Full rejects
  `--count`.
- `135-dual` is full-only: 12 slots total, six per lane.
- `--layout auto` selects horizontal or vertical from the scan; either may be
  specified explicitly.
- `--debug-analysis` writes only Debug Analysis JPGs and report files—never
  official TIFFs or a review copy. It is off by default.

The program does not infer count from filenames or pixels and does not suppress
blank slots. Partial receives no filled-layout centering authority even when its
count equals `full_count`.
Partial without a count, a non-positive count, full with a count, or a matched
partial count that exceeds the complete count fails before detection with
exit code `2`. Interactive multi-file use lists all holder/count conflicts and
returns to the mode/count step. An unresolved holder or physical
placement enters `needs_review` rather than producing guessed TIFFs.

To inspect detection before cropping, use two different fresh output paths:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --strip full --output /path/to/x5_crops
```

The normal run always detects from the source TIFF; it does not reuse the Debug
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

`needs_review/` and `_debug_analysis/` are created only
when needed. A run writes a same-parent temporary directory and publishes it once
complete. If the target already exists, X5 Crop stops and never replaces or
deletes it. Disk-space, write, and rename failures clean only the unpublished
temporary directory and report the actual error.

See the [English User Guide](user-guide.en.md) for full details.
