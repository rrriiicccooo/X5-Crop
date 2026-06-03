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
- Removed PASS/REVIEW from the DebugAnalysis `Debug boxes` panel title; the
  complete status now appears only in the top status bar.
- Made the top status bar easier to scan by rendering PASS/REVIEW larger and in
  distinct colors before the confidence details.
- Updated `README.md` to describe the more prominent status text.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran `--debug-analysis --dry-run --format 135 --no-copy-review-files` on
  `Test/135负片/正常/001.tif`; visually confirmed the panel title is just
  `Debug boxes` and REVIEW is only in the red top status bar.
- Ran standalone `--debug --dry-run --format 135 --no-copy-review-files` on
  `Test/135负片/正常/11.tif`; visually confirmed PASS renders in green with
  larger status text.

Not verified:
- Did not change or retest enhanced-analysis selection behavior.
- Did not run Windows `.bat` launchers after this debug visualization change.
- Did not run a non-dry-run export after this visualization-only change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_status_bar_review`
- `/private/tmp/x5crop_status_bar_pass`

Next recommended step:
- Copy the updated root `X5_Split_v18.py` into any standalone test folder before
  rerunning launchers there; `Test/135负片/正常` currently contains its own script
  copy.
- Revisit enhanced-analysis auto-selection separately; this change intentionally
  only touched debug visualization.
