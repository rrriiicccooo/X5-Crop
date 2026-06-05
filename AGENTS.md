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
- Active script is `X5_Crop.py` V3.3.
- V3.3 keeps the V3/V3.2 ordinary outer/gap/candidate selection chain while
  testing a stricter separation between detection geometry and output safety
  margin.
- Default output bleed is long-axis 20px and short-axis 10px. Detection now
  uses 0px bleed internally, so bleed is applied only to final output/report/
  Debug Analysis frame boxes and does not participate in outer, gap,
  confidence, or PASS/REVIEW scoring.
- Added final edge bleed protection after PASS/REVIEW status is decided: if
  same-frame-size fitting leaves the first or last frame too far inside an
  otherwise stable outer box, the output/report/debug frame is extended back to
  the outer edge plus requested long-axis bleed. This fixed the V3.1.1-style
  inward edge shrink seen on `X5_00009` and `X5_00044` while keeping detection
  scoring unchanged.
- Added an MIT `LICENSE` file and documented the project license in `README.md`
  before making the GitHub repository public.
- Removed the V3.1.1 `separator_derived_outer` competition and the V3.1.2 local
  separator rescue from the active detection chain. `X5_00007`, `X5_00019`, and
  `X5_00052` now follow the V3-style ordinary outer/gap path again.
- The `X5_00036` failure shape is guarded by
  `135_leading_grid_separator_failure`: three leading low-score grid separators,
  no accepted enhanced separator, and only adjacent late hard separators.
- Full-strip separator candidates that already pass the V2 auto gate now skip
  generating an extra content-only candidate, because the separator calibration
  has already checked content support.
- README now has one consolidated Chinese Debug Analysis section instead of two
  overlapping sections.
- macOS and Windows launchers now re-prompt after an unknown format instead of
  exiting immediately.
- Folder runs now process TIFF files in parallel with `--jobs 2` by default.
  Reports are still written by the main process after each file completes, so
  `split_report.jsonl` and `split_summary.csv` are not appended by multiple
  workers at the same time. Values above 2 are capped to 2.
- If process workers are unavailable in a restricted environment, the script
  falls back to 2 thread workers instead of failing.

Verified:
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n X5_Crop_Mac.command install/X5_Crop_Mac_install.command`
- `python3 X5_Crop.py --version` prints `X5_Crop.py 3.3`.
- Full fresh `Test/135` dry-run with `--format 135 --strip full --count 6
  --dry-run --report --no-copy-review-files --jobs 2 --no-reuse-analysis`
  produced 43 `approved_auto` / 5 `needs_review`, matching the V3.1.1 reference
  count. After the V3.2 detection rollback, the same full fresh `Test/135`
  dry-run again produced 43 / 5; in this sandbox process workers were
  unavailable, so it used the thread fallback and took about 5m13s wall time.
- Focus fresh dry-run on `X5_00002`, `X5_00007`, `X5_00009`, `X5_00014`,
  `X5_00019`, `X5_00032`, `X5_00036`, `X5_00038`, `X5_00044`, and `X5_00052`
  produced 9 `approved_auto` and `X5_00036` as the only `needs_review`.
- Focus V3.2 dry-run on `X5_00007`, `X5_00019`, `X5_00036`, and `X5_00052`
  restored the V3-style outer/gap/frame-fit behavior for `7`, `19`, and `52`;
  `X5_00036` stayed `needs_review` with
  `separator_hard_evidence_weak` / `v2_auto_gate_not_satisfied`.
- V3.3 was intentionally not full-regression tested in this turn at the user's
  request. Only syntax/launcher checks and a small focus smoke test were run;
  the user plans to run the full export and place the named output folder under
  `Test/135`.
- Focus V3.3 smoke dry-run on `X5_00007`, `X5_00019`, `X5_00036`, and
  `X5_00052` confirmed report `output_bleed` records
  `detection_long_axis_bleed=0`, `detection_short_axis_bleed=0`,
  `output_long_axis_bleed=20`, and `output_short_axis_bleed=10`; `X5_00036`
  stayed `needs_review`.
- `X5_00009` and `X5_00044` now report/output first and last frame margins at
  long-axis `-20/-20` while keeping their stable V3.1.1 outer boxes.
- `X5_00014` kept its V3.1.1 outer box; one long-axis edge is limited to -15
  only because the requested 20px bleed reaches the TIFF image boundary.
- The focused reports show full-strip candidates that pass the separator auto
  gate record `content_candidate_skipped=separator_auto_gate_passed`.
- `printf 'abc\n135\nn\nn\n\n' | ./X5_Crop_Mac.command` confirmed an invalid
  format is rejected and the next valid input continues the launcher flow; the
  run then stopped at the expected no-TIFF message in the repository root.
- Parallel smoke test on 3 linked Test/135 files produced 2 `approved_auto` and
  1 `needs_review`; in this sandbox, process workers were unavailable and the
  thread fallback completed successfully. `split_report.jsonl` had 3 rows and
  `split_summary.csv` had header + 3 rows.
- `--jobs 1` single-file smoke test on `X5_00019.tif` remained
  `approved_auto`.

Not verified:
- Windows launcher format retry was edited but not executed on Windows in this
  turn.

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
