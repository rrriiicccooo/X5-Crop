# Project Context

This document gives future Codex sessions the project background needed to continue without restarting from scratch.

## Name

The app is named:

```text
X5 Crop
```

## Origin

The project began as a Python script for cutting long TIFF film scans into individual frames.

The original v17 script must remain preserved in the project root:

```text
X5_Split_v17.py
README_X5_Split_v17.md
```

The desktop app currently imports a packaged engine from:

```text
x5crop/core/x5_split_engine.py
```

## Current App Shape

Current foundation:

- PySide6 desktop GUI
- TIFF input and output
- v17 split engine packaged into `x5crop/core/`
- app bridge in `x5crop/core_bridge.py`
- preview/debug output
- report summaries
- macOS and Windows PyInstaller specs
- GitHub Actions build workflow

## Important Product Direction

The goal is not to keep adding blind fallback logic until every file produces something.

The goal is:

```text
automatic for easy scans
honest about uncertainty
fast manual correction for hard scans
safe final export from approved crop plans
```

Hard scans include:

- underexposed rolls
- scans that start at the leader instead of a complete six-frame strip
- incomplete strips
- unstable spacing caused by old cameras
- overlapping frames
- weak separator regions

## Roadmap Anchor

The preserved roadmap is:

```text
PROJECT_P_ROADMAP.md
```

The most important next architecture step is to introduce a persistent `CropPlan` model:

```json
{
  "file": "X5 022.tif",
  "deskew_angle": -0.18,
  "outer_box": [120, 40, 9870, 1640],
  "boundaries": [0, 1625, 3250, 4875, 6500, 8125, 9750],
  "bleed": 10,
  "confidence": 0.91,
  "warnings": ["low_exposure", "weak_gap_3"],
  "manual_overrides": false
}
```

Future export should use approved crop plans rather than exporting immediately from opaque detection state.

## Near-Term Priority

Recommended next task:

```text
Add a CropPlan model and confidence/review status to the app,
then render current debug/report data through that model.
```

This creates a stable base for manual correction, caching, batch approval, and safer handling of difficult scans.

