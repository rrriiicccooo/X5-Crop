# X5 Crop User Guide

- Active development: **V4.9 source-core safety baseline**
- Stable release: **v4.2.8**

The current V4.9 development build reads X5 holder-scan TIFFs, audits the scan
canvas, independent axis scales, and positive source content, then emits review
copies, reports, and Debug Analysis. It has no approved independent Frame Grid
phase authority, so every input remains `needs_review` and no frame TIFF is
exported.

This is the formal capability boundary, not a fallback after auto-cropping fails.

## Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

Run the platform installer once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer checks `numpy`, `tifffile`, `imagecodecs`, and `Pillow`.
On macOS, it prepares only the current Release folder and does not establish
system-wide trust.

Keep the entry script, launcher, and TIFF scans in the same folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

If macOS blocks double-click launch, run:

```bash
/bin/bash X5_Crop_Mac.command
```

## Formats And Modes

| Input | Format | Full design count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPan | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

- Full and partial use the same complete scan-canvas/lane short-axis domain.
- A partial count describes complete design slots, never a partial photograph.
- Format and count remain audit identity, but cannot create frames without Grid
  authority.
- `135-dual` is audited per lane and remains in review.

## Current Detection Facts

Each TIFF produces one base gray and one image-statistics measurement. A known
scan canvas must match uniquely from pixel aspect; no match or competing matches
remain in review.

Long/short px/mm scales are calculated independently. TIFF DPI/PPI is preserved
I/O metadata and is never a detection input.

Positive content uses two independent fields:

```text
intensity = abs(I - five_point_local_mean(I)) / 255
texture   = (abs(dx) + abs(dy)) / 510
positive  = intensity_supported AND texture_supported
```

Components use strict 4-connectivity and immutable RLE. Content can describe
source pixels; it cannot create frame phase, separators, photo edges, or deskew.

The current Grid outcome is fixed:

```text
NO_INDEPENDENT_PHASE_AUTHORITY
```

Therefore:

- status: `needs_review`
- reason: `frame_grid_authority_unavailable`
- containment: `NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`
- visual deskew: `NOT_APPLICABLE_CORE_UNAVAILABLE`
- frame outputs: empty

If scan-canvas or content measurement is itself unavailable, the report adds its
independent typed reason.

## Run And Output

Normal command:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Diagnostics:

```bash
python3 X5_Crop.py . --format 135 --strip full --diagnostics
```

Full help:

```bash
python3 X5_Crop.py --help
```

The default is `--jobs 2`. The output directory may contain:

```text
x5_crop_output/
  needs_review/
  _debug/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

- `needs_review/` contains source-TIFF copies by default;
  `--no-copy-review-files` disables copying.
- `--report` writes current-only JSONL/CSV.
- `--debug-analysis` writes bounded domain and positive-content visuals.
- `--diagnostics` enables report and Debug Analysis without review copying.
- Source TIFFs are never modified.

Current schema:

```text
schema_id       = detection_report
schema_revision = source_core_grid_authority
```

The old `--bleed`, `--bleed-x`, `--bleed-y`, `--export-review`, and `--dry-run`
options have been removed and are rejected. Format-level millimetre protection
authority is reported but cannot be applied without frame geometry and has no
user override.

## ROI/TIFF Foundation

The current runtime does not export frames, but the inverse-affine ROI and TIFF
writer remain independently verified:

- identity is an exact half-open slice;
- affine ROI pixels equal the test reference;
- source RGB is sampled once per ROI;
- dtype, axes, ICC, resolution, metadata, and NONE/LZW compression are preserved;
- out-of-authority geometry raises instead of clamping.

These foundation contracts do not claim that automatic cropping is currently
available.

## Performance Boundary

The fixed 24-input detector-only diagnostic indicates future production headroom
only when the `--jobs 2` median of three measured runs is strictly below
`5.0 seconds/input`. It is not a formal output performance PASS.

Certification with 24 real frame TIFF writes, read-back verification, and
`<=5.0 seconds/input` can run only after independent Grid authority restores
automatic output. The current certification status must be `not_certified`.

## Uninstall And License

Delete the X5 Crop folder to remove the program and local output. Uninstallers
remove user-level Python dependencies, not Python itself; those dependencies may
be shared.

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

License: MIT. See the
[GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE).
