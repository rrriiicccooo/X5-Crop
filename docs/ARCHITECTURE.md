# X5 Crop Architecture Map

This document is the working map for the V4.7 clean-room source layout. It is
developer-facing and should stay shorter than the user README.

## Runtime Layers

1. `x5crop.cli`
   - Parses command-line arguments and prints progress.
   - Delegates file processing to `x5crop.workflow`.

2. `x5crop.workflow`
   - Owns the read -> deskew -> detect -> postprocess -> export -> report/debug
     orchestration for one file or a batch.
   - Does not implement detector scoring or TIFF write policy itself.

3. `x5crop.policies`
   - Resolves one `DetectionPolicy` for each format and strip mode.
   - `registry.py` only resolves and caches policies; each `format_*.py` module
     owns its concrete format/mode preset.
   - `parameters.py` is a thin lookup / public export. Concrete format
     parameter presets live under `policies/presets/`.
   - Policy construction reads preset values through capability-specific
     parameter groups: partial counts, separator gate, leading-grid separator
     failure, separator geometry support, gap search, hard-gap trust, nearby
     separator correction, robust grid, grid outer refinement, wide retry,
     outer strategy, content-floating outer, edge-anchor outer,
     format-geometry retry, short-axis aspect retry,
     outer content alignment, partial edge hint,
     partial holder, scoring
     calibration, candidate competition, content evidence, debug gap overlay,
     nearby separator diagnostics, overlap-risk diagnostics, lucky-pass risk,
     postprocess, approved geometry adjustment, detection/output bleed, and edge bleed protection. Candidate calibration, wide retry,
     content-evidence runtime, Debug Analysis gap-overlay paths, nearby
     separator diagnostics, overlap-risk diagnostics, gap search, hard-gap
     trust, nearby separator correction, robust grid, grid outer refinement,
     content-floating outer, edge-anchor outer,
     format-geometry retry, short-axis aspect retry, outer content alignment,
     partial edge hint, lucky-pass risk scoring, postprocess final caps,
     approved geometry adjustment, detection/output bleed, edge bleed protection, and leading-grid failure gates also read their caps, weights,
     retry width, evidence thresholds, overlay line settings, nearby search
     thresholds, separator search radius/width/guard/score, wide separator
     acceptance thresholds, nearby correction thresholds, robust-grid
     thresholds, short-axis aspect retry error/aspect/margins, outer/content
     alignment slack and retry margins, overlap risk thresholds, trust
     thresholds, risk weights, final REVIEW caps, and gate
     limits through grouped views.
     Remaining flat
     `FormatParameters` fields are a
     detector/geometry migration surface, not the policy factory,
     calibration/base scoring/content-support scoring/geometry-support scoring/separator-support scoring/wide-retry, gap-search, grid outer refinement,
     base outer candidates, separator-derived outer proposals, content-floating outer, edge-anchor outer, format-geometry retry,
     short-axis aspect retry, outer content-alignment,
     partial holder frame-content checks, partial edge-hint,
     approved geometry adjustment, detection/output bleed, or edge bleed protection contract.
   - Policy is the behavior entry point for detector kind, count planning,
     outer proposals, separator/content gates, candidate-run behavior,
     partial-holder safety, frame fitting, selection, postprocess, output, and
     diagnostics.
   - `FrameFitPolicy` and separator edge-pair parameters are owned by policy.
     Geometry consumes policy objects and does not construct format defaults.
   - Separator gate behavior is expressed through `SeparatorGatePolicy`
     profiles, explicit thresholds, and the `leading_grid_failure` sub-policy.
   - Separator geometry support, separator profile generation, edge-refine
     profile generation, enhanced separator analysis, gap search, hard-gap trust, nearby separator correction,
     robust grid, grid outer refinement, base outer candidates,
     separator-derived outer proposals,
     content-floating outer,
     edge-anchor outer, format-geometry retry,
     short-axis aspect retry, outer content alignment, partial edge hint,
     dark-band outer proposals,
     dual-lane detector metadata, postprocess caps, approved geometry adjustment,
     partial-holder frame-content checks, detection/output bleed, edge bleed protection, overlap-bleed diagnostics, nearby-separator diagnostics, lucky-pass risk,
     and Debug gap-overlay rendering have
     dedicated policy surfaces.
   - `OuterPolicy.separator_gap_search_max_width_ratio` owns the gap-search
     width override for separator-derived outer candidates. Candidate runtime
     should not read flat separator-first outer fields directly.
   - `OuterPolicy.separator_outer_band` and `separator_geometry_outer` own
     separator-first / separator-geometry outer proposal band thresholds,
     sequence limits, source counts, margin ratios, and candidate limits.
     Outer proposal code should consume policy, not flat
     `separator_first_outer_*` or `separator_geometry_outer_*` preset fields.
   - `OuterPolicy.base_candidates` owns base outer candidate bw / white-x /
     mask-profile thresholds, margins, and candidate area limits. Geometry should
     consume policy, not resolve flat `outer_*` preset fields by format name.
   - `FormatParameters.content_floating_outer`, `edge_anchor_outer`,
     `base_outer_candidates`, `separator_outer_band`, and
     `separator_geometry_outer` are the preset-side capability views for
     constructing outer proposal policy objects. Policy construction should not
     read the corresponding flat outer proposal fields directly.
   - `SeparatorPolicy.profile` and `edge_refine_profile` own separator-profile
     and edge-refine-profile thresholds, smoothing, weights, and background
     thresholds. Geometry and diagnostics should consume policy, not flat
     `separator_profile_*` or `edge_refine_*` preset fields. Cache keys for
     these profiles should include the selected policy.
   - `FormatParameters.separator_profile` and `edge_refine_profile` are the
     preset-side capability views for constructing those policy objects; policy
     construction should not read the flat profile fields directly.
   - `SeparatorPolicy.enhanced` owns enhanced separator trigger and acceptance
     thresholds. Geometry should consume policy, not flat `enhanced_*` preset
     fields.
   - `SeparatorPolicy.wide_separator_confidence_cap` owns the confidence cap for
     candidates containing wide separator gaps. Calibration should consume the
     selected policy, not flat wide-retry confidence-cap fields.
   - `ScoringPolicy` owns candidate calibration weights, separator source bias,
     hard-full confidence floor, and no-auto caps. Calibration and scoring code
     should consume policy, not flat `scoring_calibration` fields.
   - `ScoringPolicy.base_detection` owns base detector scoring weights,
     full-geometry floors, partial caps, outer-too-large caps, and
     low-confidence thresholds plus the semantic separator-incomplete reason
     id. `score_detection()` should consume policy, not flat `score_*` preset
     fields or old format-prefixed reason names.
   - `ContentPolicy` owns content-support score norms, weights, and support
     gates used by candidate calibration. Content support scoring should consume
     policy, not flat `content_support_*` preset fields.
   - `ContentPolicy.evidence`, `profile`, `mask`, and `candidate` own content
     evidence thresholds, content-run profile, content mask outer, and
     content-only candidate confidence caps. Content runtime should consume
     policy, not flat `content_*` preset fields or runtime `FormatParameters`.
   - `FormatParameters.content_evidence`, `content_profile`, `content_mask`,
     `content_candidate`, and `content_support` are the preset-side capability
     views for constructing `ContentPolicy`. Policy construction should not read
     the flat content fields directly.
   - `ScoringPolicy.geometry_support` owns geometry-support score width/outer/
     aspect/count norms, weights, and outer-area bounds used by candidate
     calibration. Geometry support scoring should consume policy, not flat
     `geometry_support_*`, `geometry_width_cv_norm`,
     `content_support_aspect_norm`, or score outer-area preset fields.
   - `FormatParameters.geometry_support_score` is the preset-side capability
     view for constructing `ScoringPolicy.geometry_support`. Policy
     construction should not read the flat geometry-support score fields
     directly.
   - `ScoringPolicy.separator_support` owns separator-support hard/model
     weights, grid/equal credit, and single-frame cap. Separator support scoring
     should consume policy, not flat `separator_model_*` or
     `separator_support_*` preset fields.
   - `OuterPolicy.format_geometry_retry` owns full-strip format-geometry outer
     retry thresholds. Runtime should consume the policy object, not flat
     `format_geometry_outer_retry_*` preset fields.
   - `OuterPolicy.grid_refine` owns full-strip grid-based outer refinement
     shift and width-change limits. Candidate-building code should consume the
     policy object, not flat `grid_outer_refine_*` preset fields.
   - `OuterPolicy.content_floating_outer` and `edge_anchor_outer` own
     content-floating and long-axis edge-anchor proposal thresholds. Outer
     proposal code should consume policy, not flat `floating_outer_*` or
     `long_axis_edge_anchor_*` preset fields.
   - `OuterPolicy.short_axis_aspect_retry` owns the short-axis aspect retry
     thresholds. The interface is general, but activation stays format/mode
     local; currently only 120-66 full enables it.
     Generalizing the interface must not generalize activation.
   - `OuterPolicy.content_alignment` owns outer/content alignment thresholds
     and content-aligned retry margins. Runtime should consume the policy
     object, not flat `outer_align_*` preset fields.
   - `PostprocessPolicy` owns final confidence caps plus postprocess
     review/detail reason ids such as likely partial, outer-candidate
     disagreement, deskew uncertainty, and outer-alignment disabled.
   - `PartialEdgeHintPolicy` owns partial-strip edge hint window thresholds.
     Candidate-building code should consume policy, not flat
     `partial_edge_hint_*` preset fields.
   - `PartialHolderPolicy` owns strict-holder safe-extra-frames strip-mode scope
     and content/geometry safety thresholds.
   - `CandidateRunPolicy`, `FallbackPolicy`, and `PartialStopPolicy` describe
     candidate-run control flow; they should be adjusted through policy, not
     through scattered mode branches.
   - `CandidateRunPolicy.content_candidate` owns content-candidate enablement,
     separator-auto skip modes, and skip reasons. `PartialStopPolicy` owns
     partial safe-auto stop/skip behavior, skip modes, and report reasons.
   - `CandidateRunPolicy.separator_geometry_competition` owns the median-aspect
     thresholds, content-outer strategy scope, and strip-mode scope for
     conditional separator-geometry candidate competition.
   - `CandidateRunPolicy.equal_first_before_wide_retry` owns equal-first
     wide-retry enablement, wide-geometry dependency, strip-mode scope, and
     default-count requirement.
   - `CandidateRunPolicy.dark_band_retry` owns dark-band retry strip-mode scope,
     full default-count checks, and partial retry trigger conditions; activation
     still depends on format-local `OuterPolicy.dark_band`.
     `DarkBandOuterPolicy` owns dark-band full-selection strip-mode scope and
     required-count checks.
   - `ModePolicyPreset.dark_band` groups dark-band activation,
     full-selection, and oversized separator-band enablement so 120-66
     dark-band behavior remains isolated at preset construction time.
   - `SelectionPolicy.content_mismatch_review` owns the review-only fallback
     preference, strip-mode scope, and default-count requirement when a content
     candidate has a count mismatch. The interface is general, but activation
     stays format/mode local; currently only `half_full` enables it.
   - `DiagnosticsPolicy.debug_gap_overlay` owns Debug Analysis separator-panel
     gap overlay tolerance, tick length, and line widths. Debug rendering should
     consume policy, not hard-code overlay geometry.
   - `DiagnosticsPolicy.debug_panels` and `debug_panel_titles` own Debug Analysis
     panel order and labels. The active renderer exposes only the current
     `Original gray`, `Debug boxes`, and `Separator evidence` surface.
   - `ReportPolicy` owns report schema version and report section order.
   - Capabilities may be shared, but defaults must remain format-local.

4. `x5crop.detection`
   - Builds candidates, calibrates evidence, applies gates, selects a detection,
     and produces stable report detail.
   - `outer.py`, `content.py`, `separator.py`, `candidates.py`, `scoring.py`,
     `gates.py`, and `selection.py` own real implementation, not re-export
     wrappers.
   - `candidate_build.py`, `candidate_run.py`, `calibration.py`, `fallback.py`,
     `cache_keys.py`, `partial.py`, `dual_lane.py`, `partial_holder.py`, and
     `outer_retry.py` keep candidate-building, candidate-running, candidate
     calibration, fallback, cache-key, partial-hint, detector, holder, and retry
     logic out of the main pipeline orchestration.
   - `OuterCandidate.strategy` is the candidate-kind contract. Runtime code
     should not infer dark-band, separator-first, edge-anchor, or retry behavior
     from candidate-name prefixes.
   - Format-specific behavior should be expressed through policy capabilities,
     not scattered `fmt.name` branches.

5. `x5crop.geometry`, `x5crop.image`, `x5crop.io`
   - Provide lower-level geometry, evidence image, deskew, and TIFF helpers.
   - Helpers that need format context should require an explicit `format_name`;
     they should not fall back to an implicit 135 default.
   - Geometry is split into focused modules such as `boxes.py`, `layout.py`,
     `outer_boxes.py`, `gaps.py`, `separator_profile.py`, `frame_fit.py`, and
     `output_adjustment.py`. `core.py` should keep only remaining cache-heavy
     separator helpers.
   - These layers should not import detection pipeline modules.
   - Root-level compatibility modules such as `common.py`, `core.py`, `io.py`,
     `geometry.py`, `policy.py`, and `regression.py` are intentionally absent.

6. `x5crop.reports`, `x5crop.debug`, `x5crop.regression`
   - Consume stable `Detection` / `ProcessResult` / report-schema data.
   - They should not reach into candidate generation internals.

## Guardrails

- The V4.5.4 `Test/` reports are the golden behavior baseline.
- Refactors should target 0 core diff before behavior changes are considered.
- `120-66` dark-band and square-frame constraints are isolated capabilities:
  generalize the interface, not the default activation.
- Weak `grid`, `equal`, or content-only evidence must not gain auto-pass
  authority through structural cleanup.
- TIFF metadata, bit depth, ICC/resolution, and compression behavior are part
  of the public contract.

## Verification Surface

- Use `python3 -m x5crop.regression.golden --candidate-root <candidate-root>`
  for V4.5.4 golden comparisons.
- Core regression fields are `status`, `confidence`, `review_reasons`,
  `outer_box`, `frame_boxes`, and `gaps`.
- `detail.policy` and `report_schema` are expected to differ from V4.5.4
  golden reports because those reports predate the policy/report-schema
  metadata.
