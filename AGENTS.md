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
X5_Split_v17.py
X5_Split_v18.py
```

Keep `X5_Crop.py` as the active script. Keep `X5_Split_v17.py` and
`X5_Split_v18.py` in the repository as preserved references. Keep user-facing
project documentation consolidated in `README.md`.

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
- Created active `X5_Crop.py` V1 from the latest v18 baseline.
- Added a conservative content-evidence layer using a composite score from local
  gradient, neighbor texture, local contrast, and tonal presence.
- DebugAnalysis is now a four-panel JPG: debug boxes, original gray, separator
  evidence, and content evidence.
- Removed standalone Debug launchers; keep normal launchers and DebugAnalysis
  launchers only.
- Plain debug previews now show only the status bar, green outer box, and blue
  crop boxes. Colored separator marks are drawn in the DebugAnalysis Separator
  evidence panel.
- Default bleed is now 15px left/right and 10px top/bottom.
- Content evidence is written into reports and can conservatively downgrade
  clear content/aspect conflicts, but it does not raise difficult files into
  automatic export.
- Removed v18 launchers and added cleaner `X5_Crop_*` macOS and Windows
  launchers.
- Rewrote `README.md` as the current Chinese user guide for X5 Crop V1.

Verified:
- `python3 -m py_compile X5_Crop.py X5_Split_v17.py X5_Split_v18.py`
- `bash -n X5_Crop_macOS.command X5_Crop_macOS_DebugAnalysis.command`
- `python3 X5_Crop.py --version`
- `python3 X5_Crop.py --help`
- Ran DebugAnalysis dry-runs on `Test/135负片/正常/001.tif`, `11.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` remains `needs_review` at confidence `0.676` and produces
  a four-panel DebugAnalysis JPG.
- Re-ran DebugAnalysis for `001.tif` and visually confirmed colored separator
  marks moved to the Separator evidence panel while Debug boxes stayed clean.
- Ran `--debug` on `001.tif` and visually confirmed the standalone debug JPG now
  only shows the status bar, outer box, and crop boxes.
- Confirmed `11.tif` remains `approved_auto` at confidence `0.963`.
- Confirmed `X5 022.tif` remains `needs_review` at confidence `0.679`.
- Inspected the generated `001.tif` DebugAnalysis JPG and confirmed the fourth
  `Content evidence` panel is present.

Not verified:
- Did not run Windows `.bat` launchers on Windows.
- Did not run a non-dry-run TIFF export after creating X5 Crop V1.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v1_debug_001`
- `/private/tmp/x5crop_v1_debug_11`
- `/private/tmp/x5crop_v1_debug_11b`
- `/private/tmp/x5crop_v1_debug_x5022`
- `/private/tmp/x5crop_debuganalysis_only_001`
- `/private/tmp/x5crop_clean_debug_001`

Next recommended step:
- Run DebugAnalysis on difficult weak-separator and partial-strip samples and
  confirm the content evidence panel is useful without loosening auto-export.
