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

Date: 2026-06-05
Computer: primary macOS machine
Branch: main
Last commit: see `git log -1`

Changed:
- Active script is `X5_Crop.py` V3.1.1.
- V3.1.1 is based on the recovered V3 baseline, with the simplified terminal
  output retained.
- `separator_derived_outer` is intentionally narrow: it is considered only for
  full strips when ordinary outer candidates are unstable, a reliable white
  outer is missing, outer alignment is already suspicious, or grid/model gaps
  suggest the initial outer may be shifted. The derived outer still only
  competes with normal candidates and cannot expand to full canvas or shift too
  far.
- The `X5_00036` failure shape is guarded by
  `135_leading_grid_separator_failure`: three leading low-score grid separators,
  no accepted enhanced separator, and only adjacent late hard separators.
- Full-strip separator candidates that already pass the V2 auto gate now skip
  generating an extra content-only candidate, because the separator calibration
  has already checked content support.
- README now has one consolidated Chinese Debug Analysis section instead of two
  overlapping sections.

Verified:
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n X5_Crop_Mac.command install/X5_Crop_Mac_install.command`
- `python3 X5_Crop.py --version` prints `X5_Crop.py 3.1.1`.
- Current V3.1.1 Test/135 reference dry-run before this cleanup produced 43
  `approved_auto` / 5 `needs_review`; compared with V3, only `X5_00036`
  changed to review, while the V3.1 false-review files returned to pass.
- Focus fresh dry-run on `X5_00007`, `X5_00022`, `X5_00032`, `X5_00036`,
  `X5_00038`, `X5_00051`, and `X5_00052` produced 6 `approved_auto` and
  `X5_00036` as the only `needs_review`.
- The focused reports show full-strip candidates that pass the separator auto
  gate record `content_candidate_skipped=separator_auto_gate_passed`.

Not verified:
- A fresh full Test/135 batch after this cleanup has not been run yet; only the
  focused regression set above was run.
- Windows launcher was inspected but not executed on Windows in this turn.

Known local-only files:
- `Test/`
- Temporary verification outputs under `/private/tmp/`.

Next recommended step:
- Run a focused fresh dry-run on `Test/135` target files after any detection
  change: `X5_00007`, `X5_00022`, `X5_00032`, `X5_00036`, `X5_00038`,
  `X5_00051`, and `X5_00052`.
- For speed work, the largest current cost is full-resolution deskew rotation,
  followed by 135 edge-pair refinement and enhanced separator profiles across
  multiple outer candidates.
