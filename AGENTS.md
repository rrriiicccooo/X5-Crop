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

Date: 2026-06-04
Computer: primary macOS machine
Branch: main
Last commit: see `git log -1` after this handoff commit

Changed:
- Replaced the old V2 empty-candidate fallback chain with a small hard fallback:
  if V2 ever produces no candidates, the script now returns a low-confidence
  equal-split `needs_review` detection instead of re-entering the older
  separator/content selector.
- Removed the old fallback-only functions `choose_detection_with_analysis`,
  `choose_detection`, `choose_content_detection`, and `content_detection_rank`
  to avoid maintaining two competing detector selection paths.
- Made `--analysis auto` selective: enhanced separator analysis now runs only
  when separator evidence is weak, model-only/grid/equal gaps remain, or hard
  separator scores are low. `--analysis always` still forces the enhanced pass.
- Scoring now uses the final output frame boxes after any same-frame-size fit,
  so confidence is computed against the boxes that will actually be exported.
- Fixed layout probing for planar RGB TIFF shapes by deriving spatial dimensions
  from TIFF axes/shape instead of assuming `shape[0], shape[1]`.
- Added lightweight TIFF profile reading and a cached `split_report.jsonl`
  parser so reusable Debug Analysis records can be checked before full TIFF
  pixel decoding. Cached `needs_review` records now skip faster.
- Removed obsolete format-auto leftovers (`format_auto`, format guessing helper,
  and `manual_only`) now that CLI/launchers require an explicit format.
- Removed unused `write_gray_preview_jpeg`.
- Updated README to document the real Debug Analysis panel order and the new
  `--analysis auto` / `always` / `off` behavior.
- Fixed a broad-separator regression in `find_gap`: high-scoring separator
  cores inside visually broad black/white separator bands are now evaluated
  before the broad region is marked suspicious, so a clean wide separator is
  not discarded and then overwritten by a nearby narrow `edge-pair`.
- Confirmed the `Test/135/X5_00002.tif` fifth separator now stays on the broad
  detected separator near the geometric boundary instead of moving right to the
  misleading `edge-pair`.
- Changed the outer-content alignment behavior from pure downgrade to repair
  first: when a full-strip candidate's outer box includes too much long/short
  axis border, the script now builds a `content_aligned_outer`, reruns separator
  detection on that corrected outer, and uses the retried result if it passes.
- Disabled grid-driven outer expansion during the content-aligned retry so the
  corrected outer cannot be immediately stretched back to the previous
  over-wide box.
- Fixed constrained gap marker metadata: when geometry constraints move a gap
  center, `start`/`end` are now shifted by the actual center delta so Debug
  Analysis red separator boxes stay centered on the final gap location.
- Added an outer-content alignment gate so final high-confidence decisions must
  also prove the detected outer box is close to the real content bounding box.
  The report now includes `detail.outer_content_alignment` with content bbox,
  long/short-axis slack, content-to-outer ratios, and border dark fractions.
- If content-aligned retry cannot produce an aligned passing result, outer boxes
  that include too much long-axis or short-axis white border are still capped
  below the auto-export threshold with `outer_content_bbox_mismatch`.
- Expanded the per-image V2 analysis cache so candidate scoring reuses
  `gray_work`, content evidence, separator profiles, enhanced separator
  profiles, and edge-refine profiles instead of regenerating the same expensive
  evidence for repeated candidates.
- Wired the shared cache through V2 separator candidates, content candidates,
  fallback analysis paths, final content evidence, and Debug Analysis content
  evidence rendering.
- Kept cache lazy for separator/enhanced/edge profiles: profiles are computed
  only for outer boxes that are actually evaluated.
- Removed obsolete `strip_mode == "auto"` branches from the active script now
  that the CLI and launchers only support explicit `full` or `partial` strip
  modes.
- Simplified V2 candidate-count selection and legacy fallback selectors so
  unsupported strip modes fail directly instead of silently entering old
  full-vs-partial auto competition.
- Added safe reuse of Debug Analysis report data for later normal export:
  non-dry-run crop passes now look for a matching `split_report.jsonl` entry
  before running detection again.
- Analysis reuse is guarded by script version, source file stat/profile data,
  page, format, layout, strip/count, bleed, deskew, analysis mode, deskew angle
  limits, and confidence threshold.
- Cached `approved_auto` entries export directly from cached frame boxes, while
  cached `needs_review` entries skip export instead of rerunning detection and
  possibly changing status.
- Cached deskewed entries reapply the recorded deskew angle before cropping so
  cached frame boxes are used on the same rotated pixel geometry as the original
  Debug Analysis run.
- Added `--no-reuse-analysis` to force a fresh detection pass.
- Updated README with the Debug Analysis reuse behavior and safety conditions.
- Fixed Windows blank format default using the safer `set /p` pattern:
  `FORMAT_INPUT` is prefilled with `135` before prompting, so pressing Enter
  keeps the default value.
- Cleaned launcher prompt text: use lowercase prompts and labels, and changed
  `Format [135]:` to `format:` while still treating blank input as `135`.
- Replaced the project-local dependency target with user-level dependency
  installation. Install launchers now run `pip install --user -U ...`; macOS
  falls back to prompting for `--break-system-packages --user` if normal user
  install is blocked by externally-managed Python protection.
- Moved first-time install launchers into `install/` and adjusted them to run
  from the project root before running user-level dependency installation.
- Reordered main launcher prompts to ask for format first, then partial mode,
  then Debug Analysis dry run.
- Simplified launchers again: aside from first-time install launchers, macOS now
  keeps only `X5_Crop_Mac.command` and Windows keeps only `X5_Crop_win.bat`.
  Each main launcher asks for format, whether to enable partial mode, and
  whether to enable Debug Analysis dry run.
- Removed helper launchers `_X5_Crop_Mac_run.command` and
  `_X5_Crop_win_run.bat`. Their format prompt, count mapping, dependency-path
  setup, and run logic are now inlined into the visible macOS and Windows
  launchers.
- Current user-facing launchers are `X5_Crop_Mac.command`,
  `X5_Crop_win.bat`, and first-time install launchers under `install/`.
- Fixed launcher count behavior after separating partial mode: normal/full
  launchers now pass explicit counts (`135` 6, `half` 12, `xpan` 3, `120-645` 4,
  `120-66` 3, `120-67` 3), while partial launchers keep count auto.
- Fixed Windows format prompt defaulting: Windows launchers prefill
  `FORMAT_INPUT=135` before `set /p`, because Windows keeps the previous
  variable value when the user presses Enter on an empty prompt.
- Added first-time setup launchers: `install/X5_Crop_Mac_install.command` and
  `install/X5_Crop_win_install.bat`.
- Setup launchers install `numpy`, `tifffile`, `imagecodecs`, and `Pillow` for
  the current user. If Python is missing,
  macOS uses Homebrew when available or opens python.org; Windows tries `winget`
  before opening python.org.
- Updated macOS and Windows launchers to use the normal Python on PATH rather
  than a project-local venv/dependency folder, so the script and launchers can
  move more freely after dependencies are installed for the user.
- Updated `README.md` with the first-time setup workflow and required setup
  launcher files.
- Disabled default format guessing in the active CLI: `--format` is now required
  and only accepts explicit formats (`135`, `half`, `xpan`, `120-645`,
  `120-66`, `120-67`).
- Disabled launcher-driven strip guessing: `--strip` now accepts only `full` or
  `partial`, defaults to `full`, and partial/head handling must be explicitly
  selected.
- Replaced the large set of format-specific macOS and Windows launchers with
  compact prompt-based launchers. The launcher asks for format at runtime:
  blank/`135`, `xpan`, `half`, `645`, `66`, or `67`.
- Partial/head and Debug Analysis are now prompt choices inside the single main
  launcher for each platform.
- Updated `README.md` to describe the new choose-format-first workflow and
  explain that the goal is fewer false high-confidence results, not easier PASS.
- Added per-image V2 analysis caching so `gray_work` and content evidence are
  computed once per image/layout and reused by content candidates and candidate
  calibration.
- Added a V2 full-strip shortcut: when a full-strip separator candidate passes
  the hard evidence and content-validation auto gate, same-format partial
  candidates are skipped. This keeps easy full strips fast without weakening
  difficult-image review behavior.
- Promoted the active script to X5 Crop V2 (`VERSION = "2.0"`).
- Reworked final detection into a multi-candidate scorer: V2 now generates
  separator and content candidates across plausible format/count/strip models,
  scores each candidate with geometry, separator, and content evidence, and
  records the top candidates under `v2_competition`.
- Added explicit `selected_candidate` and `selection_override` report fields so
  reports can show when a high-scoring partial content candidate lost to a
  plausible full-strip candidate.
- Limited auto-mode V2 partial candidates to useful counts and reduced partial
  offset probing to keep runtime closer to practical launcher use. Explicit
  `--strip partial` still keeps the fuller partial search.
- Updated README and launcher labels from V1 to V2.
- Tightened the final detector relationship into a joint evidence gate:
  separator evidence owns hard crop-line confirmation, content evidence validates
  the proposed photos, and format geometry constrains plausible frame shape and
  count.
- Added `separator_hard_evidence_ok(...)` so real detected, edge-pair, and
  enhanced separator marks can support auto-export, while grid/equal marks stay
  model evidence rather than hard separator evidence.
- Added a conservative content-only partial pass rule: partial strips may still
  auto-pass, but only when content confidence is very strong and there are no
  content run, coverage, or aspect ambiguity reasons.
- Added `joint_separator_not_confirmed` downgrading so a full-strip content
  candidate without hard separator confirmation falls back to `REVIEW` instead
  of auto-exporting from content alone.
- Analyzed all 79 TIFF samples under `Test/` as downsampled evidence material
  for the current detector.
- Confirmed raw content-run count is unstable on real samples: internal scene
  texture can split one frame into several content peaks, while low-texture or
  dark frames can merge several frames into one weak content run.
- Kept content evidence as the primary direction, but made the selector more
  explicitly joint: a separator candidate can win when it passes threshold, is
  supported by content evidence, and the content-primary candidate is ambiguous,
  below threshold, or smaller.
- Added a conservative auto-mode safeguard so a high-scoring partial candidate
  cannot automatically steal the result from a still-plausible full-strip
  candidate. In that case the full-strip model is returned for review with
  `partial_competes_with_plausible_full_strip`.
- Created active `X5_Crop.py` V1 from the latest v18 baseline.
- Added a conservative content-evidence layer using a composite score from local
  gradient, neighbor texture, local contrast, and tonal presence.
- DebugAnalysis is now a four-panel JPG: debug boxes, original gray, separator
  evidence, and content evidence.
- Removed standalone Debug launchers; keep normal launchers and DebugAnalysis
  launchers only.
- Plain debug previews now show only the status bar, green outer box, and
  semi-transparent crop-area fills. Colored separator marks are drawn in the
  DebugAnalysis Separator evidence panel.
- DebugAnalysis order is now Original gray, Debug boxes, Separator evidence,
  Content evidence.
- Debug boxes now use different semi-transparent fills for each crop area instead
  of blue outlines.
- Moved v17/v18 reference scripts into `archive/`.
- Launcher surface is now intentionally small: `X5_Crop_Mac.command` and
  `X5_Crop_win.bat`, plus install launchers.
- Default bleed is now long-axis 15px and short-axis 10px: horizontal strips are
  left/right 15px and top/bottom 10px; vertical strips are top/bottom 15px and
  left/right 10px.
- Detection is now content-primary: content evidence builds the crop candidate
  first, while the older separator-based detector is retained as
  `separator_assist` report data and fallback.
- Content candidate ranking now prefers more complete frame models when
  candidates are above threshold, so a tiny high-scoring partial does not steal
  the result from a plausible larger sequence.
- Partial strips are no longer capped below the auto-export threshold just for
  being partial; they can pass when content, aspect, and supporting evidence are
  strong enough.
- Content-primary candidates with mismatched content run counts are capped below
  the auto-export threshold and marked for review.
- Content evidence is written into reports and can conservatively downgrade
  clear content/aspect conflicts, but it does not raise difficult files into
  automatic export.
- Removed v18 launchers and added cleaner `X5_Crop_*` macOS and Windows
  launchers.
- Rewrote `README.md` as the current Chinese user guide for X5 Crop.

Verified:
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `Test/135/X5_00002.tif`, `Test/135/X5_00019.tif`,
  `Test/135/X5_00038.tif`, and `Test/120/X5_test_43.tif` Debug Analysis
  dry-runs kept their expected approved/review statuses after the hard fallback
  cleanup.
- Debug Analysis performance check: 8 representative 135 files took `53.53s`
  wall time, about `6.69s/file`.
- Debug Analysis performance check: 4 representative vertical `120-66` files
  took `38.98s` wall time, about `9.75s/file`.
- Combined measured Debug Analysis average across those 12 files was about
  `7.71s/file`.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `python3 X5_Crop.py --help`
- `bash -n X5_Crop_Mac.command install/X5_Crop_Mac_install.command`
- `git diff --check`
- `Test/135/X5_00002.tif` Debug Analysis dry-run remains `approved_auto`.
- `Test/135/X5_00019.tif` explicit full 135 dry-run remains `approved_auto`.
- `Test/135/X5_00038.tif` explicit partial 135 dry-run remains `needs_review`.
- `Test/120/X5_test_43.tif` explicit full `120-66` dry-run remains
  `needs_review`.
- Confirmed `--analysis auto` reports `auto_not_needed` on easy
  `Test/135/X5_00019.tif`, while `--analysis always` forces the enhanced
  separator pass.
- Confirmed reusable `approved_auto` Debug Analysis data for
  `Test/135/X5_00019.tif` exports crops without rerunning detection.
- Confirmed reusable `needs_review` Debug Analysis data for
  `Test/120/X5_test_43.tif` skips export.
- Confirmed `spatial_shape_from_shape((3, 100, 200))` and
  `spatial_shape_from_shape((100, 200, 3))` both return `(100, 200)`.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `Test/135/X5_00002.tif` Debug Analysis dry-run remains `approved_auto`; gap 5
  is now `detected` at center `16473.5` with start/end `16400..16548` instead
  of the previously shifted `edge-pair` near `16624`.
- `Test/135/X5_00019.tif` explicit full 135 dry-run remains `approved_auto`.
- `Test/135/X5_00038.tif` explicit partial 135 dry-run remains `needs_review`.
- `Test/120/X5_test_43.tif` explicit full `120-66` dry-run remains
  `needs_review`.
- `Test/135/X5_00002.tif` explicit full 135 Debug Analysis now repairs the
  over-wide outer from work box `83..20069` to `114..19885`, stays
  `approved_auto`, and reports `outer_correction.used=true`.
- Confirmed `Test/135/X5_00002.tif` gap marker `start`/`end` midpoints now align
  with final gap centers after geometry constraints.
- `Test/135/X5_00019.tif` and `Test/135/X5_00025.tif` explicit full 135 dry-runs
  remain `approved_auto`.
- `Test/120/X5_test_43.tif` explicit full `120-66` remains `needs_review`.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `Test/135/X5_00019.tif` and `Test/135/X5_00025.tif` explicit full 135 dry-runs
  remain `approved_auto`; their outer-content alignment stays within the new
  slack gate.
- `Test/120/X5_test_43.tif` explicit full `120-66` remains `needs_review`.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `git diff --check`
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `git diff --check`
- After cache expansion, `Test/135/X5_00019.tif` explicit full 135 dry-run
  stayed `approved_auto` and ran in about 5.6 seconds without cProfile and
  about 5.4 seconds under cProfile.
- After cache expansion, `Test/120/X5_test_43.tif` explicit full `120-66`
  dry-run stayed `needs_review` and ran in about 4.8 seconds.
- Debug Analysis dry-run for `Test/135/X5_00019.tif` stayed `approved_auto` and
  wrote the combined JPG in about 5.8 seconds.
- Explicit partial 135 dry-run for `Test/135/X5_00038.tif` stayed
  `needs_review`.
- Confirmed no `strip_mode == "auto"` / `auto_full_confidence` /
  `skip_partial_after_full_auto_gate` references remain.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `python3 X5_Crop.py --help` still shows only `--strip {full,partial}`.
- `Test/135/X5_00019.tif` with explicit full 135 mode remains `approved_auto`.
- `Test/135/X5_00038.tif` with explicit partial 135 mode remains
  `needs_review`.
- `python3 -m py_compile X5_Crop.py`
- Generated Debug Analysis dry-run report for `Test/135/X5_00019.tif`, then ran
  normal export against the same output folder and confirmed it reused
  `split_report.jsonl` and wrote six TIFFs without rerunning detection.
- Generated Debug Analysis dry-run report for `Test/120/X5_test_43.tif`, then
  ran normal export against the same output folder and confirmed cached
  `needs_review` skipped export.
- Forced a deskew-applied Debug Analysis run for `Test/135/X5_00025.tif` with
  `--deskew-min-angle 0.001`, then confirmed normal export reused the analysis,
  reapplied the recorded deskew angle, and wrote six TIFFs.
- Prompt smoke tests on `X5_Crop_Mac.command` confirmed the launcher output now
  uses lowercase prompt text, `format:` without `[135]`, and lowercase summary
  labels.
- `bash -n install/X5_Crop_Mac_install.command X5_Crop_Mac.command`
- Confirmed `X5_Crop_Mac.command` no longer prefers `.venv-x5crop` and no
  longer adds `.x5crop_deps` to `PYTHONPATH`.
- Confirmed install launchers use user-level pip install instead of creating a
  virtual environment or project-local dependency target.
- Prompt smoke test on `X5_Crop_Mac.command` still reaches format-first flow and
  blank answers select `135`, full mode, debug off. The repository root has no
  TIFF files, so the test intentionally stopped after `No TIFF files found`.
- `bash -n install/X5_Crop_Mac_install.command X5_Crop_Mac.command`
- Prompt smoke tests on `X5_Crop_Mac.command` confirmed the prompt order is
  format first, then partial mode, then Debug Analysis dry run. Blank answers
  select `135`, full mode, debug off; `645` + `y` + `y` selects `120-645`,
  partial mode, debug on.
- Confirmed launcher file list now contains only `X5_Crop_Mac.command`,
  `X5_Crop_win.bat`, and install launchers under `install/`.
- Confirmed current launcher list has only `X5_Crop_Mac.command`,
  `install/X5_Crop_Mac_install.command`, `X5_Crop_win.bat`, and
  `install/X5_Crop_win_install.bat` besides `X5_Crop.py`.
- `bash -n install/X5_Crop_Mac_install.command X5_Crop_Mac.command`
- Confirmed `Test/135/X5_00019.tif` with `--format 135 --strip full --count 6`
  prints `count: 6` and remains `approved_auto`; runtime was about 5.9 seconds.
- Confirmed `Test/135/X5_00038.tif` with `--format 135 --strip partial` still
  prints `count: auto` and remains `needs_review`; runtime was about 20.9
  seconds.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n install/X5_Crop_Mac_install.command X5_Crop_Mac.command`
- `python3 X5_Crop.py --version` prints `X5_Crop.py 2.0`.
- `python3 X5_Crop.py --help` shows `--format` as required and `--strip` choices
  as only `full,partial`.
- Confirmed running without `--format` fails with argparse error:
  `the following arguments are required: --format`.
- Confirmed `Test/135/X5_00019.tif` with `--format 135 --strip full --report
  --dry-run --no-copy-review-files` remains `approved_auto` as a 6-frame `135`
  result; runtime was about 6.3 seconds.
- Confirmed `Test/135/X5_00019.tif` DebugAnalysis with explicit full 135 mode
  writes `/private/tmp/x5crop_explicit_debug_19/_debug_analysis/X5_00019_debug_analysis.jpg`;
  runtime was about 6.9 seconds.
- Confirmed `Test/135/X5_00038.tif` with `--format 135 --strip partial --report
  --dry-run --no-copy-review-files` stays `needs_review`, not auto-exported,
  despite strong content candidates; runtime was about 21.0 seconds.
- Confirmed reports for explicit full/head runs show `v2_competition.formats`
  as only `['135']`, proving the selector is no longer competing across formats.
- Profiled V2 before optimization: `Test/135/X5_00019.tif` took about 23 seconds
  under `cProfile`, dominated by repeated content evidence generation.
- After content caching, `Test/135/X5_00019.tif` dropped to about 12.6 seconds
  and `Test/120/X5_test_43.tif` / `X5_test_58.tif` were about 10.3 seconds.
- After the full-strip shortcut, `Test/135/X5_00019.tif` ran in about 6.2
  seconds, `Test/135/X5_00025.tif` in about 6.0 seconds, `Test/120/X5_test_43.tif`
  in about 9.9 seconds, and `Test/120/X5_test_58.tif` in about 9.6 seconds.
- Confirmed `Test/135/X5_00019.tif` and `X5_00025.tif` still remain
  `approved_auto` 6-frame `135` results after the speed changes.
- Confirmed `Test/120/X5_test_43.tif` and `X5_test_58.tif` still remain
  `needs_review` after the speed changes.
- Generated DebugAnalysis for `Test/120/X5_test_43.tif` after the speed changes;
  ordinary detection stayed under 10 seconds, while DebugAnalysis took about
  10.3 seconds because it also writes the combined JPG.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 2.0`.
- Confirmed `Test/135/X5_00019.tif` remains `approved_auto` as a 6-frame `135`
  model after the V2 scorer. Runtime was about 25 seconds on this machine.
- Confirmed `Test/135/X5_00025.tif` remains `approved_auto` as a 6-frame `135`
  model after the V2 scorer.
- Confirmed `Test/120/X5_test_43.tif` remains `needs_review` as a 3-frame
  `120-66` model, even though 2-frame content partial candidates score highly.
- Confirmed `Test/120/X5_test_58.tif` remains `needs_review` because content is
  plausible but hard separator support is weak.
- Generated DebugAnalysis for `Test/120/X5_test_43.tif` and visually confirmed
  the final 3-frame review result still renders correctly.
- Confirmed `Test/135/X5_00019.tif` remains `approved_auto` as a 6-frame `135`
  model, with joint decision `separator_hard_evidence_passed_and_content_validated`.
- Confirmed `Test/135/X5_00025.tif` remains `approved_auto` as a 6-frame `135`
  model, with hard separator evidence plus content validation.
- Confirmed `Test/120/X5_test_43.tif` and `X5_test_44.tif` remain
  `needs_review` as 3-frame `120-66` models instead of false 2-frame partial
  auto-passes.
- Confirmed `Test/120/X5_test_58.tif` is downgraded to `needs_review` with
  `joint_separator_not_confirmed` when content is plausible but hard separator
  evidence is not strong enough.
- Confirmed `Test/135/X5_00060.tif`, `X5_00063.tif`, and
  `Test/120/X5_test_48.tif` remain `needs_review` because content evidence is
  ambiguous or incomplete.
- Built a Test contact sheet at `/private/tmp/x5crop_test_contact_sheet.jpg` for
  representative samples including `X5_test_1.tif`, `2.tif`, `3.tif`, `5.tif`,
  `9.tif`, `11.tif`, `19.tif`, `20.tif`, `22.tif`, `25.tif`, `43.tif`,
  `44.tif`, `48.tif`, `53.tif`, `72.tif`, `73.tif`, `74.tif`, `75.tif`,
  `77.tif`, and `79.tif`.
- Wrote the all-Test downsampled content summary to
  `/private/tmp/x5crop_test_content_run_summary.json`.
- Confirmed `Test/X5_test_43.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_44.tif` now returns `needs_review` for a 3-frame
  `120-66` model instead of falsely passing a 2-frame partial model.
- Confirmed `Test/X5_test_19.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed `Test/X5_test_25.tif` remains `approved_auto` as a 6-frame `135`
  model after joint separator/content selection.
- Confirmed narrow/difficult `Test/X5_test_72.tif` and `X5_test_74.tif` remain
  `needs_review` rather than being promoted by content evidence.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py`
- `bash -n install/X5_Crop_Mac_install.command X5_Crop_Mac.command`
- `python3 X5_Crop.py --version`
- `python3 X5_Crop.py --help`
- Verified vertical bleed mapping with `Box.expand(15, 10, ...)` plus
  `map_work_box(..., "vertical", ...)`: long-axis bleed maps to original
  top/bottom, short-axis bleed maps to original left/right.
- Ran content-primary dry-runs on `Test/X5_test_19.tif`, `25.tif`, `31.tif`,
  `20.tif`, `22.tif`, `23.tif`, and `30.tif`; reports show
  `analysis_source=content_primary` with separator data under
  `separator_assist`.
- Confirmed `X5_test_25.tif` is forced to `needs_review` when content detects 7
  usable runs for a 6-frame target (`content_run_count_mismatch`), even though
  separator assist passes.
- After removing the partial-strip cap and adding content-specific ranking,
  confirmed `X5_test_19.tif` selects 3 frames and passes, `X5_test_20.tif`
  selects 5 frames and passes, while `X5_test_25.tif` remains review for run
  count mismatch.
- Ran DebugAnalysis dry-runs on `Test/135负片/正常/001.tif`, `11.tif`, and
  `X5 022.tif`.
- Confirmed `001.tif` remains `needs_review` at confidence `0.676` and produces
  a four-panel DebugAnalysis JPG.
- Re-ran DebugAnalysis for `001.tif` and visually confirmed colored separator
  marks moved to the Separator evidence panel while Debug boxes stayed clean.
- Re-ran DebugAnalysis for `001.tif` after panel reordering and visually
  confirmed the order is Original gray, Debug boxes, Separator evidence, Content
  evidence, with semi-transparent crop fills in Debug boxes.
- Ran `--debug` on `001.tif` and visually confirmed the standalone debug JPG now
  only shows the status bar, outer box, and crop boxes.
- Confirmed `11.tif` remains `approved_auto` at confidence `0.963`.
- Confirmed `X5 022.tif` remains `needs_review` at confidence `0.679`.
- Inspected the generated `001.tif` DebugAnalysis JPG and confirmed the fourth
  `Content evidence` panel is present.

Not verified:
- Did not run the new install launchers end-to-end, because that would create
  or update user-level Python packages on this machine.
- Did not run `install/X5_Crop_win_install.bat` on Windows.
- Did not run Windows `.bat` launchers on Windows.
- Did not run a non-dry-run TIFF export after creating X5 Crop V2.
- Did not create hand-labeled ground-truth fixtures for all `Test/` images; this
  pass used visual inspection plus representative dry-runs.
- Did not run the V2 scorer across all 79 Test TIFFs yet. Current V2 runtime is
  slower than V1 because it scores multiple candidates per file.

Known local-only files:
- `Test/`
- `/private/tmp/x5crop_fixed_count_19`
- `/private/tmp/x5crop_partial_count_auto_38`
- `/private/tmp/x5crop_explicit_full_19`
- `/private/tmp/x5crop_explicit_head_38`
- `/private/tmp/x5crop_explicit_debug_19`
- `/private/tmp/x5crop_v1_debug_001`
- `/private/tmp/x5crop_v1_debug_11`
- `/private/tmp/x5crop_v1_debug_11b`
- `/private/tmp/x5crop_v1_debug_x5022`
- `/private/tmp/x5crop_debuganalysis_only_001`
- `/private/tmp/x5crop_clean_debug_001`
- `/private/tmp/x5crop_reordered_panels_001`
- `/private/tmp/x5crop_content_primary_19`
- `/private/tmp/x5crop_content_primary_25`
- `/private/tmp/x5crop_content_primary_31`
- `/private/tmp/x5crop_content_primary_19b`
- `/private/tmp/x5crop_content_primary_25b`
- `/private/tmp/x5crop_content_primary_batch`
- `/private/tmp/x5crop_joint_score_19`
- `/private/tmp/x5crop_joint_score_20`
- `/private/tmp/x5crop_joint_score_25`
- `/private/tmp/x5crop_joint_score_19b`
- `/private/tmp/x5crop_joint_score_20b`
- `/private/tmp/x5crop_joint_score_25c`
- `/private/tmp/x5crop_test_contact_sheet.jpg`
- `/private/tmp/x5crop_test_content_run_summary.json`
- `/private/tmp/x5crop_joint_model_19b`
- `/private/tmp/x5crop_joint_model_25b`
- `/private/tmp/x5crop_joint_model_43c_debug`
- `/private/tmp/x5crop_joint_model_44b`
- `/private/tmp/x5crop_joint_model_72b`
- `/private/tmp/x5crop_joint_model_74b`
- `/private/tmp/x5crop_joint_gate_19`
- `/private/tmp/x5crop_joint_gate_25`
- `/private/tmp/x5crop_joint_gate_43`
- `/private/tmp/x5crop_joint_gate_44`
- `/private/tmp/x5crop_joint_gate_48`
- `/private/tmp/x5crop_joint_gate_58`
- `/private/tmp/x5crop_joint_gate_60`
- `/private/tmp/x5crop_joint_gate_63`
- `/private/tmp/x5crop_v2_19`
- `/private/tmp/x5crop_v2_19b`
- `/private/tmp/x5crop_v2_19c`
- `/private/tmp/x5crop_v2_19d`
- `/private/tmp/x5crop_v2_25`
- `/private/tmp/x5crop_v2_25b`
- `/private/tmp/x5crop_v2_25c`
- `/private/tmp/x5crop_v2_25d`
- `/private/tmp/x5crop_v2_43`
- `/private/tmp/x5crop_v2_43b`
- `/private/tmp/x5crop_v2_43c`
- `/private/tmp/x5crop_v2_43d`
- `/private/tmp/x5crop_v2_43_debug`
- `/private/tmp/x5crop_v2_58b`
- `/private/tmp/x5crop_v2_58c`
- `/private/tmp/x5crop_v2_58d`
- `/private/tmp/x5crop_profile_19`
- `/private/tmp/x5crop_profile_43`
- `/private/tmp/x5crop_profile_19_cached`
- `/private/tmp/x5crop_profile_43_cached`
- `/private/tmp/x5crop_speed_19a`
- `/private/tmp/x5crop_speed_19b`
- `/private/tmp/x5crop_speed_25b`
- `/private/tmp/x5crop_speed_43a`
- `/private/tmp/x5crop_speed_43b`
- `/private/tmp/x5crop_speed_43_debug`
- `/private/tmp/x5crop_speed_58a`
- `/private/tmp/x5crop_speed_58b`

Next recommended step:
- Run V2 over a broader Test batch and use `v2_competition` to identify which
  candidate families are still too aggressive. If more speed is needed, the next
  likely target is caching separator outer candidates/profiles per image/layout.
