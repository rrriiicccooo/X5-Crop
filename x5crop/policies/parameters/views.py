from __future__ import annotations

from ...image.deskew_parameters import DeskewParameters
from .base import (
    PartialCountParameters,
    PartialEdgeHintParameters,
)
from .content import (
    ContentCandidateParameters,
    ContentEvidenceParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)
from .diagnostics import (
    DebugGapOverlayParameters,
    DiagnosticOverlapRiskParameters,
    LuckyPassRiskParameters,
    NearbySeparatorDiagnosticsParameters,
)
from .finalization import (
    ApprovedGeometryAdjustmentParameters,
    FinalizationParameters,
    PartialHolderParameters,
)
from .outer import (
    BaseOuterCandidateParameters,
    ContentContainmentCorrectionParameters,
    EdgeAnchoredContentPositionParameters,
    FloatingContentPositionParameters,
    GridOuterRefineParameters,
    OuterStrategyParameters,
    FullWidthSeparatorOuterParameters,
    LongAxisGeometryCorrectionParameters,
    SeparatorOuterBandParameters,
    ShortAxisGeometryCorrectionParameters,
)
from .scoring import (
    BaseDetectionScoreParameters,
    CandidateCompetitionParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from .separator import (
    EdgeRefineProfileParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    LeadingGridFailureParameters,
    NearbySeparatorRefinementParameters,
    RobustGridParameters,
    SeparatorGateParameters,
    SeparatorGeometrySupportParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileParameters,
)


class FormatParameterViews:
    @property
    def partial_counts(self) -> PartialCountParameters:
        return PartialCountParameters(
            offsets=self.partial_offsets,
            include_default_auto=self.partial_auto_include_default_count,
        )

    @property
    def partial_edge_hint(self) -> PartialEdgeHintParameters:
        return PartialEdgeHintParameters(
            window_ratio=self.partial_edge_hint_window_ratio,
            window_min=self.partial_edge_hint_window_min,
            window_max=self.partial_edge_hint_window_max,
        )

    @property
    def separator_gate(self) -> SeparatorGateParameters:
        return SeparatorGateParameters(
            needed_hard_max=self.separator_gate_needed_hard_max,
            max_equal_gaps_floor=self.separator_gate_max_equal_gaps_floor,
            allow_geometry_support=self.separator_allow_geometry_support,
            hard_required_all_gaps=self.separator_hard_required_all_gaps,
            edge_pair_min_score_without_broad_width=self.separator_gate_edge_pair_min_score_without_broad_width,
            edge_pair_min_score_with_broad_width=self.separator_gate_edge_pair_min_score_with_broad_width,
            min_broad_separator_width_gaps_for_auto=self.separator_gate_min_broad_separator_width_gaps_for_auto,
            score_min_hard_gaps=self.score_gate_min_hard_gaps,
            score_max_equal_gaps_floor=self.score_gate_max_equal_gaps_floor,
            low_hard_confidence_cap=self.score_gate_low_hard_confidence_cap,
            mostly_equal_confidence_cap=self.score_gate_mostly_equal_confidence_cap,
            allow_full_detected_geometry=self.score_gate_allow_full_detected_geometry,
        )

    @property
    def leading_grid_failure(self) -> LeadingGridFailureParameters:
        return LeadingGridFailureParameters(
            enabled=self.leading_grid_failure_enabled,
            min_expected_gaps=self.leading_grid_failure_min_count,
            leading_count=self.leading_grid_failure_leading_count,
            low_score=self.leading_grid_failure_low_score,
            very_low_score=self.leading_grid_failure_very_low_score,
            very_low_count=self.leading_grid_failure_very_low_count,
            max_hard_gaps=self.leading_grid_failure_max_hard,
        )

    @property
    def separator_geometry_support(self) -> SeparatorGeometrySupportParameters:
        return SeparatorGeometrySupportParameters(
            detected_geometry_min_hard_ratio=self.separator_detected_geometry_min_hard_ratio,
            detected_geometry_min_joint_score=self.separator_detected_geometry_min_joint_score,
            stable_grid_min_hard_ratio=self.separator_stable_grid_min_hard_ratio,
            stable_grid_min_joint_score=self.separator_stable_grid_min_joint_score,
            max_photo_width_cv=self.score_full_photo_width_cv,
            max_outer_area_ratio=self.score_outer_max_area,
        )

    @property
    def separator_width_profile(self) -> SeparatorWidthProfileParameters:
        return SeparatorWidthProfileParameters(
            full_enabled=self.separator_width_profile_enabled,
            partial_enabled=self.separator_width_profile_partial_enabled,
            max_width_ratio=self.separator_width_profile_max_width_ratio,
            confidence_cap=self.separator_width_profile_confidence_cap,
        )

    @property
    def content_evidence(self) -> ContentEvidenceParameters:
        return ContentEvidenceParameters(
            percentile=self.content_evidence_percentile,
            threshold_multiplier=self.content_evidence_threshold_multiplier,
            threshold_min=self.content_evidence_threshold_min,
            threshold_max=self.content_evidence_threshold_max,
            aspect_ok_max=self.content_evidence_aspect_ok_max,
            present_mean_min=self.content_evidence_present_mean_min,
            present_coverage_min=self.content_evidence_present_coverage_min,
        )

    @property
    def content_profile(self) -> ContentProfileParameters:
        return ContentProfileParameters(
            smooth_ratio=self.content_profile_smooth_ratio,
            min_run_ratio=self.content_profile_min_run_ratio,
            threshold_min=self.content_profile_threshold_min,
            threshold_max=self.content_profile_threshold_max,
            p35_weight=self.content_profile_p35_weight,
            p65_multiplier=self.content_profile_p65_multiplier,
        )

    @property
    def content_mask(self) -> ContentMaskParameters:
        return ContentMaskParameters(
            p55_weight=self.content_mask_p55_weight,
            p75_multiplier=self.content_mask_p75_multiplier,
            threshold_min=self.content_mask_min,
            threshold_max=self.content_mask_max,
            percentiles=self.content_mask_percentiles,
            bbox_min_fraction=self.content_bbox_min_fraction,
            outer_min_width_ratio=self.content_outer_min_width_ratio,
            outer_min_height_ratio=self.content_outer_min_height_ratio,
            outer_min_width_px=self.content_outer_min_width_px,
            outer_min_height_px=self.content_outer_min_height_px,
            outer_expand_ratio=self.outer_mask_expand_ratio,
        )

    @property
    def content_candidate(self) -> ContentCandidateParameters:
        return ContentCandidateParameters(
            expected_width_min_px=self.content_expected_width_min_px,
            coverage_weight=self.content_candidate_coverage_weight,
            mean_weight=self.content_candidate_mean_weight,
            run_weight=self.content_candidate_plan_weight,
            aspect_weight=self.content_candidate_aspect_weight,
            coverage_norm=self.content_conf_coverage_norm,
            mean_norm=self.content_conf_mean_norm,
            aspect_norm=self.content_conf_aspect_norm,
            weak_coverage=self.content_weak_coverage,
            aspect_uncertain=self.content_aspect_uncertain,
            grid_fallback_cap=self.content_grid_fallback_cap,
            run_mismatch_cap=self.content_run_mismatch_cap,
            runs_incomplete_cap=self.content_runs_incomplete_cap,
            weak_coverage_cap=self.content_weak_coverage_cap,
            aspect_uncertain_cap=self.content_aspect_uncertain_cap,
        )

    @property
    def content_support(self) -> ContentSupportParameters:
        return ContentSupportParameters(
            coverage_norm=self.content_conf_coverage_norm,
            mean_norm=self.content_conf_mean_norm,
            aspect_norm=self.content_support_aspect_norm,
            coverage_weight=self.content_support_coverage_weight,
            mean_weight=self.content_support_mean_weight,
            aspect_weight=self.content_support_aspect_weight,
            gate_ok=self.content_support_gate_ok,
            gate_weak=self.content_support_gate_weak,
            gate_low_content=self.content_support_gate_low_content,
            gate_aspect_conflict=self.content_support_gate_aspect_conflict,
            gate_unknown=self.content_support_gate_unknown,
        )

    @property
    def outer_strategy(self) -> OuterStrategyParameters:
        return OuterStrategyParameters(
            separator_gap_search_max_width_ratio=self.separator_outer_gap_max_width_ratio,
        )

    @property
    def floating_content_position(self) -> FloatingContentPositionParameters:
        return FloatingContentPositionParameters(
            ratio_extras=self.partial_floating_ratio_extras,
            content_threshold=self.partial_floating_content_threshold,
            content_margin_ratio=self.partial_floating_content_margin_ratio,
            content_margin_min=self.partial_floating_content_margin_min,
            content_margin_max=self.partial_floating_content_margin_max,
            min_width_ratio=self.partial_floating_min_width_ratio,
            max_candidates=self.partial_floating_max_candidates,
        )

    @property
    def edge_anchored_content_position(self) -> EdgeAnchoredContentPositionParameters:
        return EdgeAnchoredContentPositionParameters(
            partial_center_ratio=self.partial_edge_center_ratio,
            ratio_extras=self.partial_edge_ratio_extras,
            content_threshold=self.partial_edge_content_threshold,
            content_margin_ratio=self.partial_edge_content_margin_ratio,
            content_margin_min=self.partial_edge_content_margin_min,
            content_margin_max=self.partial_edge_content_margin_max,
            min_width_ratio=self.partial_edge_min_width_ratio,
            max_candidates=self.partial_edge_max_candidates,
        )

    @property
    def base_outer_candidates(self) -> BaseOuterCandidateParameters:
        return BaseOuterCandidateParameters(
            white_x_width_multiplier=self.outer_white_x_width_multiplier,
            white_x_extra_ratio=self.outer_white_x_extra_ratio,
            candidate_max_area=self.outer_candidate_max_area,
            mask_expand_ratio=self.outer_mask_expand_ratio,
            mask_profiles=self.outer_mask_profiles,
            min_width_ratio=self.outer_min_width_ratio,
            min_height_ratio=self.outer_min_height_ratio,
            min_width_px=self.outer_min_width_px,
            min_height_px=self.outer_min_height_px,
            bw_not_white_threshold=self.outer_bw_not_white_threshold,
            bw_dark_threshold=self.outer_bw_dark_threshold,
            bw_min_fraction=self.outer_bw_min_fraction,
            bw_min_width_ratio=self.outer_bw_min_width_ratio,
            bw_min_height_ratio=self.outer_bw_min_height_ratio,
            bw_margin_ratio=self.outer_bw_margin_ratio,
            bw_margin_min=self.outer_bw_margin_min,
            white_border_ratio=self.outer_white_border_ratio,
            white_run_ratio=self.outer_white_run_ratio,
            white_run_min=self.outer_white_run_min,
            white_run_max=self.outer_white_run_max,
            white_dark_threshold=self.outer_white_dark_threshold,
            white_light_threshold=self.outer_white_light_threshold,
            white_min_width_ratio=self.outer_white_min_width_ratio,
            white_min_height_ratio=self.outer_white_min_height_ratio,
            white_margin_ratio=self.outer_white_margin_ratio,
            white_margin_min=self.outer_white_margin_min,
        )

    @property
    def separator_outer_band(self) -> SeparatorOuterBandParameters:
        return SeparatorOuterBandParameters(
            min_score=self.separator_outer_min_score,
            band_score=self.separator_outer_band_score,
            min_width_ratio=self.separator_outer_min_width_ratio,
            max_width_ratio=self.separator_outer_max_width_ratio,
            spacing_min_ratio=self.separator_outer_spacing_min_ratio,
            spacing_max_ratio=self.separator_outer_spacing_max_ratio,
            frame_error_max=self.separator_outer_frame_error_max,
            edge_margin_ratio=self.separator_outer_edge_margin_ratio,
            source_candidate_count=self.separator_outer_source_candidates,
            band_candidate_count=self.separator_outer_band_candidates,
            pair_candidate_count=self.separator_outer_pair_candidates,
            max_candidates=self.separator_outer_max_candidates,
        )

    @property
    def separator_full_width_outer(self) -> FullWidthSeparatorOuterParameters:
        return FullWidthSeparatorOuterParameters(
            required_count=self.separator_full_width_outer_count,
            source_candidate_count=self.separator_full_width_outer_source_candidates,
            margin_ratios=self.separator_full_width_outer_margin_ratios,
            max_candidates=self.separator_full_width_outer_max_candidates,
        )

    @property
    def short_axis_geometry_correction(self) -> ShortAxisGeometryCorrectionParameters:
        return ShortAxisGeometryCorrectionParameters(
            min_error=self.short_axis_geometry_correction_min_error,
            target_aspect=self.short_axis_geometry_correction_target_aspect,
            margin_ratio=self.short_axis_geometry_correction_margin_ratio,
            margin_min=self.short_axis_geometry_correction_margin_min,
            margin_max=self.short_axis_geometry_correction_margin_max,
        )

    @property
    def long_axis_geometry_correction(self) -> LongAxisGeometryCorrectionParameters:
        return LongAxisGeometryCorrectionParameters(
            ratio_tolerance=self.long_axis_geometry_correction_ratio_tolerance,
            min_shrink_ratio=self.long_axis_geometry_correction_min_shrink_ratio,
            max_shrink_ratio=self.long_axis_geometry_correction_max_shrink_ratio,
            content_margin_ratio=self.long_axis_geometry_correction_content_margin_ratio,
            content_margin_min=self.long_axis_geometry_correction_content_margin_min,
            content_margin_max=self.long_axis_geometry_correction_content_margin_max,
        )

    @property
    def grid_outer_refine(self) -> GridOuterRefineParameters:
        return GridOuterRefineParameters(
            shift_ratio=self.grid_outer_refine_shift_ratio,
            shift_min=self.grid_outer_refine_shift_min,
            shift_max=self.grid_outer_refine_shift_max,
            max_width_change=self.grid_outer_refine_max_width_change,
        )

    @property
    def deskew(self) -> DeskewParameters:
        return DeskewParameters(
            min_outer_width=self.deskew_min_outer_width,
            outer_dark_threshold=self.deskew_outer_dark_threshold,
            outer_min_fraction=self.deskew_outer_min_fraction,
            sample_width_px=self.deskew_sample_width_px,
            min_samples=self.deskew_min_samples,
            max_samples=self.deskew_max_samples,
            min_col_content=self.deskew_min_col_content,
            min_col_content_ratio=self.deskew_min_col_content_ratio,
            slope_delta_max=self.deskew_slope_delta_max,
            residual_min=self.deskew_residual_min,
            residual_height_ratio=self.deskew_residual_height_ratio,
            auto_quality_ok=self.deskew_auto_quality_ok,
            fallback_quality_gain=self.deskew_fallback_quality_gain,
            fit_min_points=self.deskew_fit_min_points,
            fit_tolerance_min=self.deskew_fit_tolerance_min,
            fit_tolerance_multiplier=self.deskew_fit_tolerance_multiplier,
            span_skip_ratio=self.deskew_span_skip_ratio,
            span_skip_min=self.deskew_span_skip_min,
            span_skip_max=self.deskew_span_skip_max,
        )

    @property
    def content_containment_correction(self) -> ContentContainmentCorrectionParameters:
        return ContentContainmentCorrectionParameters(
            white_edge_long_ratio=self.outer_align_white_edge_long_ratio,
            white_edge_long_min=self.outer_align_white_edge_long_min,
            white_edge_long_max=self.outer_align_white_edge_long_max,
            long_gate_ratio=self.outer_align_long_gate_ratio,
            long_gate_min=self.outer_align_long_gate_min,
            long_gate_max=self.outer_align_long_gate_max,
            short_gate_ratio=self.outer_align_short_gate_ratio,
            short_gate_min=self.outer_align_short_gate_min,
            short_gate_max=self.outer_align_short_gate_max,
            long_excess_ratio=self.outer_align_long_excess_ratio,
            long_gate_excess_ratio=self.outer_align_long_gate_excess_ratio,
            short_excess_ratio=self.outer_align_short_excess_ratio,
            short_requires_hard_anchors=self.outer_align_short_requires_hard_anchors,
            short_content_height_max=self.outer_align_short_content_height_max,
            content_width_min=self.outer_align_content_width_min,
            edge_short_ratio=self.outer_align_edge_short_ratio,
            edge_dark_max=self.outer_align_edge_dark_max,
            border_band_ratio=self.outer_align_border_band_ratio,
            margin_x_ratio=self.outer_align_margin_x_ratio,
            margin_x_min=self.outer_align_margin_x_min,
            margin_x_max=self.outer_align_margin_x_max,
            margin_y_ratio=self.outer_align_margin_y_ratio,
            margin_y_min=self.outer_align_margin_y_min,
            margin_y_max=self.outer_align_margin_y_max,
            long_margin_ratio=self.outer_align_long_margin_ratio,
            long_margin_cap_ratio=self.outer_align_long_margin_cap_ratio,
            long_margin_cap_min=self.outer_align_long_margin_cap_min,
            long_margin_cap_max=self.outer_align_long_margin_cap_max,
            short_margin_ratio=self.outer_align_short_margin_ratio,
            short_margin_cap_ratio=self.outer_align_short_margin_cap_ratio,
            short_margin_cap_min=self.outer_align_short_margin_cap_min,
            short_margin_cap_max=self.outer_align_short_margin_cap_max,
        )

    @property
    def partial_holder(self) -> PartialHolderParameters:
        return PartialHolderParameters(
            enabled=self.partial_safe_extra_frames_enabled,
            min_count_35mm=self.partial_safe_extra_frames_min_count_35mm,
            min_count_small=self.partial_safe_extra_frames_min_count_small,
            min_hard_gaps=self.partial_safe_extra_frames_min_hard_gaps,
            min_hard_ratio=self.partial_safe_extra_frames_min_hard_ratio,
            max_equal_gaps=self.partial_safe_extra_frames_max_equal_gaps,
            max_photo_width_cv=self.partial_safe_extra_frames_max_photo_width_cv,
            min_joint_score=self.partial_safe_extra_frames_min_joint_score,
            min_content_score=self.partial_safe_extra_frames_min_content_score,
            min_geometry_score=self.partial_safe_extra_frames_min_geometry_score,
            min_broad_separator_width_gaps=self.partial_safe_extra_frames_min_broad_separator_width_gaps,
            broad_separator_width_min_ratio=self.partial_safe_extra_frames_broad_separator_width_min_ratio,
            leading_content_check=self.partial_safe_extra_frames_leading_content_check,
            leading_content_max_mean=self.partial_safe_extra_frames_leading_content_max_mean,
            leading_content_max_coverage=self.partial_safe_extra_frames_leading_content_max_coverage,
            leading_content_band_ratio=self.partial_safe_extra_frames_leading_content_band_ratio,
            frame_content_check=self.partial_safe_extra_frames_frame_content_check,
            min_frame_mean=self.partial_safe_extra_frames_min_frame_mean,
            min_frame_coverage=self.partial_safe_extra_frames_min_frame_coverage,
        )

    @property
    def scoring_calibration(self) -> ScoringCalibrationParameters:
        return ScoringCalibrationParameters(
            hard_full_confidence_floor=self.calibrate_hard_full_confidence_floor,
            geometry_weight=self.calibrate_geometry_weight,
            content_weight=self.calibrate_content_weight,
            separator_weight=self.calibrate_separator_weight,
            separator_source_bias=self.calibrate_separator_source_bias,
            no_auto_cap_partial=self.calibrate_partial_no_auto_cap,
            no_auto_cap_full=self.calibrate_full_no_auto_cap,
        )

    @property
    def base_detection_score(self) -> BaseDetectionScoreParameters:
        return BaseDetectionScoreParameters(
            photo_width_cv_norm=self.score_photo_width_cv_norm,
            gap_weight=self.score_gap_weight,
            photo_width_weight=self.score_photo_width_weight,
            outer_min_area=self.score_outer_min_area,
            outer_max_area=self.score_outer_max_area,
            outer_too_large=self.score_outer_too_large,
            image_quality_contrast_min=self.image_quality_contrast_min,
            full_photo_width_cv=self.score_full_photo_width_cv,
            geometry_floor_tight_photo_width_cv=self.score_geometry_floor_tight_photo_width_cv,
            geometry_floor_high=self.score_geometry_floor_high,
            geometry_floor_low=self.score_geometry_floor_low,
            unstable_photo_width_cv=self.score_unstable_photo_width_cv,
            full_outer_min_area=self.score_full_outer_min_area,
            low_confidence_floor=self.score_low_confidence_floor,
            partial_one_cap=self.score_partial_one_cap,
            partial_two_35mm_cap=self.score_partial_two_35mm_cap,
            partial_general_cap=self.score_partial_general_cap,
        )

    @property
    def separator_support_score(self) -> SeparatorSupportScoreParameters:
        return SeparatorSupportScoreParameters(
            model_grid_credit=self.separator_model_grid_credit,
            model_equal_credit=self.separator_model_equal_credit,
            hard_weight=self.separator_support_hard_weight,
            model_weight=self.separator_support_model_weight,
            no_expected_confidence_threshold=self.score_low_confidence_floor,
            no_expected_confidence_cap=0.75,
        )

    @property
    def geometry_support_score(self) -> GeometrySupportScoreParameters:
        return GeometrySupportScoreParameters(
            photo_width_cv_norm=self.geometry_photo_width_cv_norm,
            outer_min_area=self.score_outer_min_area,
            outer_max_area=self.score_outer_too_large,
            outer_uncertain_score=self.geometry_support_outer_uncertain,
            aspect_norm=self.content_support_aspect_norm,
            no_aspect_score=self.geometry_support_no_aspect_score,
            photo_width_weight=self.geometry_support_photo_width_weight,
            outer_weight=self.geometry_support_outer_weight,
            aspect_weight=self.geometry_support_aspect_weight,
            count_weight=self.geometry_support_count_weight,
        )

    @property
    def separator_profile(self) -> SeparatorProfileParameters:
        return SeparatorProfileParameters(
            top_ratio=self.separator_profile_top_ratio,
            bottom_ratio=self.separator_profile_bottom_ratio,
            segments=self.separator_profile_segments,
            dark_threshold=self.separator_profile_dark_threshold,
            light_threshold=self.separator_profile_light_threshold,
            consistency_percentile=self.separator_profile_consistency_percentile,
            average_weight=self.separator_profile_average_weight,
            consistency_weight=self.separator_profile_consistency_weight,
            std_norm=self.separator_profile_std_norm,
            dark_soft_mean=self.separator_profile_dark_soft_mean,
            light_soft_mean=self.separator_profile_light_soft_mean,
            light_soft_span=self.separator_profile_light_soft_span,
            soft_weight=self.separator_profile_soft_weight,
            uniform_base=self.separator_profile_uniform_base,
            uniform_weight=self.separator_profile_uniform_weight,
            gradient_weight=self.separator_profile_gradient_weight,
            smooth_ratio=self.separator_profile_smooth_ratio,
            smooth_min=self.separator_profile_smooth_min,
        )

    @property
    def edge_refine_profile(self) -> EdgeRefineProfileParameters:
        return EdgeRefineProfileParameters(
            top_ratio=self.edge_refine_top_ratio,
            bottom_ratio=self.edge_refine_bottom_ratio,
            mean_weight=self.edge_refine_mean_weight,
            p75_weight=self.edge_refine_p75_weight,
            smooth_ratio=self.edge_refine_smooth_ratio,
            smooth_min=self.edge_refine_smooth_min,
            high_percentile=self.edge_refine_high_percentile,
            background_dark_threshold=self.edge_refine_background_dark_threshold,
            background_light_threshold=self.edge_refine_background_light_threshold,
            y_edge_weight=self.edge_refine_y_edge_weight,
            activity_percentile=self.edge_refine_activity_percentile,
        )

    @property
    def candidate_competition(self) -> CandidateCompetitionParameters:
        return CandidateCompetitionParameters(
            top_n=self.candidate_competition_top_n,
            close_margin=self.candidate_competition_close_margin,
            confidence_cap=self.candidate_competition_confidence_cap,
        )

    @property
    def finalization(self) -> FinalizationParameters:
        return FinalizationParameters(
            content_aspect_conflict_cap=self.post_content_aspect_conflict_cap,
            content_low_confidence_cap=self.post_content_low_confidence_cap,
            outer_mismatch_cap=self.post_outer_mismatch_cap,
            lucky_pass_risk_cap=self.post_lucky_pass_risk_cap,
        )

    @property
    def approved_geometry_adjustment(self) -> ApprovedGeometryAdjustmentParameters:
        return ApprovedGeometryAdjustmentParameters(
            long_limit_ratio=self.approved_adjust_long_limit_ratio,
            long_limit_min=self.approved_adjust_long_limit_min,
            long_limit_max=self.approved_adjust_long_limit_max,
            min_ext_ratio=self.approved_adjust_min_ext_ratio,
            min_ext_min=self.approved_adjust_min_ext_min,
            min_ext_max=self.approved_adjust_min_ext_max,
        )

    @property
    def debug_gap_overlay(self) -> DebugGapOverlayParameters:
        return DebugGapOverlayParameters(
            overlap_tolerance_ratio=self.debug_gap_overlap_tolerance_ratio,
            overlap_tolerance_min=self.debug_gap_overlap_tolerance_min,
            overlap_tolerance_max=self.debug_gap_overlap_tolerance_max,
            tick_length_ratio=self.debug_gap_tick_length_ratio,
            tick_length_min=self.debug_gap_tick_length_min,
            hard_line_width=self.debug_gap_hard_line_width,
            model_line_width=self.debug_gap_model_line_width,
            diagnostic_line_width=self.debug_gap_diagnostic_line_width,
        )

    @property
    def nearby_separator_diagnostics(self) -> NearbySeparatorDiagnosticsParameters:
        return NearbySeparatorDiagnosticsParameters(
            window_ratio=self.nearby_window_ratio,
            window_min=self.nearby_window_min,
            window_max=self.nearby_window_max,
            exclude_ratio=self.nearby_exclude_ratio,
            exclude_min=self.nearby_exclude_min,
            exclude_max=self.nearby_exclude_max,
            max_width_ratio=self.nearby_max_width_ratio,
            max_width_min=self.nearby_max_width_min,
            max_width_max=self.nearby_max_width_max,
            detail_score_add=self.nearby_detail_score_add,
            detail_score_multiplier=self.nearby_detail_score_multiplier,
        )

    @property
    def nearby_separator_refinement(self) -> NearbySeparatorRefinementParameters:
        return NearbySeparatorRefinementParameters(
            enabled=self.nearby_active_refinement,
            window_ratio=self.nearby_window_ratio,
            window_min=self.nearby_window_min,
            window_max=self.nearby_window_max,
            exclude_ratio=self.nearby_exclude_ratio,
            exclude_min=self.nearby_exclude_min,
            exclude_max=self.nearby_exclude_max,
            max_width_ratio=self.nearby_max_width_ratio,
            max_width_min=self.nearby_max_width_min,
            max_width_max=self.nearby_max_width_max,
            distance_ratio=self.nearby_distance_ratio,
            score_add=self.nearby_score_add,
            score_multiplier=self.nearby_score_multiplier,
            local_gain_ratio=self.nearby_local_gain_ratio,
            local_gain_min=self.nearby_local_gain_min,
            local_gain_max=self.nearby_local_gain_max,
            width_cv_slack=self.nearby_width_cv_slack,
        )

    @property
    def robust_grid(self) -> RobustGridParameters:
        return RobustGridParameters(
            constrain_full_shift_ratio=self.constrain_full_shift_ratio,
            constrain_partial_shift_ratio=self.constrain_partial_shift_ratio,
            constrain_shift_min=self.constrain_shift_min,
            constrain_shift_max=self.constrain_shift_max,
            reliable_min_score=self.robust_reliable_min_score,
            min_reliable=self.robust_min_reliable,
            pitch_min_ratio=self.robust_pitch_min_ratio,
            pitch_max_ratio=self.robust_pitch_max_ratio,
            full_tolerance_ratio=self.robust_full_tolerance_ratio,
            partial_tolerance_ratio=self.robust_partial_tolerance_ratio,
            tolerance_min=self.robust_tolerance_min,
            tolerance_max=self.robust_tolerance_max,
            reject_residual_ratio=self.robust_reject_residual_ratio,
            full_shift_ratio=self.robust_full_shift_ratio,
            partial_shift_ratio=self.robust_partial_shift_ratio,
            shift_min=self.robust_shift_min,
            shift_max=self.robust_shift_max,
            hard_keep_ratio=self.robust_hard_keep_ratio,
            hard_keep_min=self.robust_hard_keep_min,
            hard_keep_max=self.robust_hard_keep_max,
            hard_protect_ratio=self.robust_hard_protect_ratio,
            hard_protect_min=self.robust_hard_protect_min,
            hard_protect_max=self.robust_hard_protect_max,
        )

    @property
    def gap_search(self) -> GapSearchParameters:
        return GapSearchParameters(
            radius_ratio=self.gap_radius_ratio,
            radius_min=self.gap_radius_min,
            radius_max=self.gap_radius_max,
            max_width_ratio=self.gap_max_width_ratio,
            max_width_min=self.gap_max_width_min,
            max_width_max=self.gap_max_width_max,
            min_width_ratio=self.gap_min_width_ratio,
            min_width_min=self.gap_min_width_min,
            min_width_max=self.gap_min_width_max,
            guard_ratio=self.gap_guard_ratio,
            guard_min=self.gap_guard_min,
            guard_max=self.gap_guard_max,
            min_score=self.gap_min_score,
            peak_multiplier=self.gap_peak_multiplier,
            band_multiplier=self.gap_band_multiplier,
            band_min_score_multiplier=self.gap_band_min_score_multiplier,
            weak_prominence_min=self.gap_weak_prominence_min,
            weak_prominence_mean_override=self.gap_weak_prominence_mean_override,
            quality_prominence_weight=self.gap_quality_prominence_weight,
            separator_width_min_mean=self.separator_width_profile_min_mean,
            separator_width_min_prominence=self.separator_width_profile_min_prominence,
        )

    @property
    def diagnostic_overlap_risk(self) -> DiagnosticOverlapRiskParameters:
        return DiagnosticOverlapRiskParameters(
            mean_min=self.diagnostic_overlap_mean_min,
            weak_continuity=self.diagnostic_overlap_weak_continuity,
            weak_activity=self.diagnostic_overlap_weak_activity,
            medium_continuity=self.diagnostic_overlap_medium_continuity,
            medium_activity=self.diagnostic_overlap_medium_activity,
            strong_continuity=self.diagnostic_overlap_strong_continuity,
            strong_activity=self.diagnostic_overlap_strong_activity,
        )

    @property
    def hard_gap_trust(self) -> HardGapTrustParameters:
        return HardGapTrustParameters(
            guard_ratio=self.hard_trust_guard_ratio,
            guard_min=self.hard_trust_guard_min,
            guard_max=self.hard_trust_guard_max,
            narrow_ratio=self.hard_trust_narrow_ratio,
            narrow_min=self.hard_trust_narrow_min,
            narrow_max=self.hard_trust_narrow_max,
            model_delta_ratio=self.hard_trust_model_delta_ratio,
            geometry_width_ratio=self.hard_trust_geometry_width_ratio,
            strong_min_score=self.hard_trust_strong_min_score,
            strong_width_min=self.hard_trust_strong_width_min,
            strong_width_max=self.hard_trust_strong_width_max,
            narrow_ok_score=self.hard_trust_narrow_ok_score,
            narrow_ok_width_min=self.hard_trust_narrow_ok_width_min,
            narrow_ok_width_max=self.hard_trust_narrow_ok_width_max,
            model_conflict_score=self.hard_trust_model_conflict_score,
            core_content_threshold=self.hard_trust_core_content_threshold,
            core_dark_threshold=self.hard_trust_core_dark_threshold,
            dark_mean_max=self.hard_trust_dark_mean_max,
            dark_fraction_min=self.hard_trust_dark_fraction_min,
            dark_activity_max=self.hard_trust_dark_activity_max,
            strong_core_content_max=self.hard_trust_strong_core_content_max,
            weak_mean_min=self.hard_trust_weak_mean_min,
            weak_content_min=self.hard_trust_weak_content_min,
            frame_border_width_ratio=self.hard_trust_frame_border_width_ratio,
            continuity_min=self.hard_trust_continuity_min,
            activity_min=self.hard_trust_activity_min,
        )

    @property
    def lucky_pass_risk(self) -> LuckyPassRiskParameters:
        return LuckyPassRiskParameters(
            enabled=self.lucky_pass_risk_enabled,
            model_gap_support_min=self.lucky_model_gap_support_min,
            model_gap_support_weight=self.lucky_model_gap_support_weight,
            minor_model_gap_support_weight=self.lucky_minor_model_gap_support_weight,
            limited_strong_hard_max=self.lucky_limited_strong_hard_max,
            limited_strong_hard_weight=self.lucky_limited_strong_hard_weight,
            very_limited_strong_hard_max=self.lucky_very_limited_strong_hard_max,
            very_limited_strong_hard_weight=self.lucky_very_limited_strong_hard_weight,
            suspicious_hard_weight=self.lucky_suspicious_hard_weight,
            strong_overlap_weight=self.lucky_strong_overlap_weight,
            combo_weight=self.lucky_combo_weight,
            unstable_photo_width_cv=self.lucky_unstable_photo_width_cv,
            unstable_photo_width_weight=self.lucky_unstable_photo_width_weight,
            mild_photo_width_cv=self.lucky_mild_photo_width_cv,
            mild_photo_width_weight=self.lucky_mild_photo_width_weight,
            strong_hard_credit_min=self.lucky_strong_hard_credit_min,
            strong_hard_credit=self.lucky_strong_hard_credit,
            stable_photo_width_cv=self.lucky_stable_photo_width_cv,
            stable_model_gap_min=self.lucky_stable_model_gap_min,
            stable_photo_width_geometry_credit=self.lucky_stable_photo_width_geometry_credit,
            risk_threshold=self.lucky_risk_threshold,
        )


__all__ = [
    "FormatParameterViews",
]
