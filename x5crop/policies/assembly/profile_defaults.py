from __future__ import annotations

from dataclasses import replace

from ...formats import FormatPhysicalSpec
from ...geometry.detection_parameters import NearbySeparatorRefinementParameters
from ..parameters.aggregate import FormatParameters
from ..parameters.finalization import PartialHolderParameters
from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from ..parameters.separator import (
    LeadingGridFailureParameters,
    SeparatorSupportParameters,
    SeparatorGeometrySupportParameters,
)


def separator_support_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> SeparatorSupportParameters:
    support = params.separator.separator_support
    if fmt.frame_geometry_profile == "medium_square":
        return replace(
            support,
            edge_pair_min_score_without_broad_width=1.0,
            edge_pair_min_score_with_broad_width=0.0,
            min_broad_separator_width_gaps_for_auto=0,
        )
    return support


def leading_grid_failure_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> LeadingGridFailureParameters:
    return replace(
        params.separator.leading_grid_failure,
        enabled=fmt.frame_geometry_profile == "standard_35mm",
    )


def base_detection_score_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> BaseDetectionScoreParameters:
    score = params.candidate.base_detection_score
    profile = fmt.frame_geometry_profile
    if profile == "dense_half":
        score = replace(score, full_photo_width_cv=0.008)
    elif fmt.family == "120":
        score = replace(score, full_photo_width_cv=0.012)
    if profile == "medium_square":
        score = replace(
            score,
            outer_max_area=1.0,
            outer_too_large=1.0,
        )
    elif profile == "medium_wide":
        score = replace(
            score,
            outer_too_large=0.995,
        )
    return score


def scoring_calibration_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> ScoringCalibrationParameters:
    calibration = params.candidate.scoring_calibration
    if fmt.family == "120":
        calibration = replace(
            calibration,
            separator_weight=0.36,
            geometry_weight=0.32,
            content_weight=0.32,
        )
    if fmt.frame_geometry_profile in {"medium_square", "medium_wide"}:
        calibration = replace(calibration, hard_full_confidence_floor=0.86)
    return calibration


def separator_support_score_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> SeparatorSupportScoreParameters:
    support = params.candidate.separator_support_score
    if fmt.frame_geometry_profile == "dense_half":
        return replace(support, model_grid_credit=0.25, model_equal_credit=0.08)
    if fmt.frame_geometry_profile == "panoramic_35mm":
        return replace(support, model_grid_credit=0.20, model_equal_credit=0.06)
    if fmt.family == "120":
        return replace(support, model_grid_credit=0.18, model_equal_credit=0.04)
    return support


def separator_geometry_support_parameters(
    fmt: FormatPhysicalSpec,
    params: FormatParameters,
) -> SeparatorGeometrySupportParameters:
    support = params.separator.separator_geometry_support
    base_score = base_detection_score_parameters(fmt, params)
    return replace(
        support,
        max_photo_width_cv=base_score.full_photo_width_cv,
        max_outer_area_ratio=base_score.outer_max_area,
    )


def partial_holder_parameters(fmt: FormatPhysicalSpec, params: FormatParameters) -> PartialHolderParameters:
    holder = params.candidate.partial_holder
    if fmt.frame_geometry_profile == "medium_square":
        holder = replace(
            holder,
            min_broad_separator_width_gaps=2,
            leading_content_check=True,
            frame_content_check=True,
        )
    return holder


def nearby_separator_refinement_parameters(
    fmt: FormatPhysicalSpec,
    params: FormatParameters,
) -> NearbySeparatorRefinementParameters:
    nearby = params.separator.nearby_separator_refinement
    if fmt.family == "120":
        return replace(nearby, score_multiplier=1.28)
    return nearby
