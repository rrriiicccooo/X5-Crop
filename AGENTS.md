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
`X5_Split_v18.py` in `archive/` as preserved references. Keep every named X5
Crop development version snapshot in `archive/` before moving past it, including
experimental versions that are later paused or rolled back. Keep user-facing
project documentation consolidated in `README.md`.

## Coding Rules

- Preserve TIFF metadata behavior unless the user explicitly asks to change it.
- Keep detection changes close to the script logic.
- Avoid broad refactors while solving a narrow detection or workflow task.
- Add or update docs when script usage, setup, or testing behavior changes.
- After changing the active script or launchers, sync the local ignored Test
  copies too, especially `Test/135/X5_Crop.py`,
  `Test/135/X5_Crop_Mac.command`, and `Test/135/X5_Crop_win.bat`.
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
- Current local sparse-checkout policy keeps root-level source/docs/config files
  visible and hides bulky or release-only paths locally. Keep `.gitignore`
  visible. If `.github/` appears later, keep it visible too because it contains
  GitHub repository automation/configuration.
- The intended sparse-checkout rules are:

```text
/*
!/archive/
!/install/
!/LICENSE
!/release/
```

- `.gitignore` and `.github/` are hidden dot paths by name. Treat them as
  project configuration, keep them in sync for other Codex sessions, and do not
  rename them to non-hidden paths. On macOS they may also have the Finder
  hidden flag; on Windows, if the user wants them hidden in Explorer, use the
  Windows hidden attribute while keeping the same Git path names.
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

Date: 2026-06-06
Computer: primary macOS machine
Branch: main
Last commit: see `git log -1`

Changed:
- Active script is `X5_Crop.py` V3.6.12.
- V3.6.12 tunes the V3.6.11 format-aware `edge-pair` parameters after full
  dry runs on local `Test/120` and `Test/半格`. Half-frame parameters are
  unchanged because the full run stayed stable. 120-66 / 120-67 now use a
  wider search window, wider gutter range, lower edge/background thresholds,
  and a tighter non-135 hard-gap movement guard. This lets 120 wide dark bands
  become separator evidence without loosening PASS/REVIEW.
- V3.6.12 target result: compared with V3.6.11 temporary full dry runs,
  half-frame stayed 6 `approved_auto` / 9 `needs_review`; 120-66 and 120-67
  stayed 0 `approved_auto` / 16 `needs_review` while edge-pair accepted totals
  increased from 0 to 16; 120-645 stayed 0 / 16 with 0 edge-pair accepts. A
  135 focus `deskew off` comparison against V3.6.11 was structurally identical
  on `X5_00014`, `X5_00026`, `X5_00036`, and `X5_00041`.
- V3.6.11 extends `edge-pair` from 135-only to format-aware full-strip
  separator refinement. The original 135 parameters are preserved. Other
  formats use conservative per-format search windows, gutter widths, edge /
  background strength thresholds, and model-gap replacement quality thresholds.
  This is intended to let non-135 formats benefit from adjacent-frame edge
  evidence without simply copying 135 tuning.
- V3.6.10 is a low-risk cleanup after V3.6.9. It removes the unused
  `grid_protection_trust()` wrapper, updates CLI version/help text, fixes the
  `--bleed-x` help default from 15 to 20, clarifies that `--analysis` affects
  both enhanced separator assist and enhanced deskew angle selection, and
  updates stale diagnostic wording that referenced the V3.3.1 output baseline.
  It should not change detection flow, PASS/REVIEW logic, or output boxes.
- V3.6.9 unifies active grid protection with lightweight diagnostic hard-gap
  trust. `apply_robust_grid` now calls shared `light_hard_gap_trust` before
  letting a hard gap resist grid override. This shared trust can flag
  `nearby_separator_conflict`, `geometry_conflict`, `suspect_internal_edge`,
  and `suspect_frame_border`, and writes `trust_detail` into grid detail. The
  goal is to reduce active/diagnostic two-track red-gap trust without changing
  output.
- V3.6.8 replaces the V3.6.7 exact `single_anchor_review_gate` with
  `lucky_pass_risk_score`, so the rule no longer reads as tailored to one
  image. It scores model-gap dependence, limited strong hard separators,
  suspicious hard gaps, strong overlap model gaps, combined suspicion/overlap,
  and geometry stability credits. At score `>= 0.80`, it adds
  `lucky_pass_risk` and caps confidence below threshold. This can only move a
  suspicious PASS to REVIEW; it cannot make a weak image pass.
- V3.6.7 promotes the V3.6.6 nearby separator check into a very narrow
  correction rule for 135 full strips: a red hard separator can be moved only
  when a nearby candidate within `±4% pitch` is clearly stronger, the local
  frame geometry improves, and global width stability does not get worse. The
  pre-correction confidence is kept as a cap, so the correction cannot increase
  confidence or make a weak image pass by itself.
- V3.6.7 added a narrow `single_anchor_review_gate` for `X5_00041`-like lucky
  PASS shapes. The active gate requires exactly 2 `strong_separator` hard gaps,
  1 suspicious hard gap, 1 strong overlap model gap, and 2 model gaps. It sends
  `X5_00041` to REVIEW while the focused check kept `X5_00007`, `X5_00023`,
  and `X5_00035` as PASS.
- V3.6.7 target result: compared with V3.6.6, full `Test/135` dry-run changed
  structurally only on `X5_00026` and `X5_00041`; `X5_00026` pulls back the
  first red gap, and `X5_00041` enters REVIEW.
- macOS and Windows launchers now print the active script version dynamically
  from `X5_Crop.py --version` instead of carrying a hard-coded launcher version.
  The ignored `Test/135/` launcher copies were synced with the same change.
- macOS and Windows launchers now search for a dependency-ready Python instead
  of accepting the first `python` on PATH. They require imports for `numpy`,
  `Pillow`, and `tifffile` before selecting an interpreter. macOS also checks
  common Homebrew paths before falling back to PATH/system Python, and the
  local ignored `Test/135/` launcher copies were synced with the same change.
- Older handoff / changelog wording that implied all `--jobs` values above 2
  are capped to 2, or used obsolete early V3.6 `hard_trust` labels as if they
  were current, has been clarified.
- Current stable GitHub Release is `v3.6.2`, published from commit
  `5321d74560dcd97d54d150bd5e7aff73e997bd67` with asset
  `X5-Crop-v3.6.2.zip`. Release notes explicitly warn that overlap,
  near-overlap, locally irregular spacing, missing separators, or continuous
  image content can still be misdetected and should be reviewed with Debug
  Analysis.
- V3.6.6 adds hard-gap trust diagnostics and a limited correction rule:
  `strong_separator` hard gaps can resist grid override only when the robust
  grid model residual is high. It also records nearby stronger separator
  candidates within `±4% pitch`, marks suspicious hard gaps in Debug Analysis,
  and adds `single_anchor_pass_risk` for locally lucky PASS cases.
- V3.6.6 target truth notes from the user: `X5_00026` leftmost red gap is
  wrong; `X5_00032` red gaps 1, 4, and 5 are wrong; `X5_00041` only the
  leftmost red gap is correct, while the other separators are not reliable.
- V3.6.5 does not change detection logic. It only changes worker caps so
  normal runs still cap at 2 workers, while explicit `--diagnostics` runs can
  use up to 4 workers. The local-only diagnostics launcher under `Test/135/`
  now passes `--jobs 4`.
- V3.6.4 rolls the active script back to the V3.6.2 detection baseline and
  pauses the V3.6.3 overlap REVIEW gate. It adds a narrow long-axis white-edge
  outer correction: only when both end gaps are hard separators, the content
  box nearly fills the outer, short-axis slack is small, and one long-axis edge
  is almost entirely white can `outer_content_alignment` trigger the existing
  `content_aligned_outer` retry.
- V3.6.3 is preserved as a paused reference direction. It promoted strong
  overlap risk on model gaps to REVIEW for 135 full strips, but the user wants
  that idea held aside while narrower diagnostics/corrections are developed.
- V3.6.2 is a small cleanup step after V3.6.1 diagnostics: it folds
  `equal-broad-region` into ordinary `equal` and keeps `hard_fallback_detection`
  as a smaller review-only equal split fallback. It must not make fallback an
  auto-pass path or loosen PASS/REVIEW.
- Sparse checkout should keep `.gitignore` visible and should also keep
  `.github/` visible if that directory is added later. Local-only hidden dot
  files remain hidden by name, but should be treated as real project config.
  The other Codex workspace may be on Windows, so do not assume Finder hidden
  flags exist there; use Windows hidden attributes only when local UI hiding is
  requested.
- `Test/135/X5_Crop.py`, `Test/135/X5_Crop_Mac.command`, and
  `Test/135/X5_Crop_win.bat` should be synced after active script / launcher
  changes; this was done for V3.6.4 after the active script change.
- V3.6.1 keeps the V3.3.1 output baseline and the V3.6 diagnostic direction,
  but diagnostics now run only when `--diagnostics` is explicitly passed.
  Normal macOS / Windows launchers do not enable diagnostics.
- V3.6.1 refines diagnostic-only overlap / continuous-content reporting into
  weak / medium / strong risk levels. Only strong overlap risk is drawn as a
  cyan diagnostic tick in Debug Analysis, reducing visual noise. This remains
  report/visual-only and must not alter output boxes, confidence, or
  PASS/REVIEW.
- A local-only macOS diagnostic launcher exists under
  `Test/135/_X5_Crop_Mac_diagnostics_local.command`; it defaults to
  `deskew auto`, `dry run`, `debug analysis`, and `--diagnostics`. It is inside
  ignored `Test/` and should not be committed or published.
- V3.6 starts from the V3.3.1 output baseline and adds diagnostic cleanup only:
  read-only `diagnostics_v3_6`, gap method role labeling, hard-gap trust
  diagnostics, overlap/continuous-content model-gap diagnostics, and lightweight
  Debug Analysis ticks. It must not change V3.3.1 `status`, `outer_box`,
  `frame_boxes`, confidence, or PASS/REVIEW.
- V3.3.2, V3.4, V3.4.1, V3.4.2, and V3.5 are preserved as archive/reference
  versions. The user wants future optimization to start from the V3.6
  diagnostic baseline and avoid damaging known-accurate scans.
- V3.5 hard-gap semantic validation and V3.4.2 local grid segments are paused
  because the user found previously accurate scans such as `X5_00051`,
  `X5_00044`, `X5_00038`, and `X5_00022` became less accurate. Keep those ideas
  as historical attempts unless the user explicitly asks to reintroduce them
  with narrower safeguards.
- V3.4.1's strong-hard-gap-over-grid idea remains a reference direction, but it
  is not active as a correction rule in V3.6.
- Debug JPG and Debug Analysis JPG status bars now include the generating
  script name and version, for example `X5_Crop.py 3.4.1`, so future visual
  regression checks can identify which script produced an image.
- The same Debug Analysis version-label change has been applied to every
  archived X5 Crop V3 snapshot from V3.0 through V3.6, so rolling back to an
  archived version preserves version labeling in generated JPGs.
- Paused V3.4 was a detection simplification pass: separator enhanced detection was
  removed entirely, `equal-broad-region` was folded into ordinary `equal`, full
  strips now use content only as validation rather than generating separate
  content candidates, and 135 full strips no longer run the simple cuts-based
  frame-size fit before the explicit edge-sample fit.
- V3.0 through V3.6.12 active-script snapshots are preserved in `archive/`:
  `X5_Crop_v3.0.py`, `X5_Crop_v3.1.py`, `X5_Crop_v3.1.1.py`,
  `X5_Crop_v3.1.2.py`, `X5_Crop_v3.2.py`, `X5_Crop_v3.3.py`, and
  `X5_Crop_v3.3.1.py`, `X5_Crop_v3.3.2.py`, `X5_Crop_v3.4.py`,
  `X5_Crop_v3.4.1.py`, `X5_Crop_v3.4.2.py`, `X5_Crop_v3.5.py`,
  `X5_Crop_v3.6.py`, `X5_Crop_v3.6.1.py`, `X5_Crop_v3.6.2.py`, and
  `X5_Crop_v3.6.3.py`, `X5_Crop_v3.6.4.py`,
  `X5_Crop_v3.6.5.py`, `X5_Crop_v3.6.6.py`,
  `X5_Crop_v3.6.7.py`, `X5_Crop_v3.6.8.py`,
  `X5_Crop_v3.6.9.py`, `X5_Crop_v3.6.10.py`,
  `X5_Crop_v3.6.11.py`, and `X5_Crop_v3.6.12.py`.
- Future named development versions, including experiments that are later
  paused or rolled back, should also be saved as archive snapshots.
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
- Added root `CHANGELOG.md` as a more detailed bilingual local development
  changelog for detection logic, rollback context, and future testing notes.
- `CHANGELOG.md` now follows the same readability structure as `README.md`:
  a complete Chinese changelog first, followed by a complete English changelog,
  instead of mixing languages line-by-line.
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
- GitHub Release `v3.6.2` was created as the current stable user-facing release
  with `X5-Crop-v3.6.2.zip`, digest
  `sha256:981cb501b63b59f3ea116bcf0030668cd18df42b6ef064ad847b45c792e61e2b`.
  The release body includes bilingual quick start and warns that overlap,
  near-overlap, irregular local spacing, missing separators, and continuous
  image content may still require manual Debug Analysis review.
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
- In paused V3.4 and later, full-strip detection no longer generated separate
  content candidates; in V3.6, do not assume that simplification is active
  because V3.6 intentionally preserves V3.3.1 output behavior.
- README now has one consolidated Chinese Debug Analysis section instead of two
  overlapping sections.
- macOS and Windows launchers now re-prompt after an unknown format instead of
  exiting immediately.
- Folder runs process TIFF files in parallel with `--jobs 2` by default.
  Reports are still written by the main process after each file completes, so
  `split_report.jsonl` and `split_summary.csv` are not appended by multiple
  workers at the same time. Normal runs cap at 2 workers; explicit diagnostics
  runs can use up to 4 workers.
- If process workers are unavailable in a restricted environment, the script
  falls back to 2 thread workers instead of failing.

Verified:
- Current V3.6.12 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.12`; `python3 -m py_compile X5_Crop.py` passed. Full
  `Test/半格` dry-run with `--format half --strip full --count 12 --deskew off
  --dry-run --report --diagnostics --no-copy-review-files --jobs 2
  --no-reuse-analysis` produced 6 `approved_auto` / 9 `needs_review`, matching
  V3.6.11, with edge-pair accepted total 13. Full `Test/120` dry-runs with
  `--format 120-66`, `--format 120-67`, and `--format 120-645` all produced
  0 `approved_auto` / 16 `needs_review`; 120-66 and 120-67 edge-pair accepted
  totals increased from 0 to 16, while 120-645 stayed 0. Focus Debug Analysis
  on `X5_test_45` / `X5_test_55` for 120-66 was visually inspected.
  V3.6.12 vs archive V3.6.11 135 focus dry-run (`deskew off`) kept identical
  status, confidence, outer boxes, frame boxes, gap methods, and gap centers
  for `X5_00014`, `X5_00026`, `X5_00036`, and `X5_00041`.
- Current V3.6.11 verification: `python3 X5_Crop.py --version` and
  `python3 archive/X5_Crop_v3.6.11.py --version` both print
  `X5_Crop.py 3.6.11`; `python3 -m py_compile X5_Crop.py
  Test/135/X5_Crop.py archive/X5_Crop_v3.6.11.py` passed. Focus dry-run with
  diagnostics on `X5_00014`, `X5_00026`, `X5_00036`, and `X5_00041`
  produced `14/26` as `approved_auto` and `36/41` as `needs_review`.
  Structured comparison against V3.6.10 on those four 135 focus files had
  changed `0` for status, confidence, outer boxes, frame boxes, gap methods,
  and gap centers.
  Lightweight full-strip code-path checks for `xpan`, `half`, `120-645`,
  `120-66`, and `120-67` completed without errors on a single TIFF; those
  checks were only path/syntax smoke tests, not accuracy validation for those
  formats.
- Current V3.6.10 verification: `python3 X5_Crop.py --version` and
  `python3 archive/X5_Crop_v3.6.10.py --version` both print
  `X5_Crop.py 3.6.10`; `python3 -m py_compile X5_Crop.py
  Test/135/X5_Crop.py archive/X5_Crop_v3.6.10.py` passed. Focus dry-run with
  diagnostics on `X5_00014`, `X5_00026`, `X5_00036`, and `X5_00041`
  produced `14/26` as `approved_auto` and `36/41` as `needs_review`.
- Current V3.6.9 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.9`; `python3 -m py_compile X5_Crop.py` passed. Focus
  dry-run on `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`,
  `X5_00032`, `X5_00035`, and `X5_00041` kept only `X5_00041` as REVIEW.
  Full `Test/135` dry-run produced 42 `approved_auto` / 6 `needs_review`.
  Structured comparison against the V3.6.8 full report had changed `0`.
- Current V3.6.8 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.8`; `python3 -m py_compile X5_Crop.py` passed. Focus
  dry-run on `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`,
  `X5_00032`, `X5_00035`, and `X5_00041` produced only `X5_00041` as
  REVIEW. Focus risk scores: `X5_00041=0.96`, `X5_00007=0.71`,
  `X5_00035=0.74`, threshold `0.80`.
- Full V3.6.8 `Test/135` dry-run with `--format 135 --strip full --count 6
  --dry-run --report --no-copy-review-files --jobs 2` produced 42
  `approved_auto` / 6 `needs_review`, with `X5_00041` entering REVIEW via
  `lucky_pass_risk`.
- Current V3.6.7 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.7`; `python3 -m py_compile X5_Crop.py` passed. Focus
  dry-run with diagnostics on `X5_00014`, `X5_00026`, `X5_00032`,
  `X5_00041`, and `X5_00036` kept `14/26/32` approved, kept `36` in review,
  and moved `41` to review with `single_anchor_pass_risk`.
- After narrowing the `single_anchor_review_gate`, focus dry-run on
  `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`, `X5_00032`, `X5_00035`,
  and `X5_00041` produced only `X5_00041` as REVIEW.
- Full V3.6.7 `Test/135` dry-run with `--format 135 --strip full --count 6
  --dry-run --report --no-copy-review-files --jobs 2` produced 42
  `approved_auto` / 6 `needs_review`. Compared with the local V3.6.6 full
  report, changed files were only `X5_00026` and `X5_00041`.
- `bash -n X5_Crop_Mac.command Test/135/X5_Crop_Mac.command`
- `python3 -m py_compile X5_Crop.py Test/135/X5_Crop.py`
- `printf '\n\n\n\n' | ./X5_Crop_Mac.command` printed
  `X5_Crop.py 3.6.7 launcher` before stopping at the expected no-TIFF message
  in the repository root.
- `env PATH=/usr/bin:/bin bash -c 'printf "\n\n\n\n" |
  ./X5_Crop_Mac.command'` printed `X5_Crop.py 3.6.9 launcher`, confirming the
  macOS launcher can still find a dependency-ready Homebrew Python when PATH
  would otherwise prefer system Python. It then stopped at the expected no-TIFF
  message in the repository root.
- `python3 -m py_compile X5_Crop.py archive/X5_Split_v17.py archive/X5_Split_v18.py archive/X5_Crop_v3.0.py archive/X5_Crop_v3.1.py archive/X5_Crop_v3.1.1.py archive/X5_Crop_v3.1.2.py archive/X5_Crop_v3.2.py archive/X5_Crop_v3.3.py`
- `bash -n X5_Crop_Mac.command install/X5_Crop_Mac_install.command`
- `python3 X5_Crop.py --version` prints `X5_Crop.py 3.6`.
- `python3 -m py_compile X5_Crop.py` passed after adding the version label to
  Debug JPG and Debug Analysis JPG status bars.
- Generated local comparison JPGs for `Test/135/X5_00007.tif` using V3.3.1,
  V3.3.2, and then-current V3.4.1 with `--deskew off`; the comparison files
  are ignored local artifacts under `Test/135/version_compare/`.
- Generated new vertical Debug Analysis comparison JPGs for `Test/135/X5_00007.tif`:
  a V3.3.1/V3.3.2/V3.4.1 comparison and an all-V3 snapshot comparison from
  V3.0 through V3.5. These are ignored local artifacts under
  `Test/135/version_compare/`.
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
- Verified GitHub Release `v3.6.2` via `gh release view v3.6.2 --json
  tagName,name,url,targetCommitish,assets,body`; it targets
  `5321d74560dcd97d54d150bd5e7aff73e997bd67` and asset
  `X5-Crop-v3.6.2.zip` reports digest
  `sha256:981cb501b63b59f3ea116bcf0030668cd18df42b6ef064ad847b45c792e61e2b`.
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
- Historical V3.4.1 rollback check: a focused `--deskew off` dry-run on
  `X5_00022`, `X5_00038`, `X5_00044`, and `X5_00051` confirmed all four stayed
  `approved_auto`.
- Current V3.3.1 rollback smoke test: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.3.1`; `python3 -m py_compile X5_Crop.py` passed; and a
  `--deskew off --debug-analysis --dry-run` smoke test on `X5_00007` produced
  `approved_auto confidence=1.000`.
- Current V3.6 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6`; `python3 -m py_compile X5_Crop.py` and `git diff --check`
  passed; a `--deskew off --debug-analysis --dry-run` smoke test on
  `X5_00007` produced `approved_auto confidence=1.000` and wrote
  `diagnostics_v3_6` to the report.
- Current V3.6.1 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.1`; `python3 -m py_compile X5_Crop.py` and
  `archive/X5_Crop_v3.6.1.py` passed; normal `--debug-analysis --dry-run
  --deskew off` on `X5_00007` produced `approved_auto confidence=1.000`
  without `diagnostics_v3_6`; the same run with `--diagnostics` wrote
  `diagnostics_v3_6` version `3.6.1` and `changes_output=false`.
- Current V3.6.2 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.2`; `python3 -m py_compile X5_Crop.py` and
  `archive/X5_Crop_v3.6.2.py` passed; a focused `--debug-analysis
  --diagnostics --dry-run` smoke test on `X5_00014`, `X5_00032`,
  `X5_00036`, and `X5_00052` produced `14/32/52` as `approved_auto` and
  `36` as `needs_review`; report gap methods no longer include
  `equal-broad-region`.
- Current V3.6.3 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.3`; `python3 -m py_compile X5_Crop.py` and
  `archive/X5_Crop_v3.6.3.py` passed; a focused `--debug-analysis
  --diagnostics --dry-run` smoke test on `X5_00002`, `X5_00007`,
  `X5_00009`, `X5_00022`, `X5_00026`, `X5_00032`, `X5_00036`,
  `X5_00038`, `X5_00051`, and `X5_00052` produced `2/7/9/22/26/36/38/51`
  as `needs_review` due to `overlap_or_near_overlap_review`, while
  `32/52` stayed `approved_auto`. Based on the existing V3.6.2 full report,
  a full V3.6.3 run is expected to newly review previously approved
  `2/7/9/22/26/38/40/41/51`; `36/37/39/43` were already review and also have
  strong overlap-risk model gaps.
- Current V3.6.4 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.4`; `python3 -m py_compile X5_Crop.py` passed; focused
  `--debug-analysis --dry-run --no-reuse-analysis` tests on
  `X5_00007`, `X5_00009`, `X5_00014`, `X5_00022`, `X5_00038`, and
  `X5_00051` kept all six as `approved_auto`. `X5_00014` triggered
  `outer_correction` from the new white-edge rule, moving the work outer from
  `186..17254` to `203..17173`. Guard tests on `X5_00001`, `X5_00004`,
  `X5_00025`, `X5_00026`, `X5_00032`, `X5_00036`, `X5_00044`, and
  `X5_00052` kept prior PASS/REVIEW status, with `X5_00036` still
  `needs_review`.
- Current V3.6.5 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.5`; `python3 -m py_compile X5_Crop.py` passed; `bash -n`
  passed for `Test/135/_X5_Crop_Mac_diagnostics_local.command`. A 4-file
  diagnostics dry run with `--jobs 4` on `X5_00014`, `X5_00032`,
  `X5_00036`, and `X5_00052` printed `parallel: 4 workers`, completed in
  about 29 seconds in the sandbox thread fallback, and produced 3 approved /
  1 review with `X5_00036` still `needs_review`.
- Current V3.6.6 verification: `python3 X5_Crop.py --version` prints
  `X5_Crop.py 3.6.6`; `python3 -m py_compile X5_Crop.py` passed. Focus
  diagnostics dry-run on `X5_00014`, `X5_00026`, `X5_00032`, and `X5_00041`
  confirmed: `X5_00014` keeps the corrected outer and restores the rightmost
  hard separator as `edge-pair`; `X5_00026` marks left gap 1 as
  `nearby_separator_conflict`; `X5_00032` marks gaps 1 and 5 as
  `geometry_conflict` and gap 4 as `nearby_separator_conflict`; `X5_00041`
  marks gap 4 as `suspect_internal_edge` and summary
  `single_anchor_pass_risk=true`.
- Full V3.6.6 dry-run report against the local V3.6.4 report kept PASS/REVIEW
  counts at 43 / 5. Geometry changed only on `X5_00014` and `X5_00026`.
  Earlier broad protection also changed `X5_00004` and `X5_00040`, but was
  narrowed by requiring high robust-grid residual before hard-gap protection.
- Full V3.6 `Test/135` dry-run with `--format 135 --strip full --count 6
  --dry-run --report --no-copy-review-files --jobs 2 --no-reuse-analysis`
  produced 43 `approved_auto` / 5 `needs_review`. Compared against the
  V3.3.1 rollback commit `8928f70`, all 48 files had identical `status`,
  `outer_box`, `frame_boxes`, and confidence; every V3.6 report row included
  `diagnostics_v3_6`.
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
- Windows launcher Python search was edited but not executed on Windows in this
  turn.

Known local-only files:
- `Test/`
- `Test/135/_X5_Crop_Mac_diagnostics_local.command`
- Temporary verification outputs under `/private/tmp/`.

Next recommended step:
- Run a focused fresh dry-run on `Test/135` target files after any detection
  change: `X5_00007`, `X5_00009`, `X5_00014`, `X5_00022`, `X5_00032`,
  `X5_00036`, `X5_00038`, `X5_00051`, and `X5_00052`.
- Fast development/regression dry-runs may still pass `--deskew off` when the
  goal is raw detector comparison. The local diagnostic launcher uses the
  default `deskew auto` to better match real diagnostic output.
- For speed work, the largest current cost is full-resolution deskew rotation,
  followed by 135 edge-pair refinement across multiple outer candidates.
