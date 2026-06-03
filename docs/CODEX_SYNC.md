# Codex Sync Guide

This project is expected to be edited and tested from more than one computer and more than one Codex session.

Use this file as the shared operating agreement.

## Shared Source of Truth

GitHub is the source of truth for code, docs, packaging scripts, and release workflow changes.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

Local machines may also contain:

- large TIFF test scans
- generated debug images
- downloaded GitHub Actions artifacts
- local virtual environments
- packaged app outputs

Those local files are useful, but they are not automatically part of the shared project state.

Some working folders may also be synchronized through NAS. Treat NAS sync as a way to move local files between machines, not as a replacement for Git history. Before editing source files in a NAS-synced folder, check whether the folder is a real Git clone and whether another machine has uncommitted work.

## NAS Two-Way Sync Rules

This project may exist in a folder that is synchronized through NAS in both directions.

That has two important consequences:

- GitHub remains the source of truth for source code, docs, workflows, and packaging scripts.
- NAS is a convenience layer for local files such as TIFF samples, downloaded apps, and generated outputs.

Do not rely on NAS sync as the only history for code changes. Always commit and push source/docs changes through Git before expecting another Codex session to continue safely.

Before editing on either computer:

```bash
git status --short
git branch --show-current
```

Then wait for NAS sync to finish if the file manager or NAS client still shows active syncing. A half-synced Git working tree can make files appear modified, missing, or stale.

Avoid simultaneous edits:

- Do not let two Codex sessions edit the same repository files at the same time in a two-way synced folder.
- If one computer is actively building or running tests, the other computer should avoid touching the same working tree until that task finishes.
- If both computers need to work at once, use separate Git branches and separate local clones instead of one shared NAS-synced working folder.

Do not synchronize or commit generated state as project truth:

- `.git/index.lock`
- `.venv/`
- `.venv-build/`
- `build/`
- `dist/`
- `release/`
- `__pycache__/`
- `.DS_Store`
- `downloaded_apps/`
- generated `split_output/` folders

If the NAS tool creates conflict files, pause and inspect before continuing. Do not delete conflict files blindly if they may contain source or docs edits from the other computer.

## Before Starting on Any Computer

Run:

```bash
git status --short
git branch --show-current
git fetch origin
```

Then compare with the remote branch you intend to work on:

```bash
git log --oneline --decorate --max-count=8 --all
```

If there are local uncommitted changes, inspect them before pulling. Do not overwrite another machine's work.

## Recommended Work Loop

1. Pull or fetch the latest remote state.
2. Read the newest handoff note in this file or in the chat.
3. Make a focused change.
4. Run the smallest useful verification.
5. Commit only intentional files.
6. Push the branch.
7. Leave a handoff note.

Useful commands:

```bash
git status --short
git diff --stat
git diff
git add README.md docs AGENTS.md
git commit -m "Document Codex collaboration workflow"
git push origin HEAD
```

Adjust the `git add` paths to match the actual files changed.

## Branch Strategy

Use `main` for stable shared state.

Use short-lived branches for active work:

```text
codex/<topic>
```

If work already exists on a branch such as `integrate-web-app`, continue there until it is merged or intentionally replaced.

Do not force-push unless both computers have confirmed that no local work will be lost.

## What To Commit

Commit:

- Python source in `x5crop/`
- packaging files in `packaging/`
- build scripts in `tools/`
- GitHub Actions workflows in `.github/workflows/`
- docs in `README.md`, `AGENTS.md`, and `docs/`
- preserved original script files:
  - `X5_Split_v17.py`
  - `README_X5_Split_v17.md`

Usually do not commit:

- `.DS_Store`
- `__pycache__/`
- `.venv/`
- `.venv-build/`
- `build/`
- `dist/`
- `release/`
- `downloaded_apps/`
- generated `split_output/` folders
- generated debug JPGs
- large TIFF samples in `Test/`

Large TIFF samples should only be committed after an explicit decision to make them official fixtures and after Git LFS tracking is configured.

## Git LFS

Git LFS is installed and globally enabled on the primary macOS machine.

Recommended tracking if official TIFF fixtures are later added:

```bash
git lfs track "*.tif"
git lfs track "*.tiff"
git add .gitattributes
```

Do not add all local test TIFFs by accident.

## GitHub CLI And SSH

The preferred GitHub transport is SSH.

Check:

```bash
ssh -T git@github.com
gh auth status
git remote -v
```

Expected remote shape:

```text
git@github.com:rrriiicccooo/X5-Crop.git
```

If `gh auth status` fails on a new computer, run:

```bash
gh auth login --hostname github.com --git-protocol ssh --web
```

## Handoff Template

Use this at the end of a session:

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

Date: 2026-06-02
Computer: primary macOS machine
Branch: integrate-web-app
Last commit: 0925665 Document NAS sync workflow

Changed:
- Added `docs/UI_REDESIGN_CAPTURE_ONE_LIGHTROOM.md` with a Capture One / Lightroom inspired review-workspace UI proposal.
- The proposal covers the three-panel layout, bottom filmstrip, review/export modes, visual style, shortcuts, CropPlan data needs, and a phased implementation plan.
- Added `native/`, a C++20 / Qt 6 native app shell implementing the first review-workspace UI pass.
- Installed Homebrew `cmake` and `qt` on the primary macOS machine to verify the native build.
- Updated the native shell to follow the revised macOS HIG-oriented light UI rules: native toolbar, sidebar and inspector toggles, light material palette, confidence percent row with progress bar, and unified filmstrip status markers.
- Aligned the actual native Qt UI more closely with `docs/assets/ui_redesign_mockup.svg`: toolbar title/actions, SOURCE/BATCH/QUEUE sidebar, review canvas header/note, inspector status/warning/crop-plan layout, filmstrip thumbnails, and queue thumbnails.

Verified:
- Read `README.md`, `docs/CODEX_SYNC.md`, `docs/PROJECT_CONTEXT.md`, current `x5crop/app.py`, `x5crop/core_bridge.py`, and the roadmap before writing the UI plan.
- Confirmed branch is `integrate-web-app`.
- Configured native CMake build with Qt 6.
- Built `native/build-arm64/X5 Crop.app` successfully on Apple Silicon.
- Launched the app and verified the main window renders the dark three-panel review workspace with bottom filmstrip and inspector.
- Rebuilt after the light macOS UI update with `./native/scripts/build_macos.sh`.
- Launched the rebuilt app and verified the toolbar, light panes, inspector, canvas, and filmstrip render.
- Rebuilt after the SVG mockup alignment with `./native/scripts/build_macos.sh`.

Not verified:
- Did not run the PySide6 app during native shell work.
- Did not build Windows or Intel macOS yet.

Known local-only files:
- `Test/`
- `downloaded_apps/`
- `__pycache__/`
- `.DS_Store`

NAS note:
- This project folder may be mirrored through two-way NAS sync. Git remains authoritative for source/docs changes; NAS is for local samples and artifacts.

Next recommended step:
- Implement native CropPlan JSON persistence next, then connect the Python engine bridge.

---

Date: 2026-06-03
Computer: Windows NAS-synced workspace
Branch: integrate-web-app
Last commit: 0925665 Document NAS sync workflow

Changed:
- Continued the standalone `X5_Split_v18.py` cleanup script work.
- Restored the remaining valuable v17-style detection safeguards into v18: robust grid fitting, grid-based outer refinement, gutter-preserving enhanced analysis, partial edge hints, richer candidate scoring, frame-size fit, stronger deskew candidate selection, deskew minimum pixel-span gate, output compression safety, packed bit-depth safety, source crop pixel validation, and debug crop previews.
- Kept rare formats manual-only for `half` and `xpan`; no dual-strip 135 support was restored.
- Follow-up omission audit found and fixed directory-input probing plus per-file `--format auto` / `--layout auto` / default count handling. Mixed-format directories no longer inherit the first TIFF's format, layout, or count.
- Follow-up omission audit also fixed true `SYX` planar RGB handling: spatial shape detection, deskew rotation, PlanarConfiguration preservation, and output validation now agree on planar TIFFs.
- Follow-up metadata audit added `SampleFormat` preservation validation, changed `--compression` default to `same`, and validates Compression when preserving known lossless source compression.
- Restored the useful v17 separator-scoring ideas into v18: vertical consistency, separator band width checks, side-guard prominence, and broad-region rejection. Added an internal white-only X-axis outer candidate to protect underexposed first/last frames from being trimmed as black border.
- Applied v17-style sampled percentile statistics for detection-only grayscale normalization, enhanced-analysis generation, and image-quality scoring. This reduces full-image percentile cost on large TIFFs without changing exported pixels.
- Added diagnostic and review-flow improvements: reports now include selected outer candidate, all outer candidates, candidate area spread, and gap methods; debug previews draw gap lines; partial strips try 0/0.25/0.5/0.75/1 offsets; low-confidence results get more specific reasons such as `likely_partial_strip`, `format_auto_low_confidence`, `outer_candidate_disagreement`, `deskew_uncertain`, and `120_separator_uncertain`.
- Added double-click launchers for v18: `X5_Split_v18_Windows_DoubleClick.bat` and `X5_Split_v18_macOS_DoubleClick.command`, plus `README_X5_Split_v18_DoubleClick.md`. Launchers process TIFF files in their own folder, write `split_output`, write reports, and do not overwrite existing outputs.
- Added `--debug-analysis` to v18 and double-click diagnostic launchers: `X5_Split_v18_Windows_Debug_DoubleClick.bat`, `X5_Split_v18_Windows_DebugAnalysis_DoubleClick.bat`, `X5_Split_v18_macOS_Debug_DoubleClick.command`, and `X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command`. Debug analysis writes base/enhanced detection PPM previews to `split_output/_debug_analysis`.

Verified:
- `py -3 -m py_compile X5_Split_v18.py`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off --report -o .codex_tmp\v18_all_135`
- `py -3 X5_Split_v18.py "Test\半格\X5 026.tif" --dry-run --deskew off --format half -o .codex_tmp\v18_all_half`
- `py -3 X5_Split_v18.py "Test\120 66负片\X5 001.tif" --dry-run --deskew off -o .codex_tmp\v18_all_120`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run -o .codex_tmp\v18_all_deskew`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --deskew off --overwrite -o .codex_tmp\v18_all_export`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off --debug -o .codex_tmp\v18_all_debug`
- `py -3 X5_Split_v18.py .codex_tmp\v18_mixed_auto --dry-run --deskew off -o .codex_tmp\v18_mixed_auto_out`
- Synthetic planar RGB TIFF export test with `photometric=rgb`, `planarconfig=separate`, and output readback validation.
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --deskew off --overwrite -o .codex_tmp\v18_meta_export`
- Synthetic planar RGB TIFF export test after adding `SampleFormat` and Compression validation.
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off -o .codex_tmp\v18_gap_135b`
- `py -3 X5_Split_v18.py "Test\120 66负片\X5 001.tif" --dry-run --deskew off -o .codex_tmp\v18_gap_120b`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --deskew off --overwrite -o .codex_tmp\v18_gap_export`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off -o .codex_tmp\v18_sample_135`
- `py -3 X5_Split_v18.py "Test\120 66负片\X5 001.tif" --dry-run --deskew off -o .codex_tmp\v18_sample_120`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --deskew off --overwrite -o .codex_tmp\v18_sample_export`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off --report -o .codex_tmp\v18_opt_135`
- `py -3 X5_Split_v18.py "Test\120 66负片\X5 001.tif" --dry-run --deskew off --report -o .codex_tmp\v18_opt_120`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --dry-run --deskew off --debug -o .codex_tmp\v18_opt_debug`
- `py -3 X5_Split_v18.py "Test\135负片\正常\001.tif" --deskew off --overwrite -o .codex_tmp\v18_opt_export`
- Windows launcher test in `.codex_tmp\doubleclick_win` with one copied 135 TIFF: `cmd /c "echo. | X5_Split_v18_Windows_DoubleClick.bat"` produced 6 crops and report successfully.
- Checked `X5_Split_v18_macOS_DoubleClick.command` contents and verified LF line endings; bash is not installed on this Windows machine, so `bash -n` was not run.
- `py -3 -m py_compile X5_Split_v18.py`
- Windows Debug launcher test in `.codex_tmp\debug_launchers`: `cmd /c "echo. | X5_Split_v18_Windows_Debug_DoubleClick.bat"` produced crops, report, and `_debug/001_debug.ppm`.
- Windows DebugAnalysis launcher test in `.codex_tmp\debug_launchers`: `cmd /c "echo. | X5_Split_v18_Windows_DebugAnalysis_DoubleClick.bat"` produced crops, report, `_debug/001_debug.ppm`, `_debug_analysis/001_base.ppm`, and `_debug_analysis/001_enhanced.ppm`.
- Checked macOS Debug and DebugAnalysis `.command` file headers and LF line endings; bash is not installed on this Windows machine, so `bash -n` was not run.

Not verified:
- Did not run the full `Test/` tree after this specific 1-10 restoration pass.
- Did not run PySide6/native app tests.

Known local-only files:
- `Test/`
- `downloaded_apps/`
- generated `.codex_tmp/` test outputs were removed after verification.

Next recommended step:
- Run a broader `Test/` folder report once v18 is ready to be treated as the active script, then decide whether to document the new CLI in a dedicated README.

---

Date: 2026-06-03
Computer: primary macOS machine
Branch: integrate-web-app
Last commit: 7178ceb Match native UI to SVG mockup

Changed:
- Read the project sync/context docs and continued the temporary standalone v18 script path from the Windows handoff.
- Changed v18 debug preview outputs from PPM to JPG:
  - `_debug/*_debug.jpg`
  - `_debug_analysis/*_base.jpg`
  - `_debug_analysis/*_enhanced.jpg`
- Updated debug and debug-analysis double-click launchers to run with `--dry-run`, so they write reports/debug JPGs but do not export cropped TIFF frames.
- Updated macOS `.command` launchers to be executable.
- Updated macOS launchers to look for `X5_Split_v18.py` beside the launcher first, then fall back to the repository script path. This supports copying only the `.command` launcher into a TIFF folder on this macOS machine.
- Updated `README_X5_Split_v18_DoubleClick.md` with the launcher-only workflow, dry-run debug behavior, JPG debug output, and Pillow dependency.

Verified:
- `python3 -m py_compile X5_Split_v18.py`
- `bash -n X5_Split_v18_macOS_DoubleClick.command X5_Split_v18_macOS_Debug_DoubleClick.command X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command`
- Created a synthetic TIFF in `/private/tmp/x5crop_v18_launcher_test`.
- Ran `python3 X5_Split_v18.py /private/tmp/x5crop_v18_launcher_test --report --debug --debug-analysis --dry-run`; confirmed `dry_run=True` and JPG debug outputs.
- Copied only `X5_Split_v18_macOS_Debug_DoubleClick.command` into the synthetic TIFF folder and ran it with `bash`; confirmed it used the repository script path, ran as dry run, and succeeded.
- Confirmed the temporary test output contained reports and debug JPGs but no cropped frame TIFFs.
- Confirmed JPG outputs with `file`.

Not verified:
- Did not run against real local `Test/` TIFF samples on this macOS session.
- Did not double-click from Finder; verified the `.command` behavior through `bash`.
- Did not run Windows `.bat` launchers after changing their dry-run/fallback behavior.

Known local-only files:
- `/private/tmp/x5crop_v18_launcher_test`
- `Test/`
- `downloaded_apps/`

Next recommended step:
- Run the v18 debug/debug-analysis launchers from Finder on a real TIFF folder, then run a broader real-sample report before deciding whether v18 replaces the current app engine path.
