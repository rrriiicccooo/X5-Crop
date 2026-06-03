# X5 Split v18 Double-Click Use

中文完整说明见：

```text
README_X5_Split_v18.md
```

Put these files in the folder that contains the TIFF scans you want to crop:

- `X5_Split_v18.py`
- Windows: `X5_Split_v18_Windows_DoubleClick.bat`
- macOS: `X5_Split_v18_macOS_DoubleClick.command`

Then double-click the launcher for your system.

Optional diagnostic launchers:

- Windows debug: `X5_Split_v18_Windows_Debug_DoubleClick.bat`
- Windows debug analysis: `X5_Split_v18_Windows_DebugAnalysis_DoubleClick.bat`
- macOS debug: `X5_Split_v18_macOS_Debug_DoubleClick.command`
- macOS debug analysis: `X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command`

Default behavior:

- Processes `.tif` and `.tiff` files in the same folder.
- Writes cropped TIFF files to `split_output`.
- Writes `split_report.jsonl` and `split_summary.csv`.
- Does not overwrite existing cropped TIFF files.
- Low-confidence files are marked in the report and are not exported unless you run the Python script manually with `--export-review`.

Debug behavior:

- Debug launchers are dry runs. They write reports and crop/gap preview JPG
  files to `split_output/_debug`, but they do not write cropped TIFF frames.
- Debug analysis launchers are also dry runs. They additionally write
  base/enhanced detection grayscale JPG files to `split_output/_debug_analysis`.
- JPG debug files can be opened directly in Finder, Preview, Photos, and most
  image viewers.

Dependencies:

```bash
python3 -m pip install -U numpy tifffile imagecodecs Pillow
```

On Windows, if `python3` is not available, use:

```powershell
py -3 -m pip install -U numpy tifffile imagecodecs Pillow
```

macOS note:

If macOS says the `.command` file cannot be opened because it is not executable, run this once in Terminal:

```bash
chmod +x X5_Split_v18_macOS_DoubleClick.command
chmod +x X5_Split_v18_macOS_Debug_DoubleClick.command
chmod +x X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command
```

After that, it can be double-clicked.
