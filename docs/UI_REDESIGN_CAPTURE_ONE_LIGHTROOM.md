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

The workflow reference is Capture One / Lightroom, adapted for long film-strip
scan splitting rather than photo color editing. The interface style should
follow Apple Human Interface Guidelines for a macOS productivity app.

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

Use a macOS split-view layout with a toolbar, sidebar, central content view,
inspector, and bottom filmstrip:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ macOS toolbar: sidebar toggle  Library | Review | Export  analyze/approve │
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

Default pane widths:

- Left library / queue: 260 px
- Center canvas: flexible
- Right inspector: 340 px
- Bottom filmstrip: 128-160 px height

## Apple HIG Alignment

Design decisions should be guided by Apple Human Interface Guidelines:

- Use platform conventions first: native window frame, toolbar, sidebar,
  split view, inspector, menus, system font, and system colors.
- Preserve visual hierarchy: navigation on the leading side, selected scan in
  the center, current-scan details in the trailing inspector, and batch context
  in supporting panes.
- Treat the toolbar as the place for actions that affect the current view:
  Analyze, Reanalyze, Approve, and Export belong in the toolbar.
- Treat the sidebar as navigation, not a dense settings form. It should contain
  source locations, smart groups, and the scan queue.
- Treat the inspector as contextual detail for the selected scan. It should be
  hideable, and advanced controls should be grouped into disclosure sections or
  tabs.
- Avoid putting critical controls only at the bottom of the window. The
  filmstrip can stay at the bottom because it is secondary navigation, but
  primary actions must also be available in the toolbar and menus.
- Prefer system-provided SF Symbols-style icons, standard control sizes,
  native selection colors, and accessible contrast.
- Avoid hard divider lines for major panes. Use macOS-style material changes,
  scroll backgrounds, spacing, and subtle shadows to separate the sidebar,
  content, inspector, and filmstrip.
- Keep toolbar icons semantically consistent with SF Symbols: analyze should
  read as inspect/search, approve as a checked circle, inspector as a split
  panel, and export as an arrow leaving a tray.
- Keep command controls visually consistent. Sidebar import actions should use
  the same native control treatment as other secondary buttons: icon plus label,
  clear hit area, no floating text-only affordances.
- Display inspector metrics as label, value, then control. For confidence, put
  the percentage value beside the `CONFIDENCE` label and keep the progress bar
  on its own row so the text never overlaps the bar.
- Use one status-marker language in the filmstrip: a selected item gets a small
  accent bar, review items get an amber dot with an exclamation mark, approved
  items get green dots, exported items get blue dots, and failed items get red
  dots. Avoid mixing text pills with dots.
- Treat the filmstrip as a bottom pane inside the main content area, not as a
  floating overlay above the window. It should share the central content
  coordinate system and be separated by material contrast and spacing.
- Design for resizing: keep the central preview stable, collapse or hide the
  inspector first, then compact the sidebar if the window becomes narrow.

Official references used:

- Apple Human Interface Guidelines overview:
  `https://developer.apple.com/design/human-interface-guidelines/`
- Designing for macOS:
  `https://developer.apple.com/design/human-interface-guidelines/designing-for-macos`
- Toolbars:
  `https://developer.apple.com/design/human-interface-guidelines/toolbars`
- Sidebars:
  `https://developer.apple.com/design/human-interface-guidelines/sidebars`
- Panels:
  `https://developer.apple.com/design/human-interface-guidelines/panels`
- Layout:
  `https://developer.apple.com/design/human-interface-guidelines/layout`
- Materials:
  `https://developer.apple.com/design/human-interface-guidelines/materials`
- Apple Design Resources:
  `https://developer.apple.com/design/resources/`

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
   - Confidence percent
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

Use a light, precise macOS workspace rather than a heavy darkroom UI. The
existing app icon is dark with blue-gray crop geometry, so the interface should
reuse that blue-gray as a restrained brand accent while relying mostly on
system-like neutrals.

- App background: `#eef2f7`
- Panel background: `#ffffff`
- Secondary panel background: `#f7f9fc`
- Canvas background: `#f4f6f9`
- Border: `#d8dee8`
- Primary text: `#1f2937`
- Secondary text: `#667085`
- Muted text: `#98a2b3`
- Brand blue-gray: `#7f93b6`
- Primary action: `#3d6fb6`
- Approved green: `#2f9e62`
- Review amber: `#d89b18`
- Failed red: `#d94a42`
- Crop blue: `#3d8bfd`
- Outer green: `#22a06b`
- Split red: `#e85d5d`
- Grid violet: `#8b6fd6`

Keep controls compact, but give panes more breathing room than the current
form-heavy UI. The tone should be calm and lightweight: closer to a native
macOS production tool than a dark photo editor clone.

For the mockup and future implementation, avoid drawing explicit borders around
every pane or button. Prefer native-looking fills, materials, grouped controls,
and selection backgrounds; reserve strong lines for crop overlays because those
are part of the image editing task.

## Main Actions

Toolbar actions:

- Sidebar toggle
- Library / Review / Export segmented mode picker
- Previous / Next
- Analyze
- Reanalyze
- Approve
- Inspector toggle
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

`confidence_percent` is an integer from 0 to 100. The UI should always display
confidence as a percentage, for example `56%`, never as a normalized 0-1 value.

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
