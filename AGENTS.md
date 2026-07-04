# Codex Agent Rules

This is the coordination file for this repository. Keep it short and binding:
standing rules, document roles, release rules, verification priorities, and the
latest handoff. Do not use this file for changelog entries or architecture
detail.

## First Moves

1. Read `README.md` and this handoff before editing.
2. Check branch and dirty state:

```bash
git branch --show-current
git status --short
```

3. Treat GitHub as authoritative for source and docs. NAS or local copied folders
   are only transport/testing surfaces.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Document Roles

- `快速启动_Quick_Start.md`: Release quick-start guide.
- `README.md`: complete user manual for setup, launchers, Debug Analysis,
  outputs, review folders, and common command-line use.
- `ARCHITECTURE.md`: developer source map, policy ownership, format/mode
  isolation, and verification boundaries.
- `CHANGELOG.md`: version summaries, behavior changes, validation notes, and
  rollback context.
- `AGENTS.md`: Codex coordination rules and current handoff only.

Do not duplicate long content across these documents. Link to the right document
instead.

Documentation style must be professional, concise, and restrained. Avoid
colloquial phrasing, duplicated historical detail, and cross-document overlap.

## Current Scope

- Active entry point: `X5_Crop.py`.
- Active script version: V4.9.
- Current stable GitHub Release: `v4.2.8`.
- V4+ development source lives under `x5crop/`; Release builds may package a
  standalone `X5_Crop.py`.
- Keep active work focused on the standalone X5 Crop workflow unless the user
  explicitly resumes app/native packaging.
- There is no `docs/` mirror. Root `ARCHITECTURE.md` is the single architecture
  document.

## Coding Rules

- Preserve TIFF quality and metadata behavior unless the user explicitly asks
  otherwise. Cropped TIFF output must keep bit depth, channel structure,
  ICC/color space, resolution, metadata, and known lossless compression behavior.
- Keep detection changes conservative and sample-driven.
- Do not broadly loosen PASS/REVIEW rules to fix one file.
- For detection changes, verify known-good formats before calling the change
  safe, especially `135`.
- Use `--deskew off` for fast detector regressions unless the task is about
  export or deskew behavior.
- Directional requests use horizontal-strip wording as baseline. Add rotated
  vertical-strip behavior when implementing.
- Update user docs when usage, setup, output folders, launcher behavior, or
  release packaging changes.
- Update `ARCHITECTURE.md` when source layering, policy ownership, or
  verification boundaries change.
- Update `CHANGELOG.md` when behavior, release packaging, validation scope, or
  rollback context changes.

## Completion And Sync

- When the user asks Codex to change repository source, docs, config, launchers,
  or release metadata, finish by verifying, committing, and pushing to GitHub
  unless the user explicitly says not to.
- Do not require the user to restate "push" or "sync" in later sessions.
- Before committing, run the relevant checks and confirm `git status --short`
  contains only intentional changes.
- Push the current branch to `origin` after a successful commit.
- If commit or push cannot complete, report the blocker clearly and leave the
  working tree in the safest possible state.

## Git And Local Files

- Commit only intentional source/docs/config changes.
- Check `git status --short` before and after edits.
- Other Codex sessions may have changed files. Do not revert user or
  other-session changes unless explicitly asked.
- Keep `.gitignore` visible. If `.github/` appears, keep it visible too.
- Intended sparse checkout:

```text
/*
!/archive/
!/install/
!/release/
!/LICENSE
```

- Keep `tools/` available locally; it contains regression and build utilities
  used by active verification. Keep `LICENSE`, `archive/`, `install/`, and
  `release/` cloud/GitHub only locally unless the user asks to expand them.
- Do not commit generated/local files:
  - `.venv/`, `.venv-build/`, `build/`, `dist/`, `release/`
  - `__pycache__/`, `.DS_Store`, `downloaded_apps/`
  - `Test/`
  - generated `x5_crop_output/`
  - large TIFF samples unless explicitly made official fixtures with Git LFS

## Release Package Rules

User Release zip should contain only:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/X5_Crop_Mac_install.command
install/X5_Crop_win_install.bat
install/X5_Crop_Mac_uninstall.command
install/X5_Crop_win_uninstall.bat
```

Do not package `x5crop/`, `archive/`, `CHANGELOG.md`, `AGENTS.md`, `LICENSE`,
`.github/`, diagnostics launchers, Test files, or generated outputs unless the
user changes this policy.

Use Python `zipfile` for release zips so Chinese filenames are stored with
UTF-8 metadata.

macOS installer behavior:

- `chmod +x` the main macOS launcher and installer.
- Remove `com.apple.quarantine` from the current Release folder when `xattr` is
  available.
- This is per-folder preparation, not permanent global trust registration.

## Regression Priorities

When detection changes are made, prefer V4.9 classification with
`python3 -m tools.regression.reference_classify --candidate-root <root>`. Use
`python3 -m tools.regression.compare` when raw field diffs are needed.

Core fields to protect:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

Key local sets:

- `Test/135` full: core safety baseline.
- `Test/new_135` full: wide 135 spacing examples.
- `Test/半格/full` and `Test/半格/partial`: half-frame gate and partial behavior.
- `Test/120/66` full/partial: wide-separator / separator-derived outer behavior.
- `Test/120/67` full: 120-67 baseline.

For source or policy changes, also run:

```bash
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

Also compile `tools/regression/*.py`.

For docs-only changes, `git diff --check` and a final status review are enough
unless the edit changes commands or release behavior.

## Current Handoff

Date: 2026-07-02
Computer: primary macOS machine
Branch: main
Latest documentation state: root documents have distinct responsibilities;
`ARCHITECTURE.md` is the single architecture guide and no `docs/` mirror is kept.

Current state:

- Active script is `X5_Crop.py` V4.9.
- V4.9 is an evidence-governed policy reset over the V4.7 source layout, not
  a detector-loosening release.
- Source layout is layered: thin entry, package implementation, explicit format
  physical specs, semantic decision contract, focused
  detection modules, split geometry helpers, and explicit report/debug/regression
  surfaces.
- Detailed source layering and policy boundaries live in `ARCHITECTURE.md`.
- Version history and validation summaries live in `CHANGELOG.md`.
- User setup and usage live in `README.md` and `快速启动_Quick_Start.md`.

Recent verified baseline:

- `python3 X5_Crop.py --version` printed `X5_Crop.py 4.9`.
- Full py_compile across the V4.9 package passed.
- `git diff --check` passed.
- Decision contract policy smoke passed for 14 format / strip-mode combinations.
- Seven local V4.5.4 reference sets produced 0 `unacceptable_wrong_pass` and 0
  `risky_regression` with `python3 -m tools.regression.reference_classify`.
- V4.9 no longer treats V4.5.4 as a mandatory 0-diff oracle; conservative
  REVIEW and schema/reason diffs must be explained, while new wrong PASS is
  unacceptable.
