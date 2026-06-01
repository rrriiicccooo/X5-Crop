# Project P Roadmap

This note captures the important design direction from the earlier ChatGPT web discussion for **Project P / 处理长图扫描**.

The main idea is that X5 Crop should not be only a GUI wrapper around `X5_Split_v17.py`. The long-term value is a review-oriented desktop workflow:

```text
fast analysis
+ confidence scoring
+ visual review
+ manual correction for difficult scans
+ batch export from approved crop plans
```

## Current State

The GitHub project already has the right MVP foundation:

- PySide6 desktop app
- v17 split engine under `x5crop/core/x5_split_engine.py`
- GUI bridge in `x5crop/core_bridge.py`
- debug and analysis previews
- report display
- macOS and Windows PyInstaller packaging
- GitHub Actions build workflow

This is the correct base to continue from. Do not replace it with a simpler GUI wrapper.

## Product Principle

The target workflow is:

```text
automatically solve the easy 95%
clearly flag the uncertain 5%
let the user fix that 5% very quickly
export only after review or approval
```

For extremely underexposed scans, incomplete leaders, unstable frame spacing, or overlapping frames, the app should avoid blindly adding more automatic fallback chains for every file. It should instead surface low-confidence cases and make manual correction efficient.

## Architecture Direction

Separate detection results from final TIFF export.

The app should first generate a `CropPlan` for each source file:

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

Final export should process the original TIFF from the approved `CropPlan`.

Suggested app modules:

```text
Core Engine
- TIFF reader / writer
- metadata preserver
- preview generator
- deskew detector
- analysis map generator
- outer box detector
- split line detector
- grid / frame-size fitter
- crop planner
- TIFF exporter

Job System
- file scanner
- batch queue
- worker pool
- cache manager
- error reporter

GUI
- file list panel
- preview canvas
- parameter inspector
- debug overlay panel
- manual correction tools
- export panel

Project Data
- settings.json
- per_file_overrides.json
- split_report.jsonl
- preview_cache/
```

## Analysis Strategy

Use staged analysis instead of running the heaviest chain on every file.

### Stage 1: Fast Scan

- read metadata
- generate thumbnail or preview
- estimate exposure
- estimate skew risk
- estimate outer-box risk
- decide whether the file needs deeper analysis

### Stage 2: Normal Detection

- `deskew auto`
- `analysis-enhance auto` with fast skip
- `outer-refine auto`
- `grid-fit auto`
- `frame-size-fit auto`
- default `bleed 10`

### Stage 3: Difficult-File Detection

Only run this for low-confidence files:

- `analysis-enhance strict`
- enhanced edge candidate
- `outer-refine strict`
- `frame-size-fit strict`
- `frame-size-min-samples 1`

If the result is still uncertain, mark the file for manual review instead of silently guessing.

## Low-Confidence Review

The app should prioritize files that need attention.

A file should be marked for review when signals include:

- most separators are equal fallback
- outer box was heavily refined
- frame width variation is high
- grid residual is high
- base and enhanced candidates conflict
- deskew angle is unstable
- output boxes touch risky image edges
- extreme underexposure is detected
- lossy or unusual TIFF metadata needs caution

The UI should make the main batch status obvious:

```text
120 analyzed
113 high confidence
7 need review
```

## Preview Canvas

The canvas should become the center of the app.

Overlay colors:

- green: outer box
- red: split lines
- blue: final output boxes including bleed
- yellow: deskew reference lines
- purple: theoretical equal-split grid
- dashed: candidate lines

Expected interactions:

- mouse wheel zoom
- space-drag pan
- click a split line to select it
- drag split lines
- drag outer-box edges
- double-click to reset the selected line
- right-click or button to lock current result
- previous / next file shortcuts

Suggested shortcuts:

- Left / Right: previous / next file
- Space: pan mode
- `1`-`6`: select output frame
- `G`: toggle theoretical grid
- `D`: toggle deskew lines
- `A`: toggle base/enhanced analysis view
- `R`: reanalyze current file
- `L`: lock current file
- `E`: mark equal split
- Enter: approve current file

## Manual Correction Tools

Manual correction should be fast enough to use on many scans.

Important tools:

- drag outer box edges and recalculate split geometry live
- drag one split line and lock only that line
- keep other lines automatic after one manual adjustment
- learn frame width from clear samples
- apply learned frame width to underexposed files
- copy geometry from previous file
- apply geometry to selected files
- reset manual edits

This is especially important for:

- incomplete leaders or tails
- scans that are not exactly six frames
- unstable spacing from old cameras
- overlapping frames
- underexposed rolls with weak separators

## Caching

Repeated analysis should be cheap.

Cache keys should include:

- source path
- file size
- modified time
- algorithm version
- relevant parameter hash

Suggested cached data:

- preview image
- analysis image
- detection result
- crop plan
- report summary

## Performance Direction

MVP:

- PySide6 GUI
- current numpy / tifffile / imagecodecs core
- Pillow or Qt preview generation
- JSON cache
- worker thread or process isolation from UI

Next:

- `ProcessPoolExecutor` for CPU-heavy analysis
- limit TIFF export concurrency to 1-2 files
- preview-first workflow so full-resolution TIFF writing only happens on export

Later:

- consider pyvips / libvips for thumbnails, tiled reads, preview deskew, and large-image operations
- consider C++/Qt or Rust/Tauri only after the PySide6 workflow is proven

## Presets

Keep presets explicit and conservative.

### Standard

```text
deskew auto
analysis-enhance auto
outer-refine auto
grid-fit auto
frame-size-fit auto
bleed 10
```

### Fast

```text
deskew auto
analysis-enhance off or auto-fast
debug off
quick detection only
```

### Underexposed

```text
analysis-enhance strict
outer-refine strict
frame-size-fit strict
low-confidence files flagged for review
```

### Manual Review

```text
run automatic detection
do not export immediately
show all low-confidence files first
```

## Feature Priority

### Phase 1: Review MVP

- persistent `CropPlan`
- confidence scoring and review status
- low-confidence file filter
- better report table
- preview overlays based on crop plans

### Phase 2: Manual Correction

- draggable split lines
- draggable outer box
- lock current geometry
- equal-split toggle per file
- copy geometry from previous file
- apply geometry to selected files

### Phase 3: Efficiency

- preview and analysis cache
- staged fast/deep analysis
- worker pool
- export queue
- project-level settings and overrides

### Phase 4: Professional Polish

- preset management
- keyboard-first review workflow
- `.x5crop` project file
- metadata controls
- optional libvips acceleration
- signed/notarized release builds

## Near-Term Implementation Recommendation

Continue from the existing PySide6 GitHub version.

The next concrete task should be:

```text
Add a CropPlan model and confidence/review status to the app,
then render the current debug/report data through that model.
```

That gives the project a stable place to add manual correction, caching, and batch approval without constantly reshaping the GUI.
