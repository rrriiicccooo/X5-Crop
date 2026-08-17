# X5 Crop Quick Start

The latest public stable release is v4.2.8. V5 in this repository has not been
released. Download `X5-Crop-vX.X.zip` from GitHub Releases, not GitHub's
generated Source code archive.

## 1. Install

Extract the release archive and run the platform installer:

- macOS: `install/X5_Crop_Mac_install.command`
- Windows: `install/X5_Crop_win_install.bat`

Setup finds Python 3.12–3.14, reuses suitable dependencies, and installs only
missing items. Homebrew is not required, and no private environment is created.

## 2. Add TIFFs And Launch

Put supported X5 scan TIFFs beside the launcher:

- macOS: double-click `X5_Crop_Mac.command`
- Windows: double-click `X5_Crop_win.bat`

Or use the command line:

```bash
python3 X5_Crop.py /path/to/scans --format 135
```

Omitting `--count` confirms the matched holder's default slot count. Supply a
different count explicitly:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

Count includes intermediate blank exposures. X5 Crop never infers it from a
filename or picture content and never removes blank slots. `135-dual` defaults
to 12, six per lane. Any explicit different count enters review; lane counts
are never guessed.

`--layout auto` chooses horizontal or vertical from the scan, or either may be
specified. V5 accepts single-page 16-bit RGB TIFFs with supported lossless
compression. See the [English User Guide](user-guide.en.md) for the complete
input contract.

## 3. Inspect Debug Analysis First

Use two different fresh output paths when inspecting detection before a normal
crop:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --output /path/to/x5_crops
```

Debug Analysis writes diagnostic JPGs and reports, but no official TIFFs or
review copy. A normal run always detects again from the source TIFF and never
reuses the Debug report.

## 4. Read The Result

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

Approval is source-wide: if any slot is unsafe, the complete source enters
`needs_review`. If the target already exists, X5 Crop stops and never replaces
or deletes it. See the [English User Guide](user-guide.en.md) for full details.
