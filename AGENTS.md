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
- Changed DebugAnalysis mode so it no longer creates a separate `_debug/`
  folder or standalone `*_debug.jpg`.
- DebugAnalysis launchers now pass only `--debug-analysis`, not `--debug`.
- Script-level behavior now suppresses standalone debug preview output whenever
  `--debug-analysis` is enabled, even if both flags are passed manually.
- Updated `README.md` to explain that the DebugAnalysis JPG already includes the
  debug boxes panel.

Verified:
- `bash -n X5_Split_v18_macOS.command X5_Split_v18_macOS_Debug.command
  X5_Split_v18_macOS_DebugAnalysis.command`
- `python3 -m py_compile X5_Split_v18.py`
- Ran `--debug-analysis --dry-run` on a synthetic TIFF in
  `/private/tmp/x5crop_v18_analysis_only_test`; confirmed only
  `_debug_analysis/*_debug_analysis.jpg` was written and `_debug/` was not
  created.
- Ran `--debug --dry-run` on a synthetic TIFF in
  `/private/tmp/x5crop_v18_debug_only_test`; confirmed `_debug/*_debug.jpg` was
  still written and `_debug_analysis/` was not created.
- Searched README and launchers for stale `--debug --debug-analysis` and
  duplicate `_debug` messaging in DebugAnalysis mode.

Not verified:
- Did not run against real local `Test/` TIFF samples.
- Did not run Windows `.bat` launchers after this behavior change.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_v18_analysis_only_test`
- `/private/tmp/x5crop_v18_debug_only_test`

Next recommended step:
- Run the DebugAnalysis launcher on a real difficult TIFF and confirm only the
  combined JPG is produced.
