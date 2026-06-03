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
- Reworked v18 analysis so enhanced imagery no longer reruns full detection or
  replaces the base result.
- Analysis now keeps the base outer box fixed and only uses separator evidence
  inside that outer box to supplement weak gap candidates.
- Added `enhanced-detected` gap accounting and orange debug marks for separator
  evidence accepted from the fixed-outer analysis layer.
- DebugAnalysis now shows `Separator evidence` instead of `Enhanced gray`.
- Updated CLI help and `README.md` to describe separator evidence behavior.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran dry-run reports on `Test/135负片/正常/001.tif`, `11.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` remains `needs_review` with base/enhanced/grid/equal
  counts `1/0/0/4`; no separator evidence was accepted.
- Confirmed `11.tif` remains `approved_auto` with counts `2/0/3/0`.
- Confirmed `X5 022.tif` remains `needs_review` with counts `0/0/0/5`; no
  separator evidence was accepted.
- Generated DebugAnalysis for `001.tif` and visually confirmed the third panel
  is labeled `Separator evidence`.

Not verified:
- Did not find a sample in this pass where separator evidence was accepted, so
  the orange `enhanced-detected` overlay path is code-reviewed but not visually
  exercised on a real accepted case.
- Did not run Windows `.bat` launchers after this analysis-layer change.
- Did not run a non-dry-run export after this analysis-layer change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_separator_evidence_sample`
- `/private/tmp/x5crop_separator_evidence_sample2`
- `/private/tmp/x5crop_separator_evidence_debug`

Next recommended step:
- Copy the updated root `X5_Split_v18.py` into any standalone test folder before
  rerunning launchers there; `Test/135负片/正常` currently contains its own script
  copy.
- Run DebugAnalysis on known weak-separator samples to see whether any orange
  `enhanced-detected` evidence is accepted and whether its visual mark is useful.
