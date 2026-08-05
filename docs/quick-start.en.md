# X5 Crop Quick Start

The current stable release is **v4.2.8**.

## 1. Download And Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive. Unzip it and run once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

## 2. Add TIFFs And Launch

Keep the TIFFs and launch files in one folder:

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

## 3. Choose Format, Mode, And Count

Supported formats are `135`, `135-dual`, `half`, `xpan`, `120-645`,
`120-66`, and `120-67`.

- `full`: use the format's fixed holder count.
- `partial` with an integer: strictly use that output-slot count.
- `partial` with `auto`: write every valid slot for the matched holder without
  guessing the true photo count.
- `135-dual` supports `full` only.

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

Defaults are `--layout auto` and `--jobs 2`. For every option:

```bash
python3 X5_Crop.py --help
```

## 4. Read The Result

- `approved_auto`: official photo TIFFs are written to `x5_crop_output/`.
- `needs_review`: no official photo TIFF is written; the source is copied to
  `needs_review/` by default.
- `--diagnostics`: write the report and Debug Analysis only; no photo TIFF is
  written.

The source TIFF is never modified. See the [User Guide](user-guide.en.md) for
complete settings, output, diagnostics, and TIFF-fidelity details.
