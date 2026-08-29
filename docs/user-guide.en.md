# X5 Crop V5 User Guide (Development Preview)

- Scope: unreleased V5 source on repository `main`
- Current public stable release: v4.2.8; its commands and behavior differ, so use the documentation bundled with it
- Intended input: Hasselblad / Imacon X5 holder scans whose format and exposure-slot count are already known

## Product Behavior

X5 Crop aligns a fixed physical template for a known format; it is not a general-purpose photo-boundary recognizer.
Official TIFFs are written only when every slot in the source has one unique, safe, directly usable crop. Otherwise the
entire source becomes `needs_review`; individual slots are never salvaged.

### Format And Count

Format is always required. Count may be omitted or explicit:

- omit `--count` to confirm the matched holder's default complete count;
- use `--count N` to confirm exactly N slots, including intermediate blank exposures;
- count must be positive and no greater than the matched-holder capacity;
- `135-dual` is automatic only at 12 slots, six per lane; every other count enters review.

Default complete counts are 135=6, half=12, XPan=3, 120-645=4, and 120-66=3. 120-67 uses 3 on an ordinary holder
and 2 on the short holder. 135-dual uses 12 total.

The program never infers format or real photo count from filenames, picture content, holder capacity, or blank slots.
It does not remove, merge, or reorder blank slots. V5 has no full/partial mode.

### Automatic Approval And Review

V5 first establishes coarse support and a common direction from the whole strip. It then compiles format/count into a
fixed W/H template and makes bounded local measurements only near theoretical outer, separator, and top/bottom
positions. Pixel evidence aligns or rejects the template; it cannot invent format, count, or placement authority.

Normal strips use one shared pitch. One directly proven, ordinal-unique wide or narrow gap may apply a single suffix
shift. Missing authority, multiple equally legal answers, multiple required shifts, an unknown required Frame, contact,
or overlap remains `needs_review`. Contact and overlap are challenge cases: safe review is correct behavior, and V5
does not enable a second detector or special bleed for them.

Holder fill is assessed only after placement by asking whether another W fits beyond either outer. It never searches
for or centers a placement. Both lanes of 135-dual must be complete.

## Safe Cropping, Bleed, And Deskew

Product bleed for photo-aperture output is:

```text
start/end = max(0.15 mm, 0.7% W)
top/bottom = 0.25 mm
```

Measurement uncertainty, local residual, and bleed share a maximum 5% W/H outward budget per side. Sides cannot
borrow budget from one another. A directly observed continuous outer-support pair may replace unavailable aperture
top/bottom when it fully encloses fixed H and its total height is no greater than `1.1H`; that mode adds no 0.25 mm
cross bleed. Any genuinely required source-space footprint outside authority enters review instead of being clipped.

Two-dimensional content is a conservative veto on the final post-bleed polygon. Picture structure inside bleed may be
retained; reliable content crossing the final crop boundary blocks automatic output. Dust, aliasing, and tiny corner
grazes do not independently move a boundary or select another placement.

Deskew is optional cleanup after automatic approval and never participates in detection or the Gate. `--deskew auto`
rotates only when both sides support one stable small angle; missing, conflicting, or excessive evidence preserves the
source orientation. `--deskew off` skips observation. When rotation is applied, the source and already-safe polygons use
the same affine transform before an axis-aligned envelope is taken. Small black no-data corners may remain, but
protected content cannot be cut.

## Install The Development Source

Use a complete repository checkout. Do not copy only `X5_Crop.py`, and do not treat GitHub's generated Source code
archive as a stable release package. Regular users should download v4.2.8 from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases).

The V5 development source supports Python 3.12–3.14:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a future V5 Release package.

Setup reuses a suitable global Python and existing dependencies and installs only what is missing. Unknown ownership
stops before any write. It creates no private `.venv` and does not require Homebrew.

## Input Contract

V5 production input must be:

- a one-page TIFF;
- unsigned 16-bit samples;
- three-channel RGB with contiguous planar configuration;
- `NONE`, `LZW`, `DEFLATE` / `ADOBE_DEFLATE`, or `ZSTD` lossless compression;
- TIFF Orientation 1–8.

An out-of-domain file becomes `runtime_error`; it is never silently converted. Orientation is normalized on read and
official output uses `Orientation=1`.

## Run

Graphical launch:

- macOS: place TIFFs beside `X5_Crop_Mac.command` and double-click it;
- Windows: place TIFFs beside `X5_Crop_win.bat` and double-click it.

Command-line example:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

Main options:

- `input`: one TIFF or a directory; defaults to the current directory;
- `--output PATH`: a fresh output directory;
- `--format`: `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, or `120-67`;
- `-n, --count N`: explicit slot count; omit it to confirm the default complete count;
- `--layout`: `auto`, `horizontal`, or `vertical`;
- `--deskew`: `auto` (default) or `off`;
- `--jobs N`: source concurrency, default 1 and maximum 3;
- `--debug-analysis`: write 1,800 px wide, height-adaptive three-panel diagnostic JPGs, a development report, and a
  summary, but no official TIFFs;
- `--interactive`: prompt for format, count, deskew, and Debug Analysis.

There is no `--overwrite`. The target must not exist. Use different fresh directories for Debug Analysis and official
cropping; an official run always rereads the source TIFF.

## Status, Output, And Exit Codes

Each input has exactly one terminal state:

- `approved_auto`: writes the complete official TIFF set;
- `needs_review`: writes no photos and retains the minimum missing fact and suggested action;
- `runtime_error`: this input failed while other inputs continue.

Debug Analysis shows the template, observations, winner/runner, final footprint, budget, and first blocking reason,
plus `DESKEW APPLIED`, `ROTATION NOT NEEDED`, or a typed `DESKEW SKIPPED`. It reads the same detection facts and
never solves geometry again.

Default output:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

Exit codes:

- `0`: published successfully with no `runtime_error`;
- `1`: published with a runtime error, or every input failed;
- `2`: CLI, input-set, or preflight failure;
- `3`: a fresh output directory could not be published safely.

Official TIFFs are read and written only by `tifffile + imagecodecs`, with checks for bit depth, channels, ICC,
resolution, supported metadata, lossless compression, and `Orientation=1`. Each run writes staging first and publishes
with one rename; an existing target is never traversed, replaced, or deleted.

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
