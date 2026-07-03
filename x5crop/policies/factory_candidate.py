from __future__ import annotations

from .factory_presets import FormatPolicyPreset
from .parameter_aggregate import FormatParameters
from .runtime_base import FULL, PARTIAL
from .runtime_candidate import (
    BaseDetectionScorePolicy,
    CandidatePlanPolicy,
    ContentMismatchReviewSelectionPolicy,
    SafetyCandidatePolicy,
    GeometrySupportScorePolicy,
    OuterCorrectionCandidateExtensionPolicy,
    PartialEdgeHintPolicy,
    PartialHolderPolicy,
    PartialStopPolicy,
    ScoringPolicy,
    SelectionPolicy,
    SeparatorSupportScorePolicy,
)


def partial_holder_policy(strip_mode: str, params: FormatParameters) -> PartialHolderPolicy:
    holder = params.partial_holder
    content_evidence = params.content_evidence
    partial_safe = strip_mode == PARTIAL and bool(holder.enabled)
    return PartialHolderPolicy(
        safe_extra_frames=partial_safe,
        requires_broad_separator_width_gaps=(int(holder.min_broad_separator_width_gaps) if partial_safe else 0),
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
        broad_separator_width_min_ratio=float(holder.broad_separator_width_min_ratio),
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


def candidate_plan_policy(strip_mode: str, params: FormatParameters) -> CandidatePlanPolicy:
    return CandidatePlanPolicy(
        safety_candidate=SafetyCandidatePolicy(),
        partial_stop=PartialStopPolicy(),
        outer_correction_extension=OuterCorrectionCandidateExtensionPolicy(
            enabled=bool(params.outer_correction_extension_enabled and strip_mode == FULL),
        ),
    )


def partial_edge_hint_policy(params: FormatParameters) -> PartialEdgeHintPolicy:
    hint = params.partial_edge_hint
    return PartialEdgeHintPolicy(
        window_ratio=float(hint.window_ratio),
        window_min=int(hint.window_min),
        window_max=int(hint.window_max),
    )

__all__ = [
    'partial_holder_policy',
    'scoring_policy',
    'selection_policy',
    'candidate_plan_policy',
    'partial_edge_hint_policy',
]
