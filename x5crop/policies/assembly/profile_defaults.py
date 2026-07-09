from __future__ import annotations

from dataclasses import replace

from ...formats import FormatSpec
from ..parameters.aggregate import FormatParameters
from ..parameters.base import PartialCountParameters
from ..parameters.finalization import PartialHolderParameters
from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from ..parameters.separator import (
    LeadingGridFailureParameters,
    NearbySeparatorRefinementParameters,
    SeparatorSupportParameters,
    SeparatorGeometrySupportParameters,
)


def _content_aspect(fmt: FormatSpec) -> float:
    return float(fmt.horizontal_content_aspect or 1.0)


def _is_standard_35mm_strip(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and fmt.default_count == 6 and 1.2 <= _content_aspect(fmt) <= 1.8


def _is_dense_half_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and fmt.default_count > 6 and _content_aspect(fmt) < 1.0


def _is_panorama_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and _content_aspect(fmt) > 2.0


def _is_square_medium_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "120" and abs(_content_aspect(fmt) - 1.0) <= 0.05


def _is_landscape_medium_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "120" and _content_aspect(fmt) > 1.1


def partial_count_parameters(fmt: FormatSpec, params: FormatParameters) -> PartialCountParameters:
    partial = params.partial_counts
    include_default = bool(fmt.complete_strip_can_be_underfilled)
    return replace(partial, include_default_auto=include_default)


def separator_support_parameters(fmt: FormatSpec, params: FormatParameters) -> SeparatorSupportParameters:
    gate = params.separator_support
    if _is_square_medium_frame(fmt):
        return replace(
            gate,
            edge_pair_min_score_without_broad_width=1.0,
            edge_pair_min_score_with_broad_width=0.0,
            min_broad_separator_width_gaps_for_auto=0,
        )
    return gate


def leading_grid_failure_parameters(fmt: FormatSpec, params: FormatParameters) -> LeadingGridFailureParameters:
    return replace(
        params.leading_grid_failure,
        enabled=_is_standard_35mm_strip(fmt),
    )


def base_detection_score_parameters(fmt: FormatSpec, params: FormatParameters) -> BaseDetectionScoreParameters:
    score = params.base_detection_score
    if _is_dense_half_frame(fmt):
        score = replace(score, full_photo_width_cv=0.008)
    elif fmt.family == "120":
        score = replace(score, full_photo_width_cv=0.012)
    if _is_square_medium_frame(fmt):
        score = replace(
            score,
            outer_max_area=1.0,
            outer_too_large=1.0,
        )
    elif _is_landscape_medium_frame(fmt):
        score = replace(
            score,
            outer_too_large=0.995,
        )
    return score


def scoring_calibration_parameters(fmt: FormatSpec, params: FormatParameters) -> ScoringCalibrationParameters:
    calibration = params.scoring_calibration
    if fmt.family == "120":
        calibration = replace(
            calibration,
            separator_weight=0.36,
            geometry_weight=0.32,
            content_weight=0.32,
        )
    if _is_square_medium_frame(fmt) or _is_landscape_medium_frame(fmt):
        calibration = replace(calibration, hard_full_confidence_floor=0.86)
    return calibration


def separator_support_score_parameters(fmt: FormatSpec, params: FormatParameters) -> SeparatorSupportScoreParameters:
    support = params.separator_support_score
    if _is_dense_half_frame(fmt):
        return replace(support, model_grid_credit=0.25, model_equal_credit=0.08)
    if _is_panorama_frame(fmt):
        return replace(support, model_grid_credit=0.20, model_equal_credit=0.06)
    if fmt.family == "120":
        return replace(support, model_grid_credit=0.18, model_equal_credit=0.04)
    return support


def separator_geometry_support_parameters(
    fmt: FormatSpec,
    params: FormatParameters,
) -> SeparatorGeometrySupportParameters:
    support = params.separator_geometry_support
    base_score = base_detection_score_parameters(fmt, params)
    return replace(
        support,
        max_photo_width_cv=base_score.full_photo_width_cv,
        max_outer_area_ratio=base_score.outer_max_area,
    )


def partial_holder_parameters(fmt: FormatSpec, params: FormatParameters) -> PartialHolderParameters:
    holder = params.partial_holder
    if _is_square_medium_frame(fmt):
        holder = replace(
            holder,
            min_broad_separator_width_gaps=2,
            leading_content_check=True,
            frame_content_check=True,
        )
    return holder


def nearby_separator_refinement_parameters(
    fmt: FormatSpec,
    params: FormatParameters,
) -> NearbySeparatorRefinementParameters:
    nearby = params.nearby_separator_refinement
    if fmt.family == "120":
        return replace(nearby, score_multiplier=1.28)
    return nearby


__all__ = [
    "base_detection_score_parameters",
    "leading_grid_failure_parameters",
    "nearby_separator_refinement_parameters",
    "partial_count_parameters",
    "partial_holder_parameters",
    "scoring_calibration_parameters",
    "separator_support_parameters",
    "separator_geometry_support_parameters",
    "separator_support_score_parameters",
]
