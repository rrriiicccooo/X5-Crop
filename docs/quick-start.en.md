# X5 Crop V5 Quick Start (Development Preview)

This guide applies only to the unreleased V5 source on repository `main`. The
latest public stable release remains v4.2.8. Regular users should download its
release package and follow the bundled v4.2.8 documentation; its command line
is different from this V5 preview.

## 1. Install

Obtain the complete repository checkout, then run its platform installer:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a
future V5 release package.

Setup finds Python 3.12–3.14, reuses suitable dependencies, and installs only
missing items. Homebrew is not required, and no private environment is created.

## 2. Add TIFFs And Launch

Put supported X5 scan TIFFs beside the V5 launcher:

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

Interactive mode asks for count for every format. Press Return to confirm the
matched-holder default. `135-dual` accepts another typed number consistently,
but every value other than 12 safely enters review.

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
or deletes it. Deskew is optional cleanup after the safety decision; when its
measurement is unavailable, safe photos are still written with their original
tilt. Rotated envelopes may have black corners. See the
[English User Guide](user-guide.en.md) for full details.
