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

- `full` uses the fixed holder count for the format.
- `partial --count N` treats `N` as the authoritative output count.
- `partial --count auto` conservatively emits every valid holder slot for the
  format, so blank TIFFs may remain.
- `--layout auto` selects horizontal or vertical from the scan; either may be
  specified explicitly.
- `--debug-analysis` explicitly creates a diagnostic JPG; it is off by default.
- `--preview` writes only Debug Analysis, reports, and a strictly bound
  detection snapshot—never official TIFFs or a review copy.

The program does not infer format or count from filenames and does not suppress
blank slots.

To inspect detection before cropping, run the same parameters twice and remove
`--preview` from the second command:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --preview
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

Preview uses the separate `x5_crop_preview/` and does not replace production
output. Reuse occurs only when source SHA-256, detection configuration, layout,
schema, runtime dependencies, implementation, and snapshot integrity all
match; otherwise fresh detection runs automatically. An ordinary report cannot
enable cropping by itself.

## 4. Read The Result

Photos are written directly in the output root:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  _detection_snapshot/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

`needs_review/`, `_debug_analysis/`, and `_detection_snapshot/` are created only
when needed. A successful run replaces the previous complete output only after
ownership is verified. If unknown files are present, X5 Crop stops and never
deletes them.

APFS, HFS+, and NTFS are local transaction-validation targets, but formal
support still requires a receipt for the exact release. On an unverified
filesystem, an interactive launch asks for consent. A
non-interactive command must explicitly include `--allow-best-effort-output`.
This option cannot bypass hard lock, path, disk-space, or rename failures.

See the [English User Guide](user-guide.en.md) for full details.
