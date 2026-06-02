# X5 Crop UI Redesign: Capture One / Lightroom Inspired Review Workspace

Date: 2026-06-02

## Goal

The current UI is useful for running the engine, but it feels like a parameter
wrapper. The next UI should feel like a professional crop review workstation:

```text
import scans
analyze automatically
review uncertain files first
adjust crop geometry visually
approve crop plans
export approved TIFFs
```

The visual reference is Capture One / Lightroom, adapted for long film-strip
scan splitting rather than photo color editing.

## Product Principles

- The center canvas is the product, not the option form.
- Batch status should always be visible: analyzed, approved, needs review,
  failed, exported.
- Easy scans should move through automatically.
- Difficult scans should become obvious and quick to fix.
- Export should happen from approved crop plans, not directly from an opaque
  one-shot detection run.
- Advanced detection parameters should exist, but stay behind a focused panel.

## Proposed Main Layout

Use a dark, three-panel desktop layout with a bottom filmstrip:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top bar: Library | Review | Export     Analyze  Reanalyze  Approve  Export │
├───────────────┬──────────────────────────────────────────────┬───────────────┤
│ Left panel    │ Main preview canvas                          │ Right panel   │
│               │                                              │               │
│ Source        │ zoomable long scan preview                   │ Histogram     │
│ folders       │ overlay: outer box, split lines, crop boxes  │ Crop Plan     │
│               │ drag lines / edges                           │ Warnings      │
│ Batch queue   │ compare debug / analysis / final preview     │ Adjustments   │
│ status groups │                                              │ Export        │
│               │                                              │               │
├───────────────┴──────────────────────────────────────────────┴───────────────┤
│ Bottom filmstrip: scan thumbnails with status badges and warning markers     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Default panel widths:

- Left library / queue: 260 px
- Center canvas: flexible
- Right inspector: 340 px
- Bottom filmstrip: 128-160 px height

## Modes

### Library

Purpose: choose TIFF files or folders and understand the batch before analysis.

Main controls:

- Add File
- Add Folder
- Remove Selected
- Output Folder
- Analyze Batch

Left panel:

- Recent folders
- Current source path
- File groups:
  - All
  - Not analyzed
  - Needs review
  - Approved
  - Exported
  - Failed

Center:

- Empty state with drag-and-drop target
- After selecting a file, show a neutral preview if available

Right panel:

- Batch summary
- Default preset
- Frame count
- Bleed
- Compression

### Review

Purpose: inspect automatic crop plans and manually correct difficult scans.

This should be the default working mode after analysis.

Center canvas:

- Long scan preview fits to width by default.
- Mouse wheel zoom.
- Space-drag pan.
- Split lines are draggable vertical handles.
- Outer box edges are draggable.
- Final crop boxes are visible with frame numbers.
- Selected frame is highlighted.
- Toggle overlays:
  - Crop boxes
  - Split lines
  - Outer box
  - Equal grid
  - Deskew guides
  - Warning zones

Right inspector tabs:

1. Plan
   - Review status: Needs review / Approved / Locked
   - Confidence score
   - Warning list
   - Source metadata summary
   - Detection method summary

2. Adjust
   - Frame count
   - Bleed
   - Deskew angle
   - Outer X / Y numeric fields
   - Boundary numeric fields
   - Reset selected line
   - Reset all manual edits
   - Copy geometry from previous
   - Apply geometry to selected files

3. Analyze
   - Preset: Standard / Fast / Underexposed / Review
   - Deskew
   - Analysis enhance
   - Outer refine
   - Grid fit
   - Frame size fit
   - Force equal split
   - Reanalyze current
   - Reanalyze selected

4. Export
   - Output folder
   - Compression
   - Overwrite outputs
   - Export approved
   - Export selected

Bottom filmstrip:

- One item per source TIFF.
- Thumbnail uses debug preview when available.
- Status badge:
  - gray: not analyzed
  - green: approved
  - amber: needs review
  - red: failed
  - blue: exported
- Small warning count.
- Current file has a clear focus ring.

### Export

Purpose: make final output decisions without re-entering technical parameters.

Center:

- Batch export summary
- List of files blocked from export because they are not approved
- Estimated output count

Right:

- Output folder
- Compression
- Metadata preservation note
- Overwrite toggle
- Export button

## Visual Style

Use a restrained professional dark theme:

- App background: `#171717`
- Panel background: `#202020`
- Canvas background: `#101010`
- Border: `#343434`
- Primary text: `#f2f2f2`
- Secondary text: `#a8a8a8`
- Muted text: `#737373`
- Accent blue: `#4ea1ff`
- Approved green: `#3fb950`
- Review amber: `#d29922`
- Failed red: `#f85149`
- Crop blue: `#58a6ff`
- Outer green: `#56d364`
- Split red: `#ff6b6b`
- Grid purple: `#bc8cff`

Keep controls compact. This should feel like a utility for repeated work, not a
marketing page.

## Main Actions

Top bar actions:

- Analyze
- Reanalyze
- Approve
- Lock
- Previous
- Next
- Export

Canvas toolbar:

- Zoom to fit
- 100%
- Pan
- Select
- Toggle crop boxes
- Toggle split lines
- Toggle grid
- Toggle debug / analysis preview

File actions:

- Mark approved
- Mark needs review
- Lock geometry
- Reset manual edits
- Copy geometry
- Apply geometry

## Keyboard Shortcuts

- Left / Right: previous / next file
- Enter: approve current file
- R: reanalyze current file
- L: lock current crop plan
- E: force equal split for current file
- G: toggle equal grid
- D: toggle debug overlays
- A: toggle analysis preview
- Space: pan while held
- 1-6: select frame
- Cmd/Ctrl + Plus: zoom in
- Cmd/Ctrl + Minus: zoom out
- Cmd/Ctrl + 0: zoom to fit

## Required Data Model

The UI should be backed by a persistent crop plan instead of only a log/report
view.

Minimum useful `CropPlan`:

```json
{
  "source": "/path/to/X5 022.tif",
  "output_dir": "/path/to/split_output",
  "frame_count": 6,
  "deskew_angle": -0.18,
  "outer_box": [120, 40, 9870, 1640],
  "boundaries": [0, 1625, 3250, 4875, 6500, 8125, 9750],
  "bleed": 10,
  "crop_boxes": [[120, 40, 1750, 1640]],
  "confidence_percent": 91,
  "status": "needs_review",
  "warnings": ["low_exposure", "weak_gap_3"],
  "manual_overrides": false,
  "locked": false,
  "analysis_version": "1.1.0"
}
```

Recommended statuses:

- `not_analyzed`
- `analyzing`
- `needs_review`
- `approved`
- `locked`
- `exported`
- `failed`

## Current Code Mapping

Existing app pieces that can be reused:

- `EngineWorker`: keep for background analysis/export jobs.
- `PreviewLabel`: replace with a real canvas widget later, but it can host the
  first redesign pass.
- `read_report`: use as the temporary source for status/warnings until
  `CropPlan` exists.
- `debug_preview_for` and `analysis_preview_for`: use for filmstrip thumbnails
  and canvas preview.
- `EngineOptions`: keep as the advanced Analyze panel data source.

Needed new UI classes:

- `ReviewCanvas`: zoom, pan, overlays, selected boundary/frame.
- `FileQueueModel`: source TIFF list plus status, warning count, preview path.
- `FilmstripWidget`: thumbnail row with badges.
- `InspectorPanel`: Plan / Adjust / Analyze / Export tabs.
- `CropPlanStore`: read/write crop plans and manual overrides.

## MVP Implementation Plan

### Phase 1: Shell Redesign

No new crop editing yet. Reorganize the current UI into the professional layout.

- Replace the top input/output group with a compact toolbar.
- Add left file/status panel.
- Keep current preview tabs in the center, styled as the main canvas.
- Move options into right-side tabs.
- Add bottom filmstrip list.
- Parse `split_report.jsonl` to show warning counts and status badges.

This phase makes the app feel like the target workflow without changing engine
behavior.

### Phase 2: CropPlan Foundation

- Add `x5crop/crop_plan.py`.
- Convert report rows into crop plans.
- Save plans to `.x5crop/crop_plans.json`.
- Track status, approval, lock state, and manual override flags.
- Make Export use approved plans when possible.

### Phase 3: Interactive Canvas

- Replace static preview labels with a custom `QGraphicsView` or canvas widget.
- Draw editable overlays from `CropPlan`.
- Support zoom, pan, split-line dragging, outer-box dragging, and reset actions.

### Phase 4: Batch Review Speed

- Needs-review queue.
- Approve and advance.
- Copy geometry from previous.
- Apply geometry to selected.
- Batch reanalyze selected files.

## First Build Target

The first practical implementation should be Phase 1. It is low risk because it
only changes layout and presentation:

```text
existing engine behavior
+ professional review shell
+ clearer batch state
+ less intimidating advanced settings
```

After Phase 1 is tested, build `CropPlan` and manual editing on top of it.
