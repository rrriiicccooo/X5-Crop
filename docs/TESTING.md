# Testing Guide

X5 Crop needs visual and data-oriented testing because the hard problems are image-specific.

## Main Risk Cases

Prioritize test scans that cover:

- normal 135 negative strips
- underexposed 135 negative strips
- 135 leader or tail scans with fewer than six complete frames
- 135 positive strips
- half-frame strips
- 120 scans
- unstable frame spacing from older cameras
- overlapping frames
- weak separators

## Local Test Data

Large TIFF scans may exist locally under:

```text
Test/
```

This folder is treated as local working data unless a specific subset is promoted to official fixtures.

Do not commit large TIFFs by accident.

## Manual App Test

Run from source:

```bash
python X5_Crop.py
```

Minimum smoke test:

1. Select one TIFF file.
2. Choose an output folder.
3. Run Analyze / Dry Run.
4. Inspect report summary.
5. Inspect debug preview and analysis preview.
6. Export TIFFs.
7. Confirm output files are written to `split_output` or the selected output folder.

## Batch Test

Use a folder containing several difficult TIFFs.

Check:

- the UI remains responsive
- each input file appears in the report
- failures show actionable messages
- debug images are produced when enabled
- output count matches the selected frame count or equal-split behavior
- unusual scans are not silently treated as high-confidence once confidence scoring exists

## Current Verification Commands

There is not yet a formal automated test suite.

Useful checks today:

```bash
python -m compileall X5_Crop.py x5crop
python X5_Crop.py
```

For packaging verification, see `docs/RELEASE_BUILD.md`.

## Expected Future Tests

As the CropPlan workflow is added, create tests around:

- `CropPlan` serialization
- confidence scoring
- review status transitions
- boundary validation
- export from approved crop plans
- metadata preservation
- cache key stability

Small synthetic images can be committed as normal fixtures. Large real TIFF fixtures should use Git LFS only after an explicit decision.

