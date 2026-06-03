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
- Moved PASS/REVIEW confidence text out of the image area into a top status bar
  for both Debug and DebugAnalysis JPGs.
- Reduced debug overlay clutter: real detected separator regions still draw as
  red marks, while grid/equal/fallback separators draw only short edge ticks.
- Suppressed inferred separator ticks that overlap a real detected separator.
- Updated `README.md` to describe the external status bar and short tick marks.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran standalone `--debug --dry-run --format 135 --no-copy-review-files` on
  `Test/135负片/正常/001.tif`; visually confirmed the REVIEW status bar is
  outside the image and inferred separator marks are shorter edge ticks.
- Ran `--debug-analysis --dry-run --format 135 --no-copy-review-files` on the
  same sample; visually confirmed the combined JPG uses a top status bar and a
  short `Debug boxes | REVIEW` panel label.

Not verified:
- Did not change or retest enhanced-analysis selection behavior.
- Did not run Windows `.bat` launchers after this debug visualization change.
- Did not run a non-dry-run export after this visualization-only change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_debug_layout_fix`
- `/private/tmp/x5crop_debug_analysis_layout_fix`
- `/private/tmp/x5crop_debug_analysis_layout_fix2`

Next recommended step:
- Copy the updated root `X5_Split_v18.py` into any standalone test folder before
  rerunning launchers there; `Test/135负片/正常` currently contains its own script
  copy.
- Revisit enhanced-analysis auto-selection separately; this change intentionally
  only touched debug visualization.
