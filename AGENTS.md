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
- Updated v18 DebugAnalysis panel layout to adapt to scan orientation.
- Horizontal scans now stack the three panels vertically: Debug boxes, Original
  gray, Enhanced gray.
- Vertical scans keep the three panels side-by-side in columns.
- Updated the Chinese `README.md` to describe the adaptive panel layout.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Created synthetic horizontal and vertical TIFF strips in
  `/private/tmp/x5crop_v18_adaptive_panel_test`.
- Ran v18 with `--debug-analysis --dry-run --confidence-threshold 1.0` on both
  files.
- Confirmed horizontal output size is `1650x666`, showing vertical stacking.
- Confirmed vertical output size is `564x1684`, showing side-by-side columns.
- Visually inspected both generated DebugAnalysis JPGs.

Not verified:
- Did not run against real local `Test/` TIFF samples.
- Did not run macOS/Windows double-click launchers after this script change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v18_adaptive_panel_test`

Next recommended step:
- Run a real difficult TIFF through `--debug --debug-analysis --dry-run` and
  inspect the adaptive combined JPG plus `needs_review/` copy.
