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
- Added a conservative v17-style `edge-pair` refinement path for 135 full strips.
  It only replaces a gap when the base image has a strong pair of vertical edges
  around a narrow background-like separator region.
- Added conservative same-frame-size fitting for 135 full strips. It requires at
  least two trusted edge samples and only changes output boxes; confidence is
  still scored from the pre-fit boxes to avoid false PASS decisions.
- Debug red separator marks now include `edge-pair` regions.
- Updated `README.md` to explain red `edge-pair` evidence and same-frame-size
  fitting.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran dry-run reports on `Test/135负片/正常/001.tif`, `11.tif`, `15.tif`, and
  `X5 022.tif`.
- Confirmed weak samples still do not auto-pass: `001.tif` stays
  `needs_review` with methods `equal/equal/equal/edge-pair/equal`; `X5 022.tif`
  stays `needs_review` with methods `equal/equal/equal/equal/edge-pair`.
- Confirmed normal samples still auto-pass: `11.tif` and `15.tif` both use five
  `edge-pair` separators and same-frame-size fitting.
- Generated DebugAnalysis for `X5 022.tif` and visually confirmed the REVIEW
  status and red edge-pair separator region.

Not verified:
- Did not run Windows `.bat` launchers after this detection change.
- Did not run a non-dry-run export after this detection change.
- Did not run the full `Test/135负片/正常` directory after this change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_edge_frame_fit_sample`
- `/private/tmp/x5crop_edge_frame_fit_debug`
- `/private/tmp/x5crop_edge_frame_fit_debug2`

Next recommended step:
- Copy the updated root `X5_Split_v18.py` into any standalone test folder before
  rerunning launchers there; `Test/135负片/正常` currently contains its own script
  copy.
- Run DebugAnalysis on additional difficult weak-separator samples and confirm
  new `edge-pair` evidence does not push questionable files over the confidence
  threshold.
