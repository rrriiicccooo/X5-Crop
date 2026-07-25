# X5 Crop User Guide

- Active development: **V4.9**
- Stable release: **v4.2.8**

X5 Crop splits long TIFF scans from Hasselblad / Imacon X5 holders into
individual TIFF frames. It exports a result only when geometry is resolved and
output protection is feasible; every other result remains in review.

For normal use, download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

## Install And Run

Run the platform installer once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer checks `numpy`, `tifffile`, `imagecodecs`, and `Pillow`. On macOS,
it prepares only the current Release folder and does not establish system-wide
trust.

Keep the entry script, launcher, and TIFF scans in the same folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

Launch:

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

If macOS blocks double-click launch, run this in the same folder:

```bash
/bin/bash X5_Crop_Mac.command
```

The interactive launcher asks:

```text
format:
partial mode? [y/n, return=no]:
count:
debug analysis? [y/n, return=no]:
```

`count` is asked only in partial mode; Return or `auto` enables automatic count.

## Formats And Modes

| Input | Format | Full count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

- Use full when film fills the holder.
- Use partial for heads, tails, short strips, or scans that do not fill the holder.
- A complete three-frame XPAN or 120-66 scan that does not fill its canvas also
  uses partial.
- `135-dual` is intended for complete dual strips and remains in REVIEW when lane
  evidence is incomplete.

## Detection And Safety

- Source TIFFs are never modified; output is written to new files.
- Output preserves bit depth, channels, ICC/color space, resolution metadata,
  other metadata, and known lossless compression behavior.
- TIFF DPI/PPI is preserved I/O metadata and never a detection input. A known
  single-strip canvas is matched from pixel aspect and supplies px/mm; unknown or
  competing canvases remain in REVIEW.
- Automatic deskew is mandatory. Before frame solving, detection joins the real
  shared photo edges; deskew, mapped geometry, shared-axis safety, and frame size
  consume the same evidence without post-rotation remeasurement.
- Theory only bounds computation. Scan extrema, a single edge, scores, or work
  budgets cannot replace observed paired pixels.
- Bleed is applied only after safe base geometry is resolved. It cannot change
  geometry, gates, or output protection.

## Debug Analysis

Debug Analysis is a dry run: it runs complete detection and writes JPG/report
artifacts without exporting final crop TIFFs.

```text
x5_crop_output/_debug_analysis/
```

Each JPG shows:

1. source physical canvas, shared photo-edge fragments, witnesses, and uncertainty;
2. mapped pair, shared short axis, `FrameSlot`, and `FrameCropEnvelope`;
3. long-axis boundaries, separators, and final boxes.

When no pair is selected, typed failures and compact observation summaries remain
visible. Reports and Debug read detection evidence; they neither recompute
geometry nor act as a cache.

Status:

- `PASS`: automatically exported.
- `REVIEW`: not automatically exported.
- `RUNTIME ERROR`: detection completed, but a later runtime stage failed.

## Output

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

- `needs_review/` contains source-TIFF copies for external handling.
- `x5_crop_report.jsonl` is the current-schema machine audit record.
- `x5_crop_run_manifest.jsonl` records each input's terminal outcome, actual
  outputs, and runtime metrics.
- Normal runs do not overwrite existing crops; `--overwrite` opts in.

Default bleed is 20 px on the long axis and 10 px on the short axis. It affects
final output only.

## Command Line

```bash
# Full help
python3 X5_Crop.py --help

# Interactive mode
python3 X5_Crop.py --interactive

# Normal full crop
python3 X5_Crop.py . --format 135 --strip full

# Debug Analysis dry run
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run

# Partial
python3 X5_Crop.py . --format 135 --strip partial --report

# Disable parallel workers
python3 X5_Crop.py . --format 135 --strip full --jobs 1
```

`--export-review` exports a REVIEW crop only when geometry is resolved and output
protection is feasible. It cannot bypass provisional geometry or unresolved
safety.

## Uninstall And License

Delete the X5 Crop folder to remove the program and its local outputs.
Uninstallers remove user-level dependencies, not Python itself; those
dependencies may be shared.

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

License: MIT. See the
[GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE).
