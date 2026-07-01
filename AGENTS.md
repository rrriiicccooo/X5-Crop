# Codex Agent Rules

This is the single coordination file for this repository. Keep it short:
standing rules, current source layout, release rules, and the latest handoff.

## First Moves

1. Read `README.md` and this handoff.
2. Check branch and dirty state before editing:

```bash
git branch --show-current
git status --short
```

3. Treat GitHub as authoritative for source/docs. NAS or local copied folders
   are only transport/testing surfaces.

Repository:

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Current Scope

- Keep active work focused on the standalone X5 Crop workflow unless the user
  explicitly resumes app/native packaging.
- Active entry point: `X5_Crop.py`.
- In V4+, `X5_Crop.py` is a thin development entry; implementation lives under
  `x5crop/`.
- Keep named development snapshots in `archive/` before moving past them.
- Preserve `archive/X5_Split_v17.py` and `archive/X5_Split_v18.py` as old
  references when present.
- User-facing docs are `README.md`, `快速启动_Quick_Start.md`, and
  `CHANGELOG.md`.
- Developer architecture docs are `ARCHITECTURE.md` and
  `docs/ARCHITECTURE.md`; keep them mirrored when updating either copy.

## Coding Rules

- Preserve TIFF quality/metadata behavior unless the user explicitly asks
  otherwise. Cropped TIFF output must keep bit depth, channel structure,
  ICC/color space, resolution, and metadata.
- Keep detection changes conservative and sample-driven. Do not loosen
  PASS/REVIEW rules broadly to fix one file.
- For detection changes, verify known-good formats before calling the change
  safe, especially `135`.
- Use `--deskew off` for fast detector regressions unless the task is about
  export/deskew behavior.
- Update docs when usage, setup, output folders, launcher behavior, or release
  packaging changes.
- Directional requests use horizontal-strip wording as baseline. Add rotated
  vertical-strip behavior when implementing.
- After changing active script/package/launchers, sync ignored local Test
  copies when available:
  - `Test/135`
  - `Test/new_135`
  - `Test/120/66`
  - `Test/120/67`
  - `Test/半格/full`
  - `Test/半格/partial`

## Git And Local Files

- Commit only intentional source/docs/config changes.
- Check `git status --short` before and after edits. Other synced Codex
  sessions may have changed files.
- Do not revert user/other-session changes unless explicitly asked.
- Keep `.gitignore` visible. If `.github/` appears, keep it visible too.
- Intended sparse checkout:

```text
/*
!/archive/
!/install/
!/release/
!/tools/
!/LICENSE
```

- Keep `LICENSE`, `archive/`, `install/`, `release/`, and `tools/` cloud/GitHub
  only locally unless the user asks to expand them.
- Do not commit generated/local files:
  - `.venv/`, `.venv-build/`, `build/`, `dist/`, `release/`
  - `__pycache__/`, `.DS_Store`, `downloaded_apps/`
  - `Test/`
  - generated `x5_crop_output/`
  - large TIFF samples unless explicitly made official fixtures with Git LFS

## Release Package Rules

User Release zip should contain only:

```text
X5_Crop.py                  # standalone script from tools/build_standalone.py
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
- This is per-folder preparation, not a permanent global trust registration.

## Regression Priorities

When detection changes are made, prefer comparing reports with
`python3 -m x5crop.regression.compare` or the current regression CLI.

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
- `Test/120/66` full/partial: dark-band / separator-derived outer behavior.
- `Test/120/67` full: 120-67 baseline.

## Current Handoff

Date: 2026-06-30
Computer: primary macOS machine
Branch: main
Last commit: see `git log -1`

Current state:

- Working tree is dirty with V4.7 clean-room source rewrite cleanup changes.
  Treat the whole tree as intentional in-progress work; do not overwrite it.
- Active script is `X5_Crop.py` V4.7.
- Current stable GitHub Release remains `v4.2.8`.
- V4.7 is intended as a clean source-layout rewrite over V4.5.4 behavior, not
  a detector-loosening release.
- Root `ARCHITECTURE.md` now mirrors `docs/ARCHITECTURE.md` as a bilingual
  developer architecture guide.

V4.7 source layout:

- Thin entry: `X5_Crop.py`
- Main package: `x5crop/`
- Active layout includes:
  - `app.py`, `config.py`, `formats.py`, `workflow.py`
  - `domain.py`, `format_specs.py`, `runtime.py`
  - `io/`, `image/`, `geometry/`, `detection/`, `diagnostics/`, `export/`
  - `policies/`, `regression/`
- Old root modules `x5crop/common.py`, `x5crop/policy.py`, `x5crop/core.py`,
  `x5crop/io.py`, `x5crop/geometry.py`, and `x5crop/regression.py` have been
  removed from active source.
- `archive/X5_Crop_v4.6/` exists as the V4.6 snapshot.

Important V4.7 behavior notes:

- Per-format policies now live in `x5crop/policies/`.
- Format parameter presets are split under `x5crop/policies/presets/`;
  `policies/parameters.py` is now a thin lookup / public export. Policy
  construction reads capability-specific parameter groups such as separator
  gate, leading-grid separator failure, separator geometry support, gap search,
  hard-gap trust, nearby separator correction, robust grid, outer strategy,
  content-floating outer, edge-anchor outer, short-axis aspect retry,
  partial holder, scoring calibration, candidate competition, content evidence,
  debug gap overlay, nearby separator diagnostics, overlap-risk diagnostics,
  lucky-pass risk, postprocess, approved geometry adjustment, detection/output
  bleed, and edge bleed protection instead of reaching into the flat preset table
  directly. Runtime calibration, wide-retry,
  content-evidence, Debug Analysis gap-overlay, nearby separator diagnostics,
  overlap-risk diagnostics, gap search, hard-gap trust, nearby separator
  correction, robust grid, grid outer refinement, content-floating outer,
  edge-anchor outer, format-geometry retry,
  short-axis aspect retry, outer content alignment, partial edge hint,
  lucky-pass risk,
  postprocess-cap, approved geometry adjustment, detection/output bleed,
  edge bleed protection, and leading-grid failure gate
  paths also read their thresholds/caps/weights from those grouped views.
- `policies/registry.py` is a thin policy resolve/cache layer. Concrete
  format/mode policy presets now live in the corresponding `format_*.py`
  modules.
- `SeparatorGatePolicy.profile` and explicit gate thresholds are the runtime
  separator-gate contract.
- `SeparatorGatePolicy.leading_grid_failure` owns the leading weak-grid
  separator failure capability; runtime gates no longer read flat
  `leading_grid_failure_*` preset fields directly.
- Format-family gate parameter names have been normalized: edge-pair and wide
  separator gate thresholds are semantic `separator_gate_*` parameters, not
  `separator_gate_120_*` names.
- `SelectionPolicy.content_mismatch_review` owns the review-only candidate
  preference for content-count mismatch cases. It defaults off and is currently
  enabled only by `half_full`.
- `SeparatorGeometrySupportPolicy` expresses `wide_geometry` and `stable_grid`
  support as generic separator capability modes. They default off and are
  currently enabled only by half full.
- `SeparatorEdgePairPolicy` is held by `DetectionPolicy.separator`; runtime
  passes it into geometry edge-pair refinement.
- `SeparatorPolicy.hard_gap_trust` controls semantic hard-gap trust thresholds
  used by robust-grid hard separator protection and read-only diagnostics;
  active geometry/diagnostics no longer read flat `hard_trust_*` preset fields
  directly.
- `SeparatorPolicy.nearby_correction` controls active nearby-separator
  correction search, score, distance, and local-geometry thresholds;
  `candidate_build.py` and `geometry/gaps.py` no longer read flat `nearby_*`
  preset fields for candidate-moving correction.
- `SeparatorPolicy.robust_grid` controls hard-gap geometry constraining,
  robust-grid fitting, reliable-gap scoring, and hard-separator protection;
  geometry/scoring runtime no longer reads flat `constrain_*` or `robust_*`
  preset fields directly.
- `SeparatorPolicy.gap_search` controls base separator gap search radius,
  width, guard, score, and wide separator acceptance thresholds; active
  geometry/candidate retry no longer reads flat `gap_*` / `wide_gap_min_*`
  preset fields directly.
- `SeparatorPolicy.profile` and `edge_refine_profile` control separator-profile
  and edge-refine-profile generation thresholds, weights, smoothing, and
  background thresholds; `geometry/separator_profile.py` no longer reads flat
  `separator_profile_*` / `edge_refine_*` preset fields directly, and detection
  plus read-only diagnostics pass the selected policy explicitly. Separator
  profile and edge-refine profile caches are keyed by the selected policy.
  Policy construction reads these values through
  `FormatParameters.separator_profile` / `edge_refine_profile` capability views
  rather than direct flat profile fields.
- `SeparatorPolicy.enhanced` controls enhanced separator analysis trigger,
  acceptance score, width, and shift limits; `geometry/core.py` no longer reads
  flat `enhanced_*` preset fields directly.
- `ContentPolicy.evidence`, `profile`, `mask`, and `candidate` own content
  evidence thresholds, content-run profile, content mask outer, and content-only
  candidate confidence caps; `detection/content.py` consumes policy instead of
  flat `content_*` preset fields or runtime `FormatParameters`.
- `FormatParameters.content_evidence`, `content_profile`, `content_mask`,
  `content_candidate`, and `content_support` are the preset-side capability
  views for constructing `ContentPolicy`; policy factory no longer reads the
  corresponding flat content fields directly.
- `SeparatorPolicy.wide_separator_confidence_cap` owns the confidence cap for
  candidates containing wide separator gaps; `calibration.py` no longer reads
  flat wide-retry confidence-cap parameters directly.
- `DarkBandOuterPolicy` expresses dark-band outer/gap parameters and full
  dark-band candidate selection. It defaults off and is currently conditional
  only for `120-66` full/partial.
- `OuterPolicy.separator_outer_allow_oversized_band` holds the 120-66 oversized
  separator-band capability; implementation code no longer checks
  `tuning.name == "120-66"`.
- `OuterPolicy.separator_gap_search_max_width_ratio` controls the gap-search
  width override for separator-derived outer candidates; `candidate_run.py` no
  longer reads flat `separator_first_outer_gap_max_width_ratio` directly.
- `OuterPolicy.separator_outer_band` and `separator_geometry_outer` control
  separator-first / separator-geometry outer proposal band thresholds, sequence
  limits, source counts, margin ratios, and candidate limits; `detection/outer.py`
  no longer reads flat `separator_first_outer_*` or
  `separator_geometry_outer_*` preset fields directly.
- `FormatParameters.content_floating_outer`, `edge_anchor_outer`,
  `base_outer_candidates`, `separator_outer_band`, and
  `separator_geometry_outer` are the preset-side capability views for
  constructing outer proposal policy objects; policy factory no longer reads the
  corresponding flat outer proposal fields directly.
- `OuterPolicy.format_geometry_retry` controls format-geometry outer retry
  enablement, ratio tolerance, shrink limits, and content margin; `outer_retry.py`
  no longer reads flat `format_geometry_outer_retry_*` preset fields directly.
- `OuterPolicy.grid_refine` controls full-strip grid-based outer refinement
  shift and width-change limits; `candidate_build.py` no longer reads flat
  `grid_outer_refine_*` preset fields directly.
- `OuterPolicy.short_axis_aspect_retry` controls short-axis aspect outer retry
  error/aspect/margins. It defaults off and is currently enabled only for
  `120-66` full; `outer_retry.py` no longer reads flat
  `short_axis_aspect_retry_*` preset fields directly.
- `OuterPolicy.content_alignment` controls outer/content alignment slack,
  white-edge detection, mismatch gates, and content-aligned retry margins;
  `outer_retry.py` and `postprocess.py` no longer read flat `outer_align_*`
  preset fields directly.
- `OuterPolicy.base_candidates` controls base outer candidate bw / white-x /
  mask-profile thresholds, margins, and candidate area limits;
  `geometry/outer_boxes.py` no longer reads flat `outer_*` preset fields or
  resolves parameters by format name.
- `OuterPolicy.content_floating_outer` and `edge_anchor_outer` own
  content-floating and long-axis edge-anchor outer proposal thresholds;
  `detection/outer.py` no longer reads flat `floating_outer_*` or
  `long_axis_edge_anchor_*` preset fields directly.
- `PartialEdgeHintPolicy` controls partial-strip edge hint window thresholds;
  `detection/partial.py` and `candidate_build.py` no longer read flat
  `partial_edge_hint_*` preset fields directly.
- `DiagnosticsPolicy.overlap_bleed_risk` controls overlap-bleed diagnostic
  attachment and overlap-risk thresholds instead of postprocess checking
  partial/half/120 directly or diagnostics reading flat `diagnostic_overlap_*`
  preset fields.
- `DiagnosticsPolicy.debug_gap_overlay` controls Debug Analysis separator-panel
  gap overlay tolerances, tick length, and line widths instead of
  `debug/render.py` reading flat `debug_gap_*` preset fields or hard-coding gap
  tick length directly.
- `DiagnosticsPolicy.nearby_separator` controls nearby-separator diagnostic
  search windows and stronger-candidate thresholds; `detection/diagnostics.py`
  no longer reads flat `nearby_*` preset fields for that diagnostic search.
- `DiagnosticsPolicy.lucky_pass_risk` controls lucky-pass risk scoring weights
  and enablement; `detection/diagnostics.py` no longer reads flat `lucky_*`
  preset fields directly for that risk score.
- `ScoringPolicy` owns candidate calibration weights, separator source bias,
  hard-full confidence floor, and no-auto caps; calibration/scoring runtime no
  longer reads `scoring_calibration` from flat format parameters directly.
- `ScoringPolicy.base_detection` owns base detector scoring weights,
  full-geometry floors, partial caps, outer-too-large caps, low-confidence
  thresholds, and the separator-incomplete reason id; `score_detection()` no
  longer reads flat `score_*` fields directly or emits the old
  `120_separator_uncertain` format-prefixed reason name.
- `ContentPolicy` owns content-support scoring norms, weights, and support
  gates used during candidate calibration; `content_support_score()` no longer
  reads flat `content_support_*` fields directly.
- `ScoringPolicy.geometry_support` owns geometry-support scoring width, outer,
  aspect, and count norms/weights plus outer-area bounds used during candidate
  calibration; `geometry_support_score()` no longer reads flat
  `geometry_support_*`, `geometry_width_cv_norm`, `content_support_aspect_norm`,
  or score outer-area fields directly.
- `ScoringPolicy.separator_support` owns separator-support hard/model weights,
  grid/equal credit, and single-frame cap used during candidate calibration;
  `separator_support_score()` no longer reads flat `separator_model_*` or
  `separator_support_*` fields directly.
- `PostprocessPolicy` owns postprocess confidence caps for content aspect
  conflict, low content evidence, outer/content mismatch, and lucky-pass risk;
  `finalize_detection_decision()` no longer receives flat tuning parameters for
  those caps. It also owns postprocess review/detail reason ids for
  outer-alignment disabled, likely partial, outer-candidate disagreement, and
  deskew uncertainty cases.
- `PostprocessPolicy.approved_geometry_adjustment` owns the approved-auto
  long-axis output geometry extension limits; `geometry/output_adjustment.py`
  no longer reads flat `approved_adjust_*` preset fields directly.
- `OutputPolicy.edge_bleed_protection` owns the full-strip output edge guard
  used after output bleed; `geometry/output_adjustment.py` no longer carries
  hard-coded edge guard ratio/min/max values.
- `OutputPolicy.overlap_risk_long_axis_bleed` owns the output-only long-axis
  bleed increase for overlap-risk cases; postprocess and cached workflow reuse
  no longer hard-code the 50px value.
- `OutputPolicy.detection_long_axis_bleed` and
  `detection_short_axis_bleed` own the bleed used during detection geometry;
  `detection_geometry_config()` no longer hard-codes zero detection bleed.
- `DetectorPolicy.dual_lane` records lane count, lane format, and unsupported
  partial reason for the 135-dual detector path.
- `DetectionPolicy.frame_fit` owns frame-fit behavior. Geometry consumes the
  policy object and no longer constructs format frame-fit defaults.
- `PartialHolderPolicy` now expresses 66 partial strict holder rules, including
  safe-extra-frames strip-mode scope, wide-like gaps, leading content, frame
  content, hard/equal gap limits, width CV, joint/content/geometry score,
  per-frame content thresholds, and frame aspect-error limits.
- `CandidateRunPolicy.content_candidate`, `FallbackPolicy`, and
  `PartialStopPolicy` now express candidate-run behavior such as content
  candidate enable/skip modes and reasons, fallback outer proposal use, and
  partial safe-auto stopping.
- `CandidateRunPolicy.separator_geometry_competition` owns the median-aspect
  thresholds, content-outer strategy scope, and strip-mode scope used to decide
  when conditional separator-geometry candidates may compete; runtime no longer
  hides those constants or mode branches in `candidate_run.py`.
- `CandidateRunPolicy.equal_first_before_wide_retry` owns equal-first wide-retry
  enablement, its wide-geometry dependency, strip-mode scope, and default-count
  requirement. The policy scope defaults to full/default-count, while the active
  support still depends on format-local wide-geometry policy.
- `CandidateRunPolicy.dark_band_retry` owns full/partial dark-band retry
  strip-mode scope, full default-count checks, and partial retry trigger
  conditions. The interface is generic, but actual activation still requires
  `OuterPolicy.dark_band` to be enabled, currently only for `120-66`
  full/partial.
- `DarkBandOuterPolicy` owns dark-band full-selection strip-mode scope and
  required-count checks; the active capability remains isolated to `120-66`.
- `ModePolicyPreset.dark_band` groups dark-band activation, full-selection, and
  oversized separator-band enablement so the 120-66 risk model stays isolated in
  policy preset construction.
- `OuterCandidate.strategy` is the runtime candidate-kind contract. Candidate
  selection/build/calibration no longer infer behavior from candidate-name
  prefixes.
- `candidate_build.py`, `candidate_run.py`, `dual_lane.py`,
  `partial_holder.py`, `outer_retry.py`, `calibration.py`, `fallback.py`,
  `cache_keys.py`, and `partial.py` hold candidate-building, candidate-running,
  specialized detector, holder, retry, candidate-calibration, fallback,
  cache-key, and partial-hint logic that used to bloat `pipeline.py`.
- Geometry is split into focused modules: `boxes.py`, `layout.py`,
  `outer_boxes.py`, `gaps.py`, `separator_profile.py`, `frame_fit.py`, and
  `output_adjustment.py`; `geometry/core.py` now holds the remaining
  cache-heavy separator helpers.
- Low-level helpers that need format context now require explicit
  `format_name`; active runtime should not keep implicit `"135"` defaults in
  deskew, gap, separator profile cache, content profile, or diagnostics helpers.
- `FormatParameters` / `format_parameters()` in `policies/parameters.py`
  replace the old active-source `FormatTuning` surface. Remaining flat fields
  are a runtime transition surface for detector/geometry helpers, not the
  policy factory or calibration/wide-retry contract.
- Runtime policy ids are written into reports.
- `ReportPolicy` owns report schema version and section order; report rows
  include `report_schema`.
- Debug Analysis has been simplified to three visual panels:
  `Original gray`, `Debug boxes`, and `Separator evidence`.
- `DiagnosticsPolicy.debug_panels` and `debug_panel_titles` own the Debug
  Analysis panel order and labels; the active renderer only exposes the current
  three-panel surface.
- `120-66` full/partial are the only modes with dark-band behavior enabled
  conditionally; other formats keep it off unless later verified.

Verified after V4.7 clean-room rewrite:

- `python3 X5_Crop.py --version` printed `X5_Crop.py 4.7`.
- Full py_compile across the V4.7 package passed.
- `git diff --check` passed.
- Legacy-residue scan had no hits for `common`, `FormatTuning`,
  `format_tuning`, `separator_gate_mode`, `score_gate_135`, `separator_135`,
  `separator_half`, `import *`, `edge_pair_params_for_format`, or
  `frame_fit_policy` under active `x5crop/`.
- V4.7 content policy runtime cleanup dry-run regressions against local V4.5.4 reports with
  `--deskew off` were written under
  `/private/tmp/x5_v47_content_policy_20260701_run1` and produced 0 core diff
  for `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`,
  and `gaps`. The run also generated 103 Debug Analysis JPGs:
  - `Test/135` full, 48 rows
  - `Test/new_135` full, 4 rows
  - `Test/120/66` full, 16 rows
  - `Test/120/66` partial, 16 rows
  - `Test/120/67` full, 4 rows
  - `Test/半格/full`, 10 rows
  - `Test/半格/partial`, 5 rows
- Counts matched V4.5.4:
  - `135` full: 43 approved / 5 review
  - `new_135` full: 4 approved / 0 review
  - `120-66` full: 16 approved / 0 review
  - `120-66` partial: 16 approved / 0 review
  - `120-67` full: 3 approved / 1 review
  - half full: 10 approved / 0 review
  - half partial: 5 approved / 0 review
- Including `detail.policy` and `report_schema` in golden comparison produced
  196 metadata-only diffs because V4.5.4 golden rows lack V4.7 policy/report
  schema metadata. There were no crop/status/confidence/gap diffs.
- Latest V4.7 candidate-run policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_candidate_run_policy_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. This run did not generate Debug Analysis JPGs.
- `ReportPolicy` smoke confirmed report schema version
  `v4_7_policy_schema_1` and sections resolve through the selected
  format/mode policy.
- Latest V4.7 report policy cleanup dry-run regressions with `--deskew off`
  were written under `/private/tmp/x5_v47_report_policy_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 dark-band candidate-run policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_dark_band_candidate_run_policy_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 selection policy cleanup dry-run regressions with `--deskew off`
  were written under `/private/tmp/x5_v47_selection_policy_20260701_run3`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 content-candidate run policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_content_candidate_run_policy_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 postprocess reason policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_postprocess_reason_policy_20260701_run1`. They produced
  0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 Debug panel policy cleanup dry-run regressions with `--deskew off`
  were written under `/private/tmp/x5_v47_debug_panel_policy_20260701_run1`.
  They produced 0 diff for `status`, `confidence`, `review_reasons`,
  `outer_box`, `frame_boxes`, and `gaps` across all seven local V4.5.4 golden
  cases. Default golden compare still produced 196 metadata-only diffs in
  `detail.policy` / `report_schema`. A focused 135 Debug Analysis smoke wrote
  `/private/tmp/x5_v47_debug_panel_policy_smoke/_debug_analysis/X5_00041_debug_analysis.jpg`
  as a 1679x876 RGB JPEG with the policy-owned three-panel labels.
- Latest V4.7 candidate-run mode policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_candidate_run_mode_policy_20260701_run1`. They produced
  0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed separator-auto content skip is scoped
  to `full`, while partial-safe content skip is scoped to `partial`.
- Latest V4.7 selection scope policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_selection_scope_policy_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`,
  and `gaps` across all seven local V4.5.4 golden cases. Default golden compare
  still produced 196 metadata-only diffs in `detail.policy` / `report_schema`.
  Policy smoke confirmed only `half_full` enables content mismatch review, scoped
  to `full` and default count.
- Latest V4.7 dark-band selection scope cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_dark_band_selection_scope_20260701_run1`. They produced
  0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed only `120_66_full` /
  `120_66_partial` enable dark-band full-selection capability, scoped to `full`
  and required count.
- Latest V4.7 dark-band retry scope cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_dark_band_retry_scope_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`,
  and `gaps` across all seven local V4.5.4 golden cases. Default golden compare
  still produced 196 metadata-only diffs in `detail.policy` / `report_schema`.
  Policy smoke confirmed only `120_66_full` / `120_66_partial` enable dark-band,
  retry scope is `full` / `partial`, and full retry requires default count.
- Latest V4.7 equal-first wide-retry policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_equal_first_wide_retry_policy_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed equal-first wide-retry scope is `full`
  and default count, while actual wide geometry support remains only `half_full`.
- Latest V4.7 partial-holder scope policy cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_partial_holder_scope_policy_20260701_run1`. They produced
  0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed partial-holder safe-extra-frames scope
  is `partial`, and strict holder remains enabled only for `120_66_partial`.
- Latest V4.7 separator-geometry competition scope cleanup dry-run regressions
  with `--deskew off` were written under
  `/private/tmp/x5_v47_separator_geometry_competition_scope_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed content-outer max median-aspect cap
  scope is strategy `content_outer` and strip mode `partial`.
- Latest V4.7 separator-incomplete reason cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_separator_uncertain_reason_policy_20260701_run1`. They
  produced 0 diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed every format/mode resolves the
  semantic `separator_evidence_incomplete` reason id through
  `ScoringPolicy.base_detection`.
- Latest V4.7 implicit-135 default cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_no_implicit_135_default_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`.
- Latest V4.7 dark-band mode-preset cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_dark_band_mode_preset_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed dark-band / oversized separator-band
  enablement remains limited to `120_66_full` and `120_66_partial`.
- Latest V4.7 separator-profile parameter-view cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_profile_parameter_views_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed all 14 policies resolve
  `SeparatorPolicy.profile` / `edge_refine_profile` through the new preset
  capability views.
- Latest V4.7 content/geometry-support parameter-view cleanup dry-run
  regressions with `--deskew off` were written under
  `/private/tmp/x5_v47_content_parameter_views_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed all 14 policies resolve
  `ContentPolicy` and `ScoringPolicy.geometry_support` through preset-side
  capability views.
- Latest V4.7 outer-proposal parameter-view cleanup dry-run regressions with
  `--deskew off` were written under
  `/private/tmp/x5_v47_outer_parameter_views_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. Policy smoke confirmed all 14 policies resolve content
  floating outer, edge-anchor outer, base outer candidates, separator outer band,
  and separator-geometry outer through preset-side capability views.
- Latest V4.7 final policy-readiness dry-run regressions with `--deskew off`
  were written under
  `/private/tmp/x5_v47_final_policy_readiness_20260701_run1`. They produced 0
  diff for `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` across all seven local V4.5.4 golden cases. Default
  golden compare still produced 196 metadata-only diffs in `detail.policy` /
  `report_schema`. A focused Debug Analysis smoke wrote
  `/private/tmp/x5_v47_final_debug_smoke_20260701/_debug_analysis/X5_00041_debug_analysis.jpg`
  as a 1679x876 RGB JPEG, and policy smoke confirmed the three panel titles and
  Debug gap tick parameters come from `DiagnosticsPolicy`.
- Policy smoke confirmed 14 supported format/mode policies resolve; only
  `half_full` enables `SelectionPolicy.content_mismatch_review`.
- Current residue scan has no hits for candidate-name `startswith()` strategy
  inference, old outer mode helper/adapters, `separator_gate_120_*`, old
  format-prefixed separator gate/scoring reason ids such as
  `120_separator_uncertain`, `FormatTuning`, `format_tuning`, `import *`,
  `edge_pair_params_for_format`, `frame_fit_policy`, or implicit
  `format_name: str = "135"` defaults.
- Policy factory residue scan has no direct flat-field hits for separator gate,
  score gate, partial-safe holder, candidate competition, calibration caps,
  outer strategy, wide retry, outer retry, leading-grid failure, nearby
  separator diagnostics, overlap-risk diagnostics, hard-gap trust, nearby
  separator correction, robust grid, gap search, or lucky-pass risk
  parameters; it now reads grouped capability parameters from
  `FormatParameters`.
- Scoring runtime residue scan has no direct hits for
  `tuning.scoring_calibration`, `policy.parameters.scoring_calibration`, or
  `scoring_calibration` under active detection/geometry/workflow runtime; those
  paths now read `ScoringPolicy`.
- Base scoring residue scan has no direct `score_*` flat-field reads in
  `score_detection()`; those paths now read `ScoringPolicy.base_detection`.
- Content-support scoring residue scan has no direct hits for
  `content_conf_*` or `content_support_*` flat-field reads in
  `content_support_score()` / candidate calibration; those paths now read
  `ContentPolicy`.
- Content runtime residue scan has no direct hits for `format_parameters()`,
  `tuning.content*`, or `policy.parameters` in `detection/content.py`; content
  evidence, profile, mask, and content-only candidate confidence now read
  `ContentPolicy` sub-policies.
- Geometry-support scoring residue scan has no direct hits for
  `geometry_support_*`, `geometry_width_cv_norm`, `content_support_aspect_norm`,
  or score outer-area flat-field reads in `geometry_support_score()` /
  candidate calibration; those paths now read `ScoringPolicy.geometry_support`.
- `FormatParameters.geometry_support_score` is the preset-side capability view
  for constructing `ScoringPolicy.geometry_support`; policy factory no longer
  reads the flat geometry-support score fields directly.
- Separator-support scoring residue scan has no direct hits for
  `separator_model_*` or `separator_support_*` flat-field reads in
  `separator_support_score()` / candidate calibration; those paths now read
  `ScoringPolicy.separator_support`.
- Wide-retry and content-evidence runtime residue scans have no
  direct flat-field hits for `tuning.wide_retry`, `tuning.wide_gap_retry_*`,
  `tuning.wide_gap_confidence_cap`, `tuning.content_evidence_*`, or
  `format_parameters(...).content_evidence_*`; those paths now read
  `SeparatorPolicy.wide_separator_confidence_cap`, `wide_retry`, and
  `content_evidence` grouped parameters.
- Partial-holder frame-content residue scan has no direct
  `policy.parameters.content_evidence` hit in `x5crop/detection/partial_holder.py`;
  frame aspect conflict checks now read `PartialHolderPolicy`.
- Candidate-run separator outer gap override residue scan has no direct
  `format_parameters()` or `separator_first_outer_gap_max_width_ratio` hits in
  `x5crop/detection/candidate_run.py`; runtime now reads
  `OuterPolicy.separator_gap_search_max_width_ratio`.
- Separator-derived outer proposer residue scan has no direct `FormatParameters`,
  `format_parameters()`, `tuning.*`, `separator_first_outer_*`, or
  `separator_geometry_outer_*` flat-field reads in `x5crop/detection/outer.py`;
  runtime now reads `OuterPolicy.separator_outer_band`,
  `OuterPolicy.separator_geometry_outer`, and `SeparatorPolicy.gap_search`.
- Base outer candidate residue scan has no direct `FormatParameters`,
  `format_parameters()`, `tuning.*`, or flat `outer_*` candidate-threshold reads
  in `x5crop/geometry/outer_boxes.py`, `x5crop/detection/outer.py`, or
  `x5crop/detection/dual_lane.py`; runtime now reads
  `OuterPolicy.base_candidates`.
- Separator profile residue scan has no direct `format_parameters()`,
  `tuning.*`, `separator_profile_*`, or `edge_refine_*` flat-field reads in
  `x5crop/geometry/separator_profile.py`, `x5crop/detection/candidate_build.py`,
  `x5crop/detection/outer.py`, or `x5crop/detection/diagnostics.py`; runtime now
  reads `SeparatorPolicy.profile` and `SeparatorPolicy.edge_refine_profile`, and
  cache keys include the selected profile policy.
- Enhanced separator residue scan has no direct `format_parameters()`,
  `tuning.*`, or flat `enhanced_*` preset-field reads in `x5crop/geometry/core.py`
  or `x5crop/detection/candidate_build.py`; runtime now reads
  `SeparatorPolicy.enhanced`, and the policy factory reads the
  `enhanced_separator` parameter group.
- Format-geometry retry residue scan has no direct flat-field hits for
  `format_geometry_outer_retry_*` outside `x5crop/policies/**`; runtime now
  reads `OuterPolicy.format_geometry_retry`.
- Grid outer-refine residue scan has no direct flat-field hits for
  `grid_outer_refine_*` outside `x5crop/policies/**`; runtime now reads
  `OuterPolicy.grid_refine`.
- Short-axis aspect retry residue scan has no direct flat-field hits for
  `short_axis_aspect_retry_*` in `x5crop/detection/outer_retry.py`; runtime now
  reads `OuterPolicy.short_axis_aspect_retry`.
- Outer content-alignment residue scan has no direct flat-field hits for
  `outer_align_*` in `x5crop/detection/outer_retry.py` or
  `x5crop/detection/postprocess.py`; runtime now reads
  `OuterPolicy.content_alignment`.
- Content-floating / edge-anchor outer residue scan has no direct flat-field hits
  for `floating_outer_*` or `long_axis_edge_anchor_*` in
  `x5crop/detection/outer.py`; runtime now reads
  `OuterPolicy.content_floating_outer` and `OuterPolicy.edge_anchor_outer`.
- Partial edge-hint residue scan has no direct flat-field hits for
  `partial_edge_hint_*` outside `x5crop/policies/**`; runtime now reads
  `PartialEdgeHintPolicy`.
- Debug Analysis gap-overlay residue scan has no direct flat-field hits for
  `format_parameters()` or `debug_gap_*` in `x5crop/debug/render.py`; rendering
  now reads `DiagnosticsPolicy.debug_gap_overlay` for overlay tolerance, tick
  length, and line widths.
- Postprocess-cap residue scan has no direct flat-field hits for
  `tuning.post_*_cap` in `x5crop/detection/postprocess.py`; final decision
  caps now read from `PostprocessPolicy`.
- Approved geometry adjustment residue scan has no direct flat-field hits for
  `approved_adjust_*` outside `x5crop/policies/**`; runtime now reads
  `PostprocessPolicy.approved_geometry_adjustment`.
- Edge bleed protection residue scan has no hard-coded
  `max(70.0, min(120.0, nominal * 0.0150))` style guard in active runtime;
  runtime now reads `OutputPolicy.edge_bleed_protection`.
- Overlap-risk output bleed residue scan has no active-runtime
  `max(int(config.bleed_x), 50)` hard-code; runtime now reads
  `OutputPolicy.overlap_risk_long_axis_bleed`.
- Detection bleed residue scan has no hard-coded `bleed_x=0` / `bleed_y=0`
  in active runtime; runtime now reads `OutputPolicy.detection_*_bleed`.
- A focused 135 Debug Analysis smoke produced
  `/private/tmp/x5_v47_final_debug_smoke_20260701/_debug_analysis/X5_00041_debug_analysis.jpg`
  as a 1679x876 RGB JPEG with policy-owned three-panel titles and Debug gap
  tick parameters.

Not verified:

- Default-deskew export timing for V4.7.
- `xpan`, `120-645`, and `135-dual` full sample comparisons, because local
  golden reports were not listed.
- Release package generation.

Known local-only / ignored files:

- `Test/` contains local scripts, packages, TIFF samples, and generated
  reports/debug outputs.
- V4.7 temporary verification outputs were written under `/private/tmp/`.
- `__pycache__/` may exist from compile checks and remains ignored.

Next recommended step:

- If continuing V4.7, run default-deskew/export timing before any release call.
- If publishing, build the standalone Release package from V4.7, run default
  deskew/export timing, and decide whether V4.7 should supersede stable
  `v4.2.8`.
