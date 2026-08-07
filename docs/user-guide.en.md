# X5 Crop User Guide

- Latest public stable release: v4.2.8
- Current repository source: current-only V5, not publicly released
- Intended input: Hasselblad / Imacon X5 holder scans whose format, strip mode,
  and required count are already known

## Product Behavior

X5 Crop produces conservative TIFF crops without cutting real photo content.
You provide the film format. The program combines scan pixels, fixed physical
dimensions, holder canvas, count, and order. It writes photos only when content
protection, excess margins, transform, and TIFF output are all safe. Otherwise
the whole source enters `needs_review`; individual slots are never salvaged.

The program does not claim to recover one uniquely true photo boundary and does
not infer format or count from filenames. `partial --count auto` uses the valid
maximum capacity of the matched holder. Blank suppression is not implemented,
so blank slots may be emitted. When adjacent photos touch or locally overlap,
neighboring outputs may share a small amount of source pixels to protect content.

## Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

The release package supports Python 3.12–3.14 and freezes these dependencies:

```text
numpy==2.5.1
scipy==1.18.0
opencv-python-headless==5.0.0.93
tifffile==2026.7.31
imagecodecs==2026.6.26
Pillow==12.3.0
```

Run the platform installer:

- macOS: `install/X5_Crop_Mac_install.command`
- Windows: `install/X5_Crop_win_install.bat`

Dependencies are installed in the target Python's user package site. No private
`.venv` is created. If a frozen dependency already exists at another version,
the installer stops before upgrading, downgrading, or overwriting it.

## Input Contract

The V5 production domain is:

- one TIFF page;
- unsigned 16-bit samples;
- three-channel RGB with contiguous planar configuration;
- `NONE`, `LZW`, `DEFLATE` / `ADOBE_DEFLATE`, or `ZSTD` lossless compression;
- TIFF Orientation 1–8.

A file outside this domain becomes `runtime_error`; it is not converted or
guessed. Orientation is resolved at decode. Detection, ordering, and cropping
use canonical visual coordinates, and output pixels are written with
`Orientation=1`.

## Run

Graphical launch:

- macOS: put TIFFs beside `X5_Crop_Mac.command` and double-click it.
- Windows: put TIFFs beside `X5_Crop_win.bat` and double-click it.

Command-line example:

```bash
python3 X5_Crop.py /path/to/scans \
  --format 120-66 \
  --strip partial \
  --count auto \
  --jobs 2
```

Production options:

- `input`: one TIFF or a directory; defaults to the current directory.
- `--output PATH`: output directory; defaults to `x5_crop_output` beside input.
- `--format`: `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, or `120-67`.
- `--layout`: `auto`, `horizontal`, or `vertical`.
- `--strip`: `full` or `partial`.
- `--count N|auto`: authoritative partial count or matched-holder capacity;
  full mode uses the fixed format count.
- `--jobs N`: source concurrency; default 2, maximum 3. Numerical library
  threads remain fixed at 1.
- `--debug-analysis`: explicitly write a four-layer diagnostic JPG; off by default.
- `--allow-best-effort-output`: explicitly accept weaker publication semantics
  on an unverified filesystem.
- `--interactive`: prompt for format, mode, count, and Debug Analysis.

There is no `--overwrite`. A successful run always replaces the previous
complete, verified V5-owned output.

## Status And Exit Codes

Each input has one terminal status:

- `approved_auto`: writes the complete set of official photo TIFFs.
- `needs_review`: writes no official photos and copies the source into
  `needs_review/`.
- `runtime_error`: writes no photos for that input while other inputs continue.

Exit codes:

- `0`: published successfully with no `runtime_error`.
- `1`: published with at least one `runtime_error`, or every input failed and
  nothing was published.
- `2`: CLI, input-set, or preflight failure.
- `3`: ambiguous output transaction, publication failure, or recovery failure.

If every input is `runtime_error`, X5 Crop does not publish an empty replacement;
the previous output remains untouched.

## Output And Safe Replacement

Default layout:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

Photos stay directly in the root. There are no `run-*` or per-source folders.
`needs_review/` and `_debug_analysis/` appear only when needed.

A new run first builds a complete internal transaction directory beside the
target. After all inputs finish, official TIFF readback succeeds, and report and
manifest are complete, two same-parent renames publish the new result. The old
result is then deleted. Clear process crashes or forced termination can be
recovered. If sudden power loss leaves an ambiguous state, target, new, old, and
journal are all preserved for manual confirmation.

Automatic replacement requires a fixed owner marker, current manifest, and an
exact inventory match. An extra or missing file, link, junction, reparse point,
old schema, or manually created directory stops the run; user files are never
silently deleted.

## Filesystems And Disk Space

Verified local filesystems run directly. SMB, NAS, cloud-synchronized folders,
unverified exFAT, and filesystems whose semantics cannot be established are
best effort:

- an interactive launch shows the risk and target and defaults to refusal;
- non-interactive use must explicitly include `--allow-best-effort-output`.

Consent cannot bypass hard lock, same-filesystem, rename, path-safety, or disk-
space failures. Preflight budgets the complete new output, reports, optional
Debug Analysis, transaction overhead, and a 32 MiB guard for the whole
invocation. The old result still occupies space until publication succeeds.

## TIFF Fidelity And Privacy

Official TIFF I/O is owned exclusively by `tifffile + imagecodecs`. Every output
is reopened after its write handle closes and checked for 16-bit RGB, three
channels, contiguous planar layout, shape, pixels, ICC, resolution, resolution
unit, supported metadata, lossless compression, and `Orientation=1`.

Normal runs do not reread source TIFFs to calculate content SHA, inspect Git or
test cohorts, create performance receipts, profile, or inject faults. They keep
only lightweight identity needed for the run and output transaction: `run_id`,
input ordinal, portable filename, size, mtime, dependency/thread identity, and
publication facts. Pillow is imported lazily only when Debug Analysis is enabled.

## Current Validation Boundary

V5 is now the repository's only runtime. Synthetic contracts, strict TIFF and
Orientation handling, current schemas, standalone construction, and recoverable
flat-output publication exist. Full real golden accuracy, the 24-source
performance receipt, and formal Windows x64, Apple Silicon, and Intel macOS
receipts are not complete. This repository state is therefore not a V5 release-
ready or all-platform-support claim. Users should continue to use public stable
v4.2.8.

## Remove And License

Dependency uninstallers:

- macOS: `install/X5_Crop_Mac_uninstall.command`
- Windows: `install/X5_Crop_win_uninstall.bat`

The uninstaller removes only dependencies introduced by X5 Crop whose versions
have not changed and which are no longer required by another package.

License: MIT — [LICENSE](../LICENSE)
