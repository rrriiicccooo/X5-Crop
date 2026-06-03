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
X5_Split_v17.py
X5_Split_v18.py
```

Keep `X5_Split_v17.py` in the repository as the preserved v17 reference. Keep
user-facing project documentation consolidated in `README.md`.

## Coding Rules

- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Keep detection changes close to the script logic.
- Avoid broad refactors while solving a narrow detection or workflow task.
- Add or update docs when script usage, setup, or testing behavior changes.

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
- Tightened v18 outer-candidate selection so near-full-canvas boxes are ignored
  when smaller valid strip candidates exist.
- Tightened 135 confidence scoring so very even geometry no longer auto-passes
  when too many separators are equal/fallback splits or too few real separators
  were detected.
- Debug and DebugAnalysis JPGs now show a PASS/REVIEW confidence badge in the
  image itself.
- Detected separator marks now preserve and draw the detected separator band
  width where available, instead of always drawing a single line.
- Updated `README.md` to explain PASS/REVIEW badges and the difference between
  red detected separator regions and yellow/purple inferred cut lines.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran `--debug-analysis --dry-run --format 135 --no-copy-review-files` against
  samples from `Test/135负片/正常`: `001.tif`, `11.tif`, `15.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` changed from previous approved behavior to
  `needs_review` with `mostly_equal_split` and
  `too_few_detected_separators`.
- Confirmed `X5 022.tif` becomes `needs_review` when all five separators are
  equal/fallback splits.
- Confirmed `11.tif` and `15.tif` still pass with smaller non-full outer boxes
  and two real detected separators plus grid-derived separators.
- Visually inspected generated DebugAnalysis JPGs for `001.tif` and `11.tif`;
  PASS/REVIEW badges are visible and red detected separators are drawn as
  regions where width data exists.
- Ran standalone `--debug --dry-run` on `001.tif` and confirmed the `_debug`
  JPG also includes the REVIEW badge.

Not verified:
- Did not run Windows `.bat` launchers after this color/doc change.
- Did not complete a full-directory run over all `Test/135负片/正常` samples;
  the first full run was stopped because it was taking too long.
- Did not run a non-dry-run export after this confidence change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_sample_v18_fix`
- `/private/tmp/x5crop_sample_v18_debug_fix`

Next recommended step:
- Copy the updated root `X5_Split_v18.py` into any standalone test folder before
  rerunning launchers there; `Test/135负片/正常` currently contains its own script
  copy.
- Run a focused real export on known-good samples after reviewing DebugAnalysis
  output.
