from __future__ import annotations

from ..formats import FORMATS
from .base import (
    FULL,
    PARTIAL,
    ApprovedGeometryAdjustmentPolicy,
    BaseDetectionScorePolicy,
    CandidateRunPolicy,
    ContentCandidatePolicy,
    ContentEvidencePolicy,
    ContentMismatchReviewSelectionPolicy,
    ContentPolicy,
    ContentFloatingOuterPolicy,
    ContentMaskPolicy,
    ContentProfilePolicy,
    CountPolicy,
    DarkBandOuterPolicy,
    DebugGapOverlayPolicy,
    DetectionPolicy,
    DetectorPolicy,
    EdgeAnchorOuterPolicy,
    FormatGeometryRetryPolicy,
    FrameFitPolicy,
    FallbackPolicy,
    GatePolicy,
    GapSearchPolicy,
    GeometrySupportScorePolicy,
    GridOuterRefinePolicy,
    HardGapTrustPolicy,
    LeadingGridFailurePolicy,
    LuckyPassRiskPolicy,
    NearbySeparatorCorrectionPolicy,
    NearbySeparatorDiagnosticsPolicy,
    OuterCandidateDetectionPolicy,
    OuterContentAlignmentPolicy,
    OuterMaskProfilePolicy,
    OuterPolicy,
    OverlapBleedRiskPolicy,
    PartialEdgeHintPolicy,
    PartialHolderPolicy,
    PartialStopPolicy,
    PostprocessPolicy,
    ReportPolicy,
    RobustGridPolicy,
    RuntimeDiagnosticsPolicy,
    ScoringPolicy,
    SelectionPolicy,
    SeparatorEdgePairPolicy,
    EnhancedSeparatorPolicy,
    SeparatorGatePolicy,
    SeparatorGeometryOuterPolicy,
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorOuterBandPolicy,
    SeparatorProfilePolicy,
    SeparatorSupportScorePolicy,
    SeparatorPolicy,
    ShortAxisAspectRetryPolicy,
    EdgeRefineProfilePolicy,
)
from .ids import detection_policy_id_for
from .factory_presets import DarkBandModePreset, FormatPolicyPreset, ModePolicyPreset
from .parameters import FormatParameters


def partial_frame_fit(format_id: str) -> FrameFitPolicy:
    return FrameFitPolicy(
        name=f"{format_id}-partial",
        edge_evidence=False,
        geometry_fallback=True,
    )


def count_policy(fmt_id: str, strip_mode: str, params: FormatParameters) -> CountPolicy:
    fmt = FORMATS[fmt_id]
    if strip_mode == FULL:
        return CountPolicy(fixed_count=None, auto_counts=(fmt.default_count,))
    partial = params.partial_counts
    return CountPolicy(
        fixed_count=None,
        auto_counts=tuple(reversed(fmt.allowed_counts)),
        partial_offsets=partial.offsets,
        include_default_in_partial_auto=bool(partial.include_default_auto),
    )


def separator_gate_policy(
    preset: FormatPolicyPreset,
    params: FormatParameters,
) -> SeparatorGatePolicy:
    gate = params.separator_gate
    leading_grid = params.leading_grid_failure
    return SeparatorGatePolicy(
        profile=preset.separator_gate_profile,
        needed_hard_max=int(gate.needed_hard_max),
        max_equal_gaps_floor=int(gate.max_equal_gaps_floor),
        allow_geometry_support=bool(gate.allow_geometry_support),
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        edge_pair_min_score_without_wide=float(gate.edge_pair_min_score_without_wide),
        edge_pair_min_score_with_wide=float(gate.edge_pair_min_score_with_wide),
        min_wide_gaps_for_auto=int(gate.min_wide_gaps_for_auto),
        score_min_hard_gaps=int(gate.score_min_hard_gaps),
        score_max_equal_gaps_floor=int(gate.score_max_equal_gaps_floor),
        low_hard_confidence_cap=float(gate.low_hard_confidence_cap),
        mostly_equal_confidence_cap=float(gate.mostly_equal_confidence_cap),
        allow_full_detected_geometry=bool(gate.allow_full_detected_geometry),
        leading_grid_failure=LeadingGridFailurePolicy(
            enabled=bool(leading_grid.enabled),
            min_expected_gaps=int(leading_grid.min_expected_gaps),
            leading_count=int(leading_grid.leading_count),
            low_score=float(leading_grid.low_score),
            very_low_score=float(leading_grid.very_low_score),
            very_low_count=int(leading_grid.very_low_count),
            max_hard_gaps=int(leading_grid.max_hard_gaps),
        ),
    )


def separator_geometry_support_policy(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorGeometrySupportPolicy:
    if not mode_preset.separator_geometry_support_modes:
        return SeparatorGeometrySupportPolicy()
    support = params.separator_geometry_support
    mode_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.wide_geometry_min_hard_ratio),
        min_joint_score=float(support.wide_geometry_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_width_cv=float(support.max_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    stable_grid_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.stable_grid_min_hard_ratio),
        min_joint_score=float(support.stable_grid_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_width_cv=float(support.max_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    return SeparatorGeometrySupportPolicy(
        wide_geometry=mode_policy if "wide_geometry" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
        stable_grid=stable_grid_policy if "stable_grid" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
    )


def separator_policy(
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> SeparatorPolicy:
    gate = separator_gate_policy(preset, params)
    wide_retry = params.wide_retry
    hard_gap_trust = params.hard_gap_trust
    nearby_correction = params.nearby_separator_correction
    robust_grid = params.robust_grid
    gap_search = params.gap_search
    enhanced = params.enhanced_separator
    profile = params.separator_profile
    edge_refine = params.edge_refine_profile
    return SeparatorPolicy(
        gate=gate,
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        wide_retry=bool(
            (strip_mode == FULL and wide_retry.full_enabled)
            or (strip_mode == PARTIAL and wide_retry.partial_enabled)
        ),
        wide_retry_max_width_ratio=float(wide_retry.max_width_ratio),
        wide_separator_confidence_cap=float(wide_retry.confidence_cap),
        geometry_support_modes=mode_preset.separator_geometry_support_modes,
        geometry_support=separator_geometry_support_policy(mode_preset, params),
        edge_pair=preset.separator_edge_pair,
        hard_gap_trust=HardGapTrustPolicy(
            guard_ratio=float(hard_gap_trust.guard_ratio),
            guard_min=int(hard_gap_trust.guard_min),
            guard_max=int(hard_gap_trust.guard_max),
            narrow_ratio=float(hard_gap_trust.narrow_ratio),
            narrow_min=float(hard_gap_trust.narrow_min),
            narrow_max=float(hard_gap_trust.narrow_max),
            model_delta_ratio=float(hard_gap_trust.model_delta_ratio),
            geometry_width_ratio=float(hard_gap_trust.geometry_width_ratio),
            strong_min_score=float(hard_gap_trust.strong_min_score),
            strong_width_min=float(hard_gap_trust.strong_width_min),
            strong_width_max=float(hard_gap_trust.strong_width_max),
            narrow_ok_score=float(hard_gap_trust.narrow_ok_score),
            narrow_ok_width_min=float(hard_gap_trust.narrow_ok_width_min),
            narrow_ok_width_max=float(hard_gap_trust.narrow_ok_width_max),
            model_conflict_score=float(hard_gap_trust.model_conflict_score),
            core_content_threshold=int(hard_gap_trust.core_content_threshold),
            core_dark_threshold=int(hard_gap_trust.core_dark_threshold),
            dark_mean_max=float(hard_gap_trust.dark_mean_max),
            dark_fraction_min=float(hard_gap_trust.dark_fraction_min),
            dark_activity_max=float(hard_gap_trust.dark_activity_max),
            strong_core_content_max=float(hard_gap_trust.strong_core_content_max),
            weak_mean_min=float(hard_gap_trust.weak_mean_min),
            weak_content_min=float(hard_gap_trust.weak_content_min),
            frame_border_width_ratio=float(hard_gap_trust.frame_border_width_ratio),
            continuity_min=float(hard_gap_trust.continuity_min),
            activity_min=float(hard_gap_trust.activity_min),
        ),
        nearby_correction=NearbySeparatorCorrectionPolicy(
            enabled=bool(nearby_correction.enabled),
            window_ratio=float(nearby_correction.window_ratio),
            window_min=int(nearby_correction.window_min),
            window_max=int(nearby_correction.window_max),
            exclude_ratio=float(nearby_correction.exclude_ratio),
            exclude_min=int(nearby_correction.exclude_min),
            exclude_max=int(nearby_correction.exclude_max),
            max_width_ratio=float(nearby_correction.max_width_ratio),
            max_width_min=int(nearby_correction.max_width_min),
            max_width_max=int(nearby_correction.max_width_max),
            distance_ratio=float(nearby_correction.distance_ratio),
            score_add=float(nearby_correction.score_add),
            score_multiplier=float(nearby_correction.score_multiplier),
            local_gain_ratio=float(nearby_correction.local_gain_ratio),
            local_gain_min=float(nearby_correction.local_gain_min),
            local_gain_max=float(nearby_correction.local_gain_max),
        ),
        robust_grid=RobustGridPolicy(
            constrain_full_shift_ratio=float(robust_grid.constrain_full_shift_ratio),
            constrain_partial_shift_ratio=float(robust_grid.constrain_partial_shift_ratio),
            constrain_shift_min=float(robust_grid.constrain_shift_min),
            constrain_shift_max=float(robust_grid.constrain_shift_max),
            reliable_min_score=float(robust_grid.reliable_min_score),
            min_reliable=int(robust_grid.min_reliable),
            pitch_min_ratio=float(robust_grid.pitch_min_ratio),
            pitch_max_ratio=float(robust_grid.pitch_max_ratio),
            full_tolerance_ratio=float(robust_grid.full_tolerance_ratio),
            partial_tolerance_ratio=float(robust_grid.partial_tolerance_ratio),
            tolerance_min=float(robust_grid.tolerance_min),
            tolerance_max=float(robust_grid.tolerance_max),
            reject_residual_ratio=float(robust_grid.reject_residual_ratio),
            full_shift_ratio=float(robust_grid.full_shift_ratio),
            partial_shift_ratio=float(robust_grid.partial_shift_ratio),
            shift_min=float(robust_grid.shift_min),
            shift_max=float(robust_grid.shift_max),
            hard_keep_ratio=float(robust_grid.hard_keep_ratio),
            hard_keep_min=float(robust_grid.hard_keep_min),
            hard_keep_max=float(robust_grid.hard_keep_max),
            hard_protect_ratio=float(robust_grid.hard_protect_ratio),
            hard_protect_min=float(robust_grid.hard_protect_min),
            hard_protect_max=float(robust_grid.hard_protect_max),
        ),
        gap_search=GapSearchPolicy(
            radius_ratio=float(gap_search.radius_ratio),
            radius_min=int(gap_search.radius_min),
            radius_max=int(gap_search.radius_max),
            max_width_ratio=float(gap_search.max_width_ratio),
            max_width_min=int(gap_search.max_width_min),
            max_width_max=int(gap_search.max_width_max),
            min_width_ratio=float(gap_search.min_width_ratio),
            min_width_min=int(gap_search.min_width_min),
            min_width_max=int(gap_search.min_width_max),
            guard_ratio=float(gap_search.guard_ratio),
            guard_min=int(gap_search.guard_min),
            guard_max=int(gap_search.guard_max),
            min_score=float(gap_search.min_score),
            peak_multiplier=float(gap_search.peak_multiplier),
            band_multiplier=float(gap_search.band_multiplier),
            wide_min_mean=float(gap_search.wide_min_mean),
            wide_min_prominence=float(gap_search.wide_min_prominence),
        ),
        enhanced=EnhancedSeparatorPolicy(
            max_width_ratio=float(enhanced.max_width_ratio),
            max_width_min=float(enhanced.max_width_min),
            max_width_max=float(enhanced.max_width_max),
            max_shift_ratio=float(enhanced.max_shift_ratio),
            max_shift_min=float(enhanced.max_shift_min),
            max_shift_max=float(enhanced.max_shift_max),
            auto_low_score=float(enhanced.auto_low_score),
        ),
        profile=SeparatorProfilePolicy(
            top_ratio=float(profile.top_ratio),
            bottom_ratio=float(profile.bottom_ratio),
            segments=int(profile.segments),
            dark_threshold=int(profile.dark_threshold),
            light_threshold=int(profile.light_threshold),
            consistency_percentile=float(profile.consistency_percentile),
            average_weight=float(profile.average_weight),
            consistency_weight=float(profile.consistency_weight),
            std_norm=float(profile.std_norm),
            dark_soft_mean=float(profile.dark_soft_mean),
            light_soft_mean=float(profile.light_soft_mean),
            light_soft_span=float(profile.light_soft_span),
            soft_weight=float(profile.soft_weight),
            uniform_base=float(profile.uniform_base),
            uniform_weight=float(profile.uniform_weight),
            gradient_weight=float(profile.gradient_weight),
            smooth_ratio=float(profile.smooth_ratio),
            smooth_min=int(profile.smooth_min),
        ),
        edge_refine_profile=EdgeRefineProfilePolicy(
            top_ratio=float(edge_refine.top_ratio),
            bottom_ratio=float(edge_refine.bottom_ratio),
            mean_weight=float(edge_refine.mean_weight),
            p75_weight=float(edge_refine.p75_weight),
            smooth_ratio=float(edge_refine.smooth_ratio),
            smooth_min=int(edge_refine.smooth_min),
            high_percentile=float(edge_refine.high_percentile),
            background_dark_threshold=int(edge_refine.background_dark_threshold),
            background_light_threshold=int(edge_refine.background_light_threshold),
            y_edge_weight=float(edge_refine.y_edge_weight),
            activity_percentile=float(edge_refine.activity_percentile),
        ),
    )


def dark_band_outer_policy(mode_preset: ModePolicyPreset) -> DarkBandOuterPolicy:
    dark_band = mode_preset.dark_band
    return DarkBandOuterPolicy(
        mode=dark_band.mode,
        required_count=3,
        full_selection_enabled=dark_band.full_selection_enabled,
    )


def outer_policy(
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> OuterPolicy:
    is_full = strip_mode == FULL
    outer = params.outer_strategy
    format_geometry = params.format_geometry_retry
    grid_refine = params.grid_outer_refine
    short_axis = params.short_axis_aspect_retry
    content_alignment = params.outer_content_alignment
    content_floating = params.content_floating_outer
    edge_anchor = params.edge_anchor_outer
    base_candidates = params.base_outer_candidates
    separator_outer = params.separator_outer_band
    separator_geometry = params.separator_geometry_outer
    content_floating_enabled = bool(
        outer.content_floating_full if is_full else outer.content_floating_partial
    )
    dark_band = mode_preset.dark_band
    edge_anchor_mode = (
        outer.edge_anchor_full_mode
        if is_full and outer.edge_anchor_full_enabled
        else outer.edge_anchor_partial_mode
        if (not is_full and outer.edge_anchor_partial_enabled)
        else "off"
    )
    return OuterPolicy(
        content_floating=content_floating_enabled,
        edge_anchor=edge_anchor_mode,
        separator_first=(
            outer.separator_first_full_mode
            if is_full and outer.separator_first_full_enabled
            else outer.separator_first_partial_mode
            if (not is_full and outer.separator_first_partial_enabled)
            else "off"
        ),
        separator_geometry=(
            outer.separator_geometry_full_mode
            if is_full
            else outer.separator_geometry_partial_mode
        ),
        separator_outer_allow_oversized_band=dark_band.separator_outer_allow_oversized_band,
        separator_outer_oversized_band_max_ratio=dark_band.separator_outer_oversized_band_max_ratio,
        separator_outer_oversized_band_score_penalty=dark_band.separator_outer_oversized_band_score_penalty,
        separator_gap_search_max_width_ratio=float(outer.separator_gap_search_max_width_ratio),
        dark_band=dark_band.mode,
        dark_band_outer=dark_band_outer_policy(mode_preset),
        format_geometry_retry=FormatGeometryRetryPolicy(
            enabled=bool(format_geometry.enabled),
            ratio_tolerance=float(format_geometry.ratio_tolerance),
            min_shrink_ratio=float(format_geometry.min_shrink_ratio),
            max_shrink_ratio=float(format_geometry.max_shrink_ratio),
            content_margin_ratio=float(format_geometry.content_margin_ratio),
            content_margin_min=int(format_geometry.content_margin_min),
            content_margin_max=int(format_geometry.content_margin_max),
        ),
        grid_refine=GridOuterRefinePolicy(
            shift_ratio=float(grid_refine.shift_ratio),
            shift_min=int(grid_refine.shift_min),
            shift_max=int(grid_refine.shift_max),
            max_width_change=float(grid_refine.max_width_change),
        ),
        short_axis_aspect_retry=ShortAxisAspectRetryPolicy(
            enabled=bool(short_axis.enabled and is_full),
            min_error=float(short_axis.min_error),
            target_aspect=float(short_axis.target_aspect),
            margin_ratio=float(short_axis.margin_ratio),
            margin_min=int(short_axis.margin_min),
            margin_max=int(short_axis.margin_max),
        ),
        content_alignment=OuterContentAlignmentPolicy(
            white_edge_long_ratio=float(content_alignment.white_edge_long_ratio),
            white_edge_long_min=int(content_alignment.white_edge_long_min),
            white_edge_long_max=int(content_alignment.white_edge_long_max),
            long_gate_ratio=float(content_alignment.long_gate_ratio),
            long_gate_min=int(content_alignment.long_gate_min),
            long_gate_max=int(content_alignment.long_gate_max),
            short_gate_ratio=float(content_alignment.short_gate_ratio),
            short_gate_min=int(content_alignment.short_gate_min),
            short_gate_max=int(content_alignment.short_gate_max),
            long_excess_ratio=float(content_alignment.long_excess_ratio),
            long_gate_excess_ratio=float(content_alignment.long_gate_excess_ratio),
            short_excess_ratio=float(content_alignment.short_excess_ratio),
            short_requires_hard_anchors=bool(content_alignment.short_requires_hard_anchors),
            short_content_height_max=float(content_alignment.short_content_height_max),
            content_width_min=float(content_alignment.content_width_min),
            edge_short_ratio=float(content_alignment.edge_short_ratio),
            edge_dark_max=float(content_alignment.edge_dark_max),
            border_band_ratio=float(content_alignment.border_band_ratio),
            margin_x_ratio=float(content_alignment.margin_x_ratio),
            margin_x_min=int(content_alignment.margin_x_min),
            margin_x_max=int(content_alignment.margin_x_max),
            margin_y_ratio=float(content_alignment.margin_y_ratio),
            margin_y_min=int(content_alignment.margin_y_min),
            margin_y_max=int(content_alignment.margin_y_max),
            long_margin_ratio=float(content_alignment.long_margin_ratio),
            long_margin_cap_ratio=float(content_alignment.long_margin_cap_ratio),
            long_margin_cap_min=int(content_alignment.long_margin_cap_min),
            long_margin_cap_max=int(content_alignment.long_margin_cap_max),
            short_margin_ratio=float(content_alignment.short_margin_ratio),
            short_margin_cap_ratio=float(content_alignment.short_margin_cap_ratio),
            short_margin_cap_min=int(content_alignment.short_margin_cap_min),
            short_margin_cap_max=int(content_alignment.short_margin_cap_max),
        ),
        content_floating_outer=ContentFloatingOuterPolicy(
            enabled=content_floating_enabled,
            ratio_extras=tuple(float(value) for value in content_floating.ratio_extras),
            content_threshold=int(content_floating.content_threshold),
            content_margin_ratio=float(content_floating.content_margin_ratio),
            content_margin_min=int(content_floating.content_margin_min),
            content_margin_max=int(content_floating.content_margin_max),
            min_width_ratio=float(content_floating.min_width_ratio),
            max_candidates=int(content_floating.max_candidates),
        ),
        edge_anchor_outer=EdgeAnchorOuterPolicy(
            mode=edge_anchor_mode,
            partial_center_ratio=float(edge_anchor.partial_center_ratio),
            ratio_extras=tuple(float(value) for value in edge_anchor.ratio_extras),
            content_threshold=int(edge_anchor.content_threshold),
            content_margin_ratio=float(edge_anchor.content_margin_ratio),
            content_margin_min=int(edge_anchor.content_margin_min),
            content_margin_max=int(edge_anchor.content_margin_max),
            min_width_ratio=float(edge_anchor.min_width_ratio),
            max_candidates=int(edge_anchor.max_candidates),
        ),
        base_candidates=OuterCandidateDetectionPolicy(
            white_x_width_multiplier=float(base_candidates.white_x_width_multiplier),
            white_x_extra_ratio=float(base_candidates.white_x_extra_ratio),
            candidate_max_area=float(base_candidates.candidate_max_area),
            mask_expand_ratio=float(base_candidates.mask_expand_ratio),
            mask_profiles=tuple(
                OuterMaskProfilePolicy(
                    name=profile.name,
                    low=profile.low,
                    high=profile.high,
                    min_row_fraction=float(profile.min_row_fraction),
                    min_col_fraction=float(profile.min_col_fraction),
                )
                for profile in base_candidates.mask_profiles
            ),
            min_width_ratio=float(base_candidates.min_width_ratio),
            min_height_ratio=float(base_candidates.min_height_ratio),
            min_width_px=int(base_candidates.min_width_px),
            min_height_px=int(base_candidates.min_height_px),
            bw_not_white_threshold=int(base_candidates.bw_not_white_threshold),
            bw_dark_threshold=int(base_candidates.bw_dark_threshold),
            bw_min_fraction=float(base_candidates.bw_min_fraction),
            bw_min_width_ratio=float(base_candidates.bw_min_width_ratio),
            bw_min_height_ratio=float(base_candidates.bw_min_height_ratio),
            bw_margin_ratio=float(base_candidates.bw_margin_ratio),
            bw_margin_min=int(base_candidates.bw_margin_min),
            white_border_ratio=float(base_candidates.white_border_ratio),
            white_run_ratio=float(base_candidates.white_run_ratio),
            white_run_min=int(base_candidates.white_run_min),
            white_run_max=int(base_candidates.white_run_max),
            white_dark_threshold=int(base_candidates.white_dark_threshold),
            white_light_threshold=int(base_candidates.white_light_threshold),
            white_min_width_ratio=float(base_candidates.white_min_width_ratio),
            white_min_height_ratio=float(base_candidates.white_min_height_ratio),
            white_margin_ratio=float(base_candidates.white_margin_ratio),
            white_margin_min=int(base_candidates.white_margin_min),
        ),
        separator_outer_band=SeparatorOuterBandPolicy(
            min_score=float(separator_outer.min_score),
            band_score=float(separator_outer.band_score),
            min_width_ratio=float(separator_outer.min_width_ratio),
            max_width_ratio=float(separator_outer.max_width_ratio),
            spacing_min_ratio=float(separator_outer.spacing_min_ratio),
            spacing_max_ratio=float(separator_outer.spacing_max_ratio),
            frame_error_max=float(separator_outer.frame_error_max),
            edge_margin_ratio=float(separator_outer.edge_margin_ratio),
            source_candidate_count=int(separator_outer.source_candidate_count),
            band_candidate_count=int(separator_outer.band_candidate_count),
            pair_candidate_count=int(separator_outer.pair_candidate_count),
            max_candidates=int(separator_outer.max_candidates),
        ),
        separator_geometry_outer=SeparatorGeometryOuterPolicy(
            required_count=int(separator_geometry.required_count),
            source_candidate_count=int(separator_geometry.source_candidate_count),
            margin_ratios=tuple(float(value) for value in separator_geometry.margin_ratios),
            max_candidates=int(separator_geometry.max_candidates),
        ),
        retries=tuple(
            name
            for name, enabled in (
                ("content_aligned_retry", outer.content_aligned_retry),
                ("format_geometry_retry", outer.format_geometry_retry),
                ("short_axis_retry", outer.short_axis_retry and is_full),
            )
            if enabled
        ),
    )


def gate_policy() -> GatePolicy:
    return GatePolicy(
        ordered_gates=(
            "confidence_floor_gate",
            "separator_gate",
            "content_gate",
            "geometry_gate",
            "mode_specific_gate",
            "hard_review_reason_gate",
            "auto_pass_gate",
            "postprocess_gate",
        ),
    )


def content_policy(params: FormatParameters) -> ContentPolicy:
    evidence = params.content_evidence
    profile = params.content_profile
    mask = params.content_mask
    candidate = params.content_candidate
    support = params.content_support
    return ContentPolicy(
        can_auto_pass_alone=False,
        evidence=ContentEvidencePolicy(
            percentile=float(evidence.percentile),
            threshold_multiplier=float(evidence.threshold_multiplier),
            threshold_min=float(evidence.threshold_min),
            threshold_max=float(evidence.threshold_max),
            aspect_ok_max=float(evidence.aspect_ok_max),
            present_mean_min=float(evidence.present_mean_min),
            present_coverage_min=float(evidence.present_coverage_min),
        ),
        profile=ContentProfilePolicy(
            smooth_ratio=float(profile.smooth_ratio),
            min_run_ratio=float(profile.min_run_ratio),
            threshold_min=float(profile.threshold_min),
            threshold_max=float(profile.threshold_max),
            p35_weight=float(profile.p35_weight),
            p65_multiplier=float(profile.p65_multiplier),
        ),
        mask=ContentMaskPolicy(
            p55_weight=float(mask.p55_weight),
            p75_multiplier=float(mask.p75_multiplier),
            threshold_min=float(mask.threshold_min),
            threshold_max=float(mask.threshold_max),
            percentiles=tuple(float(value) for value in mask.percentiles),
            bbox_min_fraction=float(mask.bbox_min_fraction),
            outer_min_width_ratio=float(mask.outer_min_width_ratio),
            outer_min_height_ratio=float(mask.outer_min_height_ratio),
            outer_min_width_px=int(mask.outer_min_width_px),
            outer_min_height_px=int(mask.outer_min_height_px),
            outer_expand_ratio=float(mask.outer_expand_ratio),
        ),
        candidate=ContentCandidatePolicy(
            expected_width_min_px=float(candidate.expected_width_min_px),
            coverage_weight=float(candidate.coverage_weight),
            mean_weight=float(candidate.mean_weight),
            run_weight=float(candidate.run_weight),
            aspect_weight=float(candidate.aspect_weight),
            coverage_norm=float(candidate.coverage_norm),
            mean_norm=float(candidate.mean_norm),
            aspect_norm=float(candidate.aspect_norm),
            weak_coverage=float(candidate.weak_coverage),
            aspect_uncertain=float(candidate.aspect_uncertain),
            grid_fallback_cap=float(candidate.grid_fallback_cap),
            run_mismatch_cap=float(candidate.run_mismatch_cap),
            runs_incomplete_cap=float(candidate.runs_incomplete_cap),
            weak_coverage_cap=float(candidate.weak_coverage_cap),
            aspect_uncertain_cap=float(candidate.aspect_uncertain_cap),
        ),
        support_coverage_norm=float(support.coverage_norm),
        support_mean_norm=float(support.mean_norm),
        support_aspect_norm=float(support.aspect_norm),
        support_coverage_weight=float(support.coverage_weight),
        support_mean_weight=float(support.mean_weight),
        support_aspect_weight=float(support.aspect_weight),
        support_gate_ok=float(support.gate_ok),
        support_gate_weak=float(support.gate_weak),
        support_gate_low_content=float(support.gate_low_content),
        support_gate_aspect_conflict=float(support.gate_aspect_conflict),
        support_gate_unknown=float(support.gate_unknown),
    )


def partial_holder_policy(strip_mode: str, params: FormatParameters) -> PartialHolderPolicy:
    holder = params.partial_holder
    content_evidence = params.content_evidence
    partial_safe = strip_mode == PARTIAL and bool(holder.enabled)
    return PartialHolderPolicy(
        safe_extra_frames=partial_safe,
        requires_wide_like_gaps=(int(holder.min_wide_like_gaps) if partial_safe else 0),
        checks_leading_content=bool(
            partial_safe and holder.leading_content_check
        ),
        checks_frame_content=bool(
            partial_safe and holder.frame_content_check
        ),
        min_count_35mm=int(holder.min_count_35mm),
        min_count_small=int(holder.min_count_small),
        min_hard_gaps=int(holder.min_hard_gaps),
        min_hard_ratio=float(holder.min_hard_ratio),
        max_equal_gaps=int(holder.max_equal_gaps),
        max_width_cv=float(holder.max_width_cv),
        min_joint_score=float(holder.min_joint_score),
        min_content_score=float(holder.min_content_score),
        min_geometry_score=float(holder.min_geometry_score),
        wide_like_min_width_ratio=float(holder.wide_like_min_width_ratio),
        leading_content_max_mean=float(holder.leading_content_max_mean),
        leading_content_max_coverage=float(holder.leading_content_max_coverage),
        leading_content_band_ratio=float(holder.leading_content_band_ratio),
        min_frame_mean=float(holder.min_frame_mean),
        min_frame_coverage=float(holder.min_frame_coverage),
        max_frame_aspect_error=float(content_evidence.aspect_ok_max),
    )


def scoring_policy(params: FormatParameters) -> ScoringPolicy:
    calibration = params.scoring_calibration
    competition = params.candidate_competition
    base_score = params.base_detection_score
    geometry_support = params.geometry_support_score
    separator_support = params.separator_support_score
    return ScoringPolicy(
        hard_full_confidence_floor=float(calibration.hard_full_confidence_floor),
        geometry_weight=float(calibration.geometry_weight),
        content_weight=float(calibration.content_weight),
        separator_weight=float(calibration.separator_weight),
        separator_source_bias=float(calibration.separator_source_bias),
        no_auto_cap_full=float(calibration.no_auto_cap_full),
        no_auto_cap_partial=float(calibration.no_auto_cap_partial),
        competition_top_n=int(competition.top_n),
        competition_close_margin=float(competition.close_margin),
        base_detection=BaseDetectionScorePolicy(
            width_cv_norm=float(base_score.width_cv_norm),
            gap_weight=float(base_score.gap_weight),
            width_weight=float(base_score.width_weight),
            outer_weight=float(base_score.outer_weight),
            contrast_weight=float(base_score.contrast_weight),
            outer_min_area=float(base_score.outer_min_area),
            outer_max_area=float(base_score.outer_max_area),
            outer_too_large=float(base_score.outer_too_large),
            outer_uncertain_confidence=float(base_score.outer_uncertain_confidence),
            contrast_min=float(base_score.contrast_min),
            contrast_floor=float(base_score.contrast_floor),
            full_width_cv=float(base_score.full_width_cv),
            geometry_floor_tight_cv=float(base_score.geometry_floor_tight_cv),
            geometry_floor_high=float(base_score.geometry_floor_high),
            geometry_floor_low=float(base_score.geometry_floor_low),
            unstable_width_cv=float(base_score.unstable_width_cv),
            full_outer_min_area=float(base_score.full_outer_min_area),
            low_confidence_floor=float(base_score.low_confidence_floor),
            partial_one_cap=float(base_score.partial_one_cap),
            partial_two_35mm_cap=float(base_score.partial_two_35mm_cap),
            partial_general_cap=float(base_score.partial_general_cap),
            outer_too_large_cap=float(base_score.outer_too_large_cap),
        ),
        geometry_support=GeometrySupportScorePolicy(
            width_cv_norm=float(geometry_support.width_cv_norm),
            outer_min_area=float(geometry_support.outer_min_area),
            outer_max_area=float(geometry_support.outer_max_area),
            outer_uncertain_score=float(geometry_support.outer_uncertain_score),
            aspect_norm=float(geometry_support.aspect_norm),
            no_aspect_score=float(geometry_support.no_aspect_score),
            width_weight=float(geometry_support.width_weight),
            outer_weight=float(geometry_support.outer_weight),
            aspect_weight=float(geometry_support.aspect_weight),
            count_weight=float(geometry_support.count_weight),
        ),
        separator_support=SeparatorSupportScorePolicy(
            model_grid_credit=float(separator_support.model_grid_credit),
            model_equal_credit=float(separator_support.model_equal_credit),
            hard_weight=float(separator_support.hard_weight),
            model_weight=float(separator_support.model_weight),
            no_expected_confidence_threshold=float(separator_support.no_expected_confidence_threshold),
            no_expected_confidence_cap=float(separator_support.no_expected_confidence_cap),
        ),
    )


def selection_policy(
    preset: FormatPolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> SelectionPolicy:
    competition = params.candidate_competition
    return SelectionPolicy(
        top_n=int(competition.top_n),
        close_margin=float(competition.close_margin),
        confidence_cap=float(competition.confidence_cap),
        content_mismatch_review=ContentMismatchReviewSelectionPolicy(
            enabled=bool(preset.content_mismatch_review_enabled and strip_mode == FULL),
        ),
    )


def candidate_run_policy() -> CandidateRunPolicy:
    return CandidateRunPolicy(
        fallback=FallbackPolicy(),
        partial_stop=PartialStopPolicy(),
    )


def report_policy() -> ReportPolicy:
    return ReportPolicy()


def partial_edge_hint_policy(params: FormatParameters) -> PartialEdgeHintPolicy:
    hint = params.partial_edge_hint
    return PartialEdgeHintPolicy(
        window_ratio=float(hint.window_ratio),
        window_min=int(hint.window_min),
        window_max=int(hint.window_max),
    )


def postprocess_policy(params: FormatParameters) -> PostprocessPolicy:
    postprocess = params.postprocess
    approved_adjustment = params.approved_geometry_adjustment
    return PostprocessPolicy(
        align_outer_to_content=True,
        retry_uncertain_outer=bool(postprocess.retry_uncertain_outer),
        apply_output_bleed=True,
        apply_approved_geometry_adjustment=True,
        approved_geometry_adjustment=ApprovedGeometryAdjustmentPolicy(
            long_limit_ratio=float(approved_adjustment.long_limit_ratio),
            long_limit_min=int(approved_adjustment.long_limit_min),
            long_limit_max=int(approved_adjustment.long_limit_max),
            min_ext_ratio=float(approved_adjustment.min_ext_ratio),
            min_ext_min=int(approved_adjustment.min_ext_min),
            min_ext_max=int(approved_adjustment.min_ext_max),
        ),
        content_aspect_conflict_cap=float(postprocess.content_aspect_conflict_cap),
        content_low_confidence_cap=float(postprocess.content_low_confidence_cap),
        outer_mismatch_cap=float(postprocess.outer_mismatch_cap),
        lucky_pass_risk_cap=float(postprocess.lucky_pass_risk_cap),
    )


def diagnostics_policy(mode_preset: ModePolicyPreset, params: FormatParameters) -> RuntimeDiagnosticsPolicy:
    debug_gap = params.debug_gap_overlay
    nearby = params.nearby_separator_diagnostics
    overlap = params.diagnostic_overlap_risk
    lucky = params.lucky_pass_risk
    return RuntimeDiagnosticsPolicy(
        overlap_bleed_risk=OverlapBleedRiskPolicy(
            enabled=mode_preset.diagnostics_overlap_bleed,
            mean_min=float(overlap.mean_min),
            weak_continuity=float(overlap.weak_continuity),
            weak_activity=float(overlap.weak_activity),
            medium_continuity=float(overlap.medium_continuity),
            medium_activity=float(overlap.medium_activity),
            strong_continuity=float(overlap.strong_continuity),
            strong_activity=float(overlap.strong_activity),
        ),
        debug_gap_overlay=DebugGapOverlayPolicy(
            overlap_tolerance_ratio=float(debug_gap.overlap_tolerance_ratio),
            overlap_tolerance_min=float(debug_gap.overlap_tolerance_min),
            overlap_tolerance_max=float(debug_gap.overlap_tolerance_max),
            tick_length_ratio=float(debug_gap.tick_length_ratio),
            tick_length_min=int(debug_gap.tick_length_min),
            hard_line_width=int(debug_gap.hard_line_width),
            model_line_width=int(debug_gap.model_line_width),
            diagnostic_line_width=int(debug_gap.diagnostic_line_width),
        ),
        nearby_separator=NearbySeparatorDiagnosticsPolicy(
            window_ratio=float(nearby.window_ratio),
            window_min=int(nearby.window_min),
            window_max=int(nearby.window_max),
            exclude_ratio=float(nearby.exclude_ratio),
            exclude_min=int(nearby.exclude_min),
            exclude_max=int(nearby.exclude_max),
            max_width_ratio=float(nearby.max_width_ratio),
            max_width_min=int(nearby.max_width_min),
            max_width_max=int(nearby.max_width_max),
            detail_score_add=float(nearby.detail_score_add),
            detail_score_multiplier=float(nearby.detail_score_multiplier),
        ),
        lucky_pass_risk=LuckyPassRiskPolicy(
            enabled=bool(lucky.enabled),
            model_gap_support_min=int(lucky.model_gap_support_min),
            model_gap_support_weight=float(lucky.model_gap_support_weight),
            minor_model_gap_support_weight=float(lucky.minor_model_gap_support_weight),
            limited_strong_hard_max=int(lucky.limited_strong_hard_max),
            limited_strong_hard_weight=float(lucky.limited_strong_hard_weight),
            very_limited_strong_hard_max=int(lucky.very_limited_strong_hard_max),
            very_limited_strong_hard_weight=float(lucky.very_limited_strong_hard_weight),
            suspicious_hard_weight=float(lucky.suspicious_hard_weight),
            strong_overlap_weight=float(lucky.strong_overlap_weight),
            combo_weight=float(lucky.combo_weight),
            unstable_width_cv=float(lucky.unstable_width_cv),
            unstable_width_weight=float(lucky.unstable_width_weight),
            mild_width_cv=float(lucky.mild_width_cv),
            mild_width_weight=float(lucky.mild_width_weight),
            strong_hard_credit_min=int(lucky.strong_hard_credit_min),
            strong_hard_credit=float(lucky.strong_hard_credit),
            stable_width_cv=float(lucky.stable_width_cv),
            stable_model_gap_min=int(lucky.stable_model_gap_min),
            stable_geometry_credit=float(lucky.stable_geometry_credit),
            risk_threshold=float(lucky.risk_threshold),
        ),
    )


def build_policy_from_preset(
    preset: FormatPolicyPreset,
    strip_mode: str,
) -> DetectionPolicy:
    mode_preset = preset.modes[strip_mode]
    fmt = FORMATS[preset.format_id]
    params = preset.parameters()
    return DetectionPolicy(
        policy_id=detection_policy_id_for(preset.format_id, strip_mode),
        format_id=preset.format_id,
        strip_mode=strip_mode,
        family=fmt.family,
        role=mode_preset.role,
        detector=DetectorPolicy(kind=mode_preset.detector_kind),
        source_parameters=params,
        counts=count_policy(preset.format_id, strip_mode, params),
        outer=outer_policy(mode_preset, strip_mode, params),
        separator=separator_policy(preset, mode_preset, strip_mode, params),
        content=content_policy(params),
        partial_holder=partial_holder_policy(strip_mode, params),
        partial_edge_hint=partial_edge_hint_policy(params),
        frame_fit=mode_preset.frame_fit or partial_frame_fit(preset.format_id),
        gates=gate_policy(),
        scoring=scoring_policy(params),
        candidate_selection=selection_policy(preset, strip_mode, params),
        candidate_run=candidate_run_policy(),
        postprocess=postprocess_policy(params),
        diagnostics=diagnostics_policy(mode_preset, params),
        report=report_policy(),
        notes=mode_preset.notes,
    )
