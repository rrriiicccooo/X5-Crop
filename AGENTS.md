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
- Active script is temporarily rolled back to `X5_Crop.py` V3.4.1.
- V3.5 hard-gap semantic validation and V3.4.2 local grid segments are paused
  in the active script because the user found previously accurate scans such as
  `X5_00051`, `X5_00044`, `X5_00038`, and `X5_00022` became less accurate.
  Keep those ideas as historical attempts only unless the user explicitly asks
  to reintroduce them with narrower safeguards.
- V3.4.1 keeps strong hard separator evidence authoritative when robust grid
  fills missing/model gaps. If a strong `detected` or `edge-pair` gap conflicts
  with the equal-spacing grid, the hard gap is preserved and the conflict is
  recorded in `grid.hard_conflicts` instead of being rewritten as `grid`.
- V3.4 is a detection simplification pass: separator enhanced detection was
  removed entirely, `equal-broad-region` was folded into ordinary `equal`, full
  strips now use content only as validation rather than generating separate
  content candidates, and 135 full strips no longer run the simple cuts-based
  frame-size fit before the explicit edge-sample fit.
- V3.0 through V3.3 active-script snapshots are preserved in `archive/`:
  `X5_Crop_v3.0.py`, `X5_Crop_v3.1.py`, `X5_Crop_v3.1.1.py`,
  `X5_Crop_v3.1.2.py`, `X5_Crop_v3.2.py`, `X5_Crop_v3.3.py`, and
  `X5_Crop_v3.3.1.py`.
- V3.3.2 adds conservative overlap-aware gap handling for 135 full strips:
  suspected overlap-like gaps are marked with `overlap_like=true` and are not
  used as strong same-frame-size anchors. This does not increase confidence or
  alter PASS/REVIEW gates.
- PASS-only geometry polish is limited to small evidence-limited long-axis
  expansion.
- README has been rewritten as a bilingual Chinese/English user guide for
  V3.3.x, covering install, launchers, Debug Analysis, reuse, command line
  usage, outputs, and license.
- User-facing README no longer mentions internal test filenames, regression
  samples, archived scripts, rollback history, or previous-version detection
  details.
- User-facing README now states that GitHub Releases are the stable user-facing
  downloads, while the repository `main` branch may contain in-progress
  development changes.
- User-facing README header now lists both the current development version and
  the current stable GitHub Release version.
- User-facing README now includes a bilingual changelog describing detection
  and workflow changes from V3.0 through the current development version.
- User-facing README now starts with a Chinese quick-start usage section before
  the longer Chinese/English guide.
- User-facing README and GitHub Release `v3.3.1` now both put bilingual
  Chinese/English quick-start usage near the top.
- README and GitHub Release `v3.3.1` quick-start sections now mention expected
  per-file runtime ranges and clarify that a quiet terminal usually means the
  script is still processing the current TIFF.
- GitHub Release `v3.3.1` was created with
  `release/X5-Crop-v3.3.1.zip` uploaded as the user-facing package.
- GitHub Release `v3.3.1` asset was replaced after cleaning the user-facing
  README and removing the short-axis polish code from the V3.3.1
  archive/package. The uploaded asset digest is
  `sha256:cec114dedd61a8cad8540676bf485e6589d078c2eb994255456bacb88137dd3d`.
- GitHub Release `v3.3.1` body now describes the stable release policy and
  summarizes major changes compared with the previous `v3` tag in Chinese and
  English.
- V3.3.1 keeps the V3/V3.2 ordinary outer/gap/candidate selection chain and
  the V3.3 output-only bleed separation.
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
  too few hard separators, and only adjacent late hard separators.
- Full-strip detection no longer generates separate content candidates; content
  is used as validation after separator/geometric candidates are built.
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
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py archive/X5_Crop_v3.0.py archive/X5_Crop_v3.1.py archive/X5_Crop_v3.1.1.py archive/X5_Crop_v3.1.2.py archive/X5_Crop_v3.2.py archive/X5_Crop_v3.3.py`
- `bash -n X5_Crop_Mac.command install/X5_Crop_Mac_install.command`
- `python3 X5_Crop.py --version` prints `X5_Crop.py 3.4.1`.
- `release/X5-Crop-v3.3.1.zip` was generated locally from the current
  V3.3.1 script, launchers, install scripts, README, LICENSE, and archive
  snapshots; the zip listing was checked.
- GitHub Release URL:
  `https://github.com/rrriiicccooo/X5-Crop/releases/tag/v3.3.1`
- Verified the updated GitHub Release asset `X5-Crop-v3.3.1.zip` reports
  digest `sha256:cec114dedd61a8cad8540676bf485e6589d078c2eb994255456bacb88137dd3d`.
- Verified GitHub Release `v3.3.1` body via `gh release view v3.3.1 --json
  body,name,tagName,assets`; it now includes Chinese/English changes compared
  with `v3`.
- Archived `X5_Crop_v3*.py` snapshots report internal versions 3.0, 3.1,
  3.1.1, 3.1.2, 3.2, 3.3, and 3.3.1.
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
- Default-output Debug Analysis terminal messages now print only the generated
  JPG filename instead of the full default `split_output/_debug_analysis/...`
  path. Explicit `--output` runs still print the full output path.
- V3.3.1 added a PASS-only geometry polish step after status is decided and
  before output bleed is applied; current behavior keeps this limited to small
  evidence-limited long-axis expansion. This does not change confidence or
  PASS/REVIEW.
- Focus V3.3.1 smoke dry-run on `X5_00007`, `X5_00009`, `X5_00036`, and
  `X5_00052` confirmed: `X5_00052` left outer expanded by 59px and
  `X5_00036` stayed `needs_review`.
- Focus V3.3.2 smoke dry-run on `X5_00007`, `X5_00009`, and `X5_00036`
  confirmed: `X5_00007` and `X5_00009` stayed `approved_auto`, `X5_00036`
  stayed `needs_review`, `X5_00007` marked one overlap-like grid gap, and
  `X5_00009` skipped global same-frame-size fitting with
  `clustered_late_edge_samples_with_leading_model_gaps`.
- Focus dry-run on `X5_00007`, `X5_00009`, `X5_00014`, and `X5_00036`
  confirmed `7/9/14` stayed `approved_auto` and `36` stayed `needs_review`.
- Focus V3.4 dry-run on `X5_00002`, `X5_00007`, `X5_00009`, `X5_00014`,
  and `X5_00036` confirmed `2/7/9/14` stayed `approved_auto`, `36` stayed
  `needs_review`, and gap methods no longer include `enhanced-detected` or
  `equal-broad-region`.
- Focus V3.4.1 dry-run on `X5_00002`, `X5_00007`, `X5_00009`, `X5_00014`,
  and `X5_00036` confirmed `2/7/9/14` stayed `approved_auto` and `36` stayed
  `needs_review`. `X5_00014` now keeps the right-side hard separator as
  `edge-pair` at `11492.5` instead of rewriting it to grid at `11294.375`;
  the conflict is recorded in `grid.hard_conflicts`.
- Focus V3.4.2 dry-run on `X5_00002`, `X5_00007`, `X5_00009`, `X5_00014`,
  and `X5_00036` confirmed `2/7/9/14` stayed `approved_auto` and `36` stayed
  `needs_review`. Local grid adjusted leading model gaps on `X5_00009` and
  bounded model gaps on `X5_00014`; `X5_00007` and `X5_00036` recorded
  `local_grid.used=false`.
- Focus V3.5 dry-run with `--deskew off` on `X5_00001`, `X5_00004`,
  `X5_00007`, `X5_00009`, `X5_00014`, `X5_00025`, `X5_00026`, and
  `X5_00036` confirmed `1/4/7/9/14/25/26` stayed `approved_auto` and `36`
  stayed `needs_review`. `X5_00026` recorded one `suspect_internal_edge`
  demotion in `hard_gap_validation`; `X5_00001`, `X5_00004`, and
  `X5_00025` recorded no suspect hard gaps.
- After the temporary rollback to V3.4.1, a focused `--deskew off` dry-run on
  `X5_00022`, `X5_00038`, `X5_00044`, and `X5_00051` confirmed all four stayed
  `approved_auto`.
- `X5_00009` and `X5_00044` now report/output first and last frame margins at
  long-axis `-20/-20` while keeping their stable V3.1.1 outer boxes.
- `X5_00014` kept its V3.1.1 outer box; one long-axis edge is limited to -15
  only because the requested 20px bleed reaches the TIFF image boundary.
- V3.4 focused reports show full-strip candidates record
  `content_candidate_skipped` and use content validation only.
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
- `release/X5-Crop-v3.3.1.zip`
- Temporary verification outputs under `/private/tmp/`.

Next recommended step:
- Run a focused fresh dry-run on `Test/135` target files after any detection
  change: `X5_00007`, `X5_00022`, `X5_00032`, `X5_00036`, `X5_00038`,
  `X5_00051`, and `X5_00052`.
- Future development/regression dry-runs should pass `--deskew off` by default
  to keep iteration fast. Enable deskew only when testing deskew itself,
  deskewed output quality, or reuse of deskew angles.
- For speed work, the largest current cost is full-resolution deskew rotation,
  followed by 135 edge-pair refinement across multiple outer candidates.
