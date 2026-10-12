# X5 Crop V5 Quick Start (Development Preview)

This guide covers only the unreleased V5 source on repository `main`. The latest public stable release is v4.2.8;
download its release package and follow its bundled documentation instead.

## Install

Obtain a complete repository checkout, then run its platform installer:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a future V5 release package. Setup finds
64-bit Python 3.12–3.14, reuses suitable dependencies, and installs or updates the rest. Homebrew is not required,
and no private environment is created.

## Run one source

From the repository root, use one TIFF or a scan directory and provide the known format:

```bash
python3 X5_Crop.py /path/to/scans --format 135
```

Omitting `--count` confirms the matched holder's default complete count. Use an explicit count when the source has a
different known count:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

For a first inspection, use a fresh debug directory and then a different fresh directory for the official run:

```bash
python3 X5_Crop.py /path/to/scans --format 135 --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --output /path/to/x5_crops
```

Debug Analysis writes diagnostic JPGs and reports, but no official TIFFs. A normal run rereads the source TIFF and
does not reuse the debug report. The target directory must not already exist; an existing target is preserved and the
run reports an output error.

## Read the result

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

Approval is source-wide: if any required slot is unsafe or evidence is insufficient, the complete source enters
`needs_review`. Deskew is optional cleanup after the safety decision. See the [English User Guide](user-guide.en.md)
for the complete input contract, format/count rules, geometry contract, output details, and exit codes.
