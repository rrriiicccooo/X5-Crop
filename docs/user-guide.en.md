# X5 Crop User Guide

- Current stable release: **v4.2.8**
- Repository status: V4.9 is an architecture experiment; V5 is the next
  production target and is not released

X5 Crop conservatively separates Hasselblad / Imacon X5 holder-scan TIFFs into
individual photos. You provide the film format, strip mode, and any required
count. The program handles detection, deskew, safe cropping, TIFF writing, and
read-back validation.
This guide follows repository development. For production use, follow the
documentation included in the GitHub Release package.

## Product Behavior

The first priority is retaining every real photo pixel. The second is avoiding
outputs so wide that they need manual recropping.

- Pixel edges and known format dimensions create a small set of complete frame
  placements; one high-scoring local line does not control the crop by itself.
- Equally valid placements jointly define the safe crop. If they cannot all fit
  inside the allowed margins, the result is `needs_review`.
- Maximum expansion is 5% of the design width on each `start/end` edge and 3%
  of the design height on each `top/bottom` edge. Each edge is an independent
  hard limit, and an exact-limit result passes.
- Outputs may retain a small border or neighboring-photo area, and adjacent
  outputs may overlap when needed to preserve content.
- Partial auto keeps every valid slot in the matched holder, so it may write an
  extra blank TIFF. It never guesses the true photo count from filenames or
  image appearance.
- `approved_auto` means the output satisfies the current safety contract; it
  does not claim that every physical edge was uniquely reconstructed.

## Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive. Unzip it and run once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

Supported platforms are macOS 14 or later on Apple Silicon and Intel Macs, and
64-bit Windows. The installer uses Python 3.12, 3.13, or 3.14 and installs
pinned `NumPy`, `SciPy`, `opencv-python-headless`, `tifffile`, `imagecodecs`,
and `Pillow` into the current user's Python site. It creates no virtual
environment and does not modify system-level Python. On macOS, it prepares only
the current Release folder and establishes no permanent system-wide trust. If
the same interpreter already contains another OpenCV distribution that owns
the `cv2` namespace, setup stops before changing any package to avoid file
collisions.

Keep the entry script, launcher, and TIFFs in one folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

Double-click `X5_Crop_Mac.command` on macOS or `X5_Crop_win.bat` on Windows.
If macOS blocks double-click launch, run this in that folder:

```bash
/bin/bash X5_Crop_Mac.command
```

## Formats, Modes, And Count

| Input | Format | Full count | Partial |
|---|---|---:|---|
| Return / `135` | 135 | 6 | 1..6 or auto |
| `dual` / `135-dual` | dual-lane 135 | 12 | unsupported |
| `half` | half-frame | 12 | 1..12 or auto |
| `xpan` | XPan | 3 | 1..3 or auto |
| `645` / `120-645` | 120-645 | 4 | 1..4 or auto |
| `66` / `120-66` | 120-66 | 3 | 1..3 or auto |
| `67` / `120-67` | 120-67 | 3 | 1..3 or auto |

The user always supplies the format; runtime never guesses it.

- Full uses the format's default count.
- A partial integer is an authoritative explicit count.
- Omitting partial `--count`, passing `--count auto`, or pressing Return in the
  interactive prompt uses holder capacity.
- Auto matches the holder and writes every valid slot for the format. It does
  not infer the number of visible photos.
- `135-dual` writes lane one positions 1..6, followed by lane two positions
  1..6.

## Run

Normal full mode:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial explicit and auto:

```bash
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
```

Explicit vertical strip:

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

`--layout auto` is the default. Parallelism defaults to `--jobs 2`; normal
runs cap at three workers and diagnostics at four. See every option with:

```bash
python3 X5_Crop.py --help
```

## Status And Review

Each input has one of three outcomes:

- `approved_auto`: safety checks pass and official photo TIFFs are written.
- `needs_review`: a concrete risk remains; no official photo TIFF is written,
  and the report records the reason.
- terminal error: reading, detection execution, writing, or read-back failed.
  This is not a review result.

Typical review causes include an unmatched holder or count, incomplete format
placement, non-unique deskew direction, inconsistent source-wide frame
geometry, lane escape, incomplete containment of retained placements, any edge
over its 5%/3% limit, or an unavailable transform.

The source TIFF is copied to `needs_review/` by default. Use
`--no-copy-review-files` to disable that copy.

## Output And Diagnostics

The default output folder is:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  ...
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

Additional files are written only when requested:

- `--report`: detailed JSONL plus a CSV summary.
- `--debug-analysis`: a four-layer diagnostic JPG showing holder authority,
  pixel evidence, frame placements, and the final safe output.
- `--diagnostics`: read-only diagnostics; enables report and Debug Analysis but
  writes no photo TIFF and copies no review file.
- `--overwrite`: replace existing outputs.
- `--compression same`: preserve supported source lossless compression where
  possible; `none` writes uncompressed TIFF.

## TIFF Fidelity

The source TIFF is never modified. Each approved output uses one inverse-affine
sample from the source. Interpolation taps outside a lane use the background
instead of sampling another lane. Every file is read back to check:

- dtype, bit depth, axes, shape, channels, and planar configuration;
- photometric interpretation and ICC/color space;
- resolution and resolution unit;
- description, datetime, software, and supported metadata;
- pixels and lossless-compression behavior.

Read, write, atomic-replace, or read-back failures remain independent errors
and never create a success result.

## Current Validation Boundary

V4.9 is retained only as a fixed-format template-first architecture experiment.
V5 has not completed implementation, real-photo accuracy validation, or release
validation. Use the version marked stable in GitHub Releases for important
originals, and always retain the source TIFFs.

## Remove And License

To clean up dependencies, run this before deleting the Release folder:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

Setup leaves a dependency receipt owned by that Release folder. The
uninstaller removes only packages that were absent before setup, remain at the
installed version, and are not used by another installed Python package.
Pre-existing, subsequently changed, or shared packages are preserved. Then
delete the X5 Crop folder to remove the program and local outputs.

License: MIT. The release root includes `LICENSE`; the
[full text](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE) is also
available on GitHub.
