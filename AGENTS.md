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
- Aligned the v18 debug overlay base colors with v17: green outer strip frame,
  blue output crop boxes, and red image-detected separator lines.
- Kept v18-only separator colors for newer inference methods: yellow for grid
  spacing, purple for equal/fallback spacing, and white for unknown/other
  sources.
- Updated `README.md` to document the debug colors and to state that default
  exported TIFF crops keep the v17-style 10px bleed.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- Ran report dry-runs on a synthetic TIFF with default bleed and with
  `--bleed 0`; confirmed default frame boxes expand by 10px on each side, with
  clamping at image boundaries where needed.
- Ran `--debug --dry-run` on the synthetic TIFF and confirmed the JPG contains
  green outer-frame and blue crop-box pixels. The synthetic case did not produce
  image-detected separators, so red-line rendering was verified by code path.

Not verified:
- Did not run against real local `Test/` TIFF samples.
- Did not run Windows `.bat` launchers after this color/doc change.
- Did not complete a real export on the synthetic TIFF because its generated
  metadata trips the script's strict `ResolutionUnit` preservation check.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v18_bleed_color_test`

Next recommended step:
- Run the normal and Debug launchers on a real difficult TIFF to visually confirm
  crop bleed and separator colors on production-like input.
