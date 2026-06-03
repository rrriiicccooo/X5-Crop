# Codex Agent Rules

This is the single Codex coordination file for this repository. Keep standing
rules, sync notes, and the current handoff here.

## First Moves

1. Read `README.md` and the current handoff at the bottom of this file.
2. Check the current branch and dirty state before editing:

```bash
git branch --show-current
git status --short
```

3. If the folder is NAS-synced or the branch is ahead/behind, inspect the
   situation before editing. GitHub is authoritative for source and docs; NAS is
   only a local-file transport layer.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Current Scope

The app/native packaging direction is paused. Keep active work focused on the
standalone script workflow unless the user explicitly resumes the app direction:

```text
X5_Crop.py
archive/X5_Split_v17.py
archive/X5_Split_v18.py
```

Keep `X5_Crop.py` as the active script. Keep `X5_Split_v17.py` and
`X5_Split_v18.py` in `archive/` as preserved references. Keep user-facing
project documentation consolidated in `README.md`.

## Coding Rules

- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Keep detection changes close to the script logic.
- Avoid broad refactors while solving a narrow detection or workflow task.
- Add or update docs when script usage, setup, or testing behavior changes.
- When the user describes directional behavior with left/right or top/bottom,
  treat that as the horizontal-strip baseline unless they say otherwise, and
  add the rotated vertical-strip behavior too.

## Git Rules

- Commit only intentional source/docs/config changes.
- If the working tree is NAS-synced, check `git status --short` before and
  after edits because another computer may have synchronized changes into the
  folder.
- Do not run two Codex sessions against the same NAS-synced working tree at the
  same time unless they are only reading.
- Do not commit local generated files or folders such as:
  - `.venv/`
  - `.venv-build/`
  - `build/`
  - `dist/`
  - `release/`
  - `__pycache__/`
  - `.DS_Store`
  - `downloaded_apps/`
  - `Test/`
  - generated `split_output/` folders
- Do not commit large TIFF samples unless the user explicitly decides they are
  official fixtures and Git LFS tracking is configured for them.

## Handoff Rule

When stopping work after source/docs changes, update the current handoff below.

Template:

```text
Date:
Computer:
Branch:
Last commit:

Changed:
- 

Verified:
- 

Not verified:
- 

Known local-only files:
- 

Next recommended step:
- 
```

## Current Handoff

Date: 2026-06-03
Computer: primary macOS machine
Branch: main
Last commit: see `git log -1` after this handoff commit

Changed:
- Analyzed all 79 top-level TIFF samples under `Test/` as downsampled evidence
  material for the current detector.
- Confirmed raw content-run count is unstable on real samples: internal scene
  texture can split one frame into several content peaks, while low-texture or
  dark frames can merge several frames into one weak content run.
- Kept content evidence as the primary direction, but made the selector more
  explicitly joint: a separator candidate can win when it passes threshold, is
  supported by content evidence, and the content-primary candidate is ambiguous,
  below threshold, or smaller.
- Added a conservative auto-mode safeguard so a high-scoring partial candidate
  cannot automatically steal the result from a still-plausible full-strip
  candidate. In that case the full-strip model is returned for review with
  `partial_competes_with_plausible_full_strip`.
- Created active `X5_Crop.py` V1 from the latest v18 baseline.
- Added a conservative content-evidence layer using a composite score from local
  gradient, neighbor texture, local contrast, and tonal presence.
- DebugAnalysis is now a four-panel JPG: debug boxes, original gray, separator
  evidence, and content evidence.
- Removed standalone Debug launchers; keep normal launchers and DebugAnalysis
  launchers only.
- Plain debug previews now show only the status bar, green outer box, and
  semi-transparent crop-area fills. Colored separator marks are drawn in the
  DebugAnalysis Separator evidence panel.
- DebugAnalysis order is now Original gray, Debug boxes, Separator evidence,
  Content evidence.
- Debug boxes now use different semi-transparent fills for each crop area instead
  of blue outlines.
- Moved v17/v18 reference scripts into `archive/`.
- Simplified launcher names to `X5_Crop_Mac.command`,
  `X5_Crop_Mac_debug.command`, `X5_Crop_win.bat`, and
  `X5_Crop_win_debug.bat`.
- Default bleed is now long-axis 15px and short-axis 10px: horizontal strips are
  left/right 15px and top/bottom 10px; vertical strips are top/bottom 15px and
  left/right 10px.
- Detection is now content-primary: content evidence builds the crop candidate
  first, while the older separator-based detector is retained as
  `separator_assist` report data and fallback.
- Content candidate ranking now prefers more complete frame models when
  candidates are above threshold, so a tiny high-scoring partial does not steal
  the result from a plausible larger sequence.
- Partial strips are no longer capped below the auto-export threshold just for
  being partial; they can pass when content, aspect, and supporting evidence are
  strong enough.
- Content-primary candidates with mismatched content run counts are capped below
  the auto-export threshold and marked for review.
- Content evidence is written into reports and can conservatively downgrade
  clear content/aspect conflicts, but it does not raise difficult files into
  automatic export.
- Removed v18 launchers and added cleaner `X5_Crop_*` macOS and Windows
  launchers.
- Rewrote `README.md` as the current Chinese user guide for X5 Crop V1.

Verified:
- Built a Test contact sheet at `/private/tmp/x5crop_test_contact_sheet.jpg` for
  representative samples including `X5_test_1.tif`, `2.tif`, `3.tif`, `5.tif`,
  `9.tif`, `11.tif`, `19.tif`, `20.tif`, `22.tif`, `25.tif`, `43.tif`,
  `44.tif`, `48.tif`, `53.tif`, `72.tif`, `73.tif`, `74.tif`, `75.tif`,
  `77.tif`, and `79.tif`.
- Wrote the all-Test downsampled content summary to
  `/private/tmp/x5crop_test_content_run_summary.json`.
- Confirmed `Test/X5_test_43.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_44.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_19.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed `Test/X5_test_25.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed narrow/difficult `Test/X5_test_72.tif` and `X5_test_74.tif` remain
  `needs_review` rather than being promoted by content evidence.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n X5_Crop_Mac.command X5_Crop_Mac_debug.command`
- `python3 X5_Crop.py --version`
- `python3 X5_Crop.py --help`
- Verified vertical bleed mapping with `Box.expand(15, 10, ...)` plus
  `map_work_box(..., "vertical", ...)`: long-axis bleed maps to original
  top/bottom, short-axis bleed maps to original left/right.
- Ran content-primary dry-runs on `Test/X5_test_19.tif`, `25.tif`, `31.tif`,
  `20.tif`, `22.tif`, `23.tif`, and `30.tif`; reports show
  `analysis_source=content_primary` with separator data under
  `separator_assist`.
- Confirmed `X5_test_25.tif` is forced to `needs_review` when content detects 7
  usable runs for a 6-frame target (`content_run_count_mismatch`), even though
  separator assist passes.
- After removing the partial-strip cap and adding content-specific ranking,
  confirmed `X5_test_19.tif` selects 3 frames and passes, `X5_test_20.tif`
  selects 5 frames and passes, while `X5_test_25.tif` remains review for run
  count mismatch.
- Ran DebugAnalysis dry-runs on `Test/135负片/正常/001.tif`, `11.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` remains `needs_review` at confidence `0.676` and produces
  a four-panel DebugAnalysis JPG.
- Re-ran DebugAnalysis for `001.tif` and visually confirmed colored separator
  marks moved to the Separator evidence panel while Debug boxes stayed clean.
- Re-ran DebugAnalysis for `001.tif` after panel reordering and visually
  confirmed the order is Original gray, Debug boxes, Separator evidence, Content
  evidence, with semi-transparent crop fills in Debug boxes.
- Ran `--debug` on `001.tif` and visually confirmed the standalone debug JPG now
  only shows the status bar, outer box, and crop boxes.
- Confirmed `11.tif` remains `approved_auto` at confidence `0.963`.
- Confirmed `X5 022.tif` remains `needs_review` at confidence `0.679`.
- Inspected the generated `001.tif` DebugAnalysis JPG and confirmed the fourth
  `Content evidence` panel is present.

Not verified:
- Did not run Windows `.bat` launchers on Windows.
- Did not run a non-dry-run TIFF export after creating X5 Crop V1.
- Did not create hand-labeled ground-truth fixtures for all `Test/` images; this
  pass used visual inspection plus representative dry-runs.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v1_debug_001`
- `/private/tmp/x5crop_v1_debug_11`
- `/private/tmp/x5crop_v1_debug_11b`
- `/private/tmp/x5crop_v1_debug_x5022`
- `/private/tmp/x5crop_debuganalysis_only_001`
- `/private/tmp/x5crop_clean_debug_001`
- `/private/tmp/x5crop_reordered_panels_001`
- `/private/tmp/x5crop_content_primary_19`
- `/private/tmp/x5crop_content_primary_25`
- `/private/tmp/x5crop_content_primary_31`
- `/private/tmp/x5crop_content_primary_19b`
- `/private/tmp/x5crop_content_primary_25b`
- `/private/tmp/x5crop_content_primary_batch`
- `/private/tmp/x5crop_joint_score_19`
- `/private/tmp/x5crop_joint_score_20`
- `/private/tmp/x5crop_joint_score_25`
- `/private/tmp/x5crop_joint_score_19b`
- `/private/tmp/x5crop_joint_score_20b`
- `/private/tmp/x5crop_joint_score_25c`
- `/private/tmp/x5crop_test_contact_sheet.jpg`
- `/private/tmp/x5crop_test_content_run_summary.json`
- `/private/tmp/x5crop_joint_model_19b`
- `/private/tmp/x5crop_joint_model_25b`
- `/private/tmp/x5crop_joint_model_43c_debug`
- `/private/tmp/x5crop_joint_model_44b`
- `/private/tmp/x5crop_joint_model_72b`
- `/private/tmp/x5crop_joint_model_74b`

Next recommended step:
- Continue turning visually reviewed Test samples into a small hand-labeled
  regression fixture set, especially vertical 120 and narrow 135/xpan-like
  strips, so future detector changes can be measured against expected counts.
