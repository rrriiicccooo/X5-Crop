# X5 Crop Quick Start

This page covers the current V4.9 development build. After you choose the film
format, X5 Crop makes conservative automatic crops that prioritize retaining
all real photo content. Outputs may keep extra pixels, overlap, or include a
small part of a neighboring photo; tight boundary replication is not the goal.
The current stable release remains **v4.2.8**.

## 1. Download And Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive. Unzip it and run the installer once:

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

If macOS blocks double-click launch, run this in that folder:

```bash
/bin/bash X5_Crop_Mac.command
```

## 3. Choose Format, Mode, And Count

Supported inputs are `135`, `135-dual`, `half`, `xpan`, `645`, `66`, and `67`.

- `full`: count is fixed to the format default. An explicit count is accepted
  only when it equals that default.
- `partial`: an integer is an authoritative explicit count. Pressing Return,
  entering `auto`, or omitting CLI `--count` selects bounded automatic count.
- Auto searches only `1..default_count`, further limited by the uniquely
  matched holder capacity. It never guesses format or reads count from a
  filename.
- `135-dual` currently supports full only. Its 12 outputs use top lane then
  bottom lane, with left-to-right local order in each lane.

Examples:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 135 --strip partial --count auto --report
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

The default is `--jobs 2`. For all options:

```bash
python3 X5_Crop.py --help
```

## 4. Result And Output

`approved_auto` means the protected output satisfies the bounded safety
contract. It does not claim that every photo edge or separator was uniquely
proven. An approved run writes:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  ...
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

`needs_review` is reserved for a concrete, unabsorbed count, ordinal, slot
ownership, known-content containment, source/lane authority, or output-geometry
risk. By default, the source TIFF is copied to `needs_review/`; use
`--no-copy-review-files` to disable that copy.

`--diagnostics` is read-only: it preserves the same detection and DecisionGate
result and writes the report plus Debug Analysis, but writes no frame TIFF and
copies no review file.

## 5. TIFF Safety

- The source TIFF is never modified.
- Each output ROI is sampled from the source once, then written and read back.
- dtype, axes, channels, ICC/color space, resolution, metadata, and NONE/LZW
  lossless-compression behavior are preserved.
- Read, write, or read-back errors remain terminal failures; they are never
  converted to `needs_review`.

## 6. Uninstall

Delete the X5 Crop folder to remove the program. To remove user-level
dependencies:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
