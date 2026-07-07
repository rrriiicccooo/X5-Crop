from __future__ import annotations

from dataclasses import replace

from ...formats import FormatSpec
from ..parameters.aggregate import FormatParameters
from ..parameters.base import PartialCountParameters
from ..parameters.diagnostics import LuckyPassRiskParameters
from ..parameters.finalization import PartialHolderParameters
from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from ..parameters.separator import (
    LeadingGridFailureParameters,
    NearbySeparatorRefinementParameters,
    SeparatorGateParameters,
    SeparatorGeometrySupportParameters,
)


def _has_physical_risk(fmt: FormatSpec, risk: str) -> bool:
    return risk in fmt.known_physical_risks


def _is_dense_half_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and fmt.default_count > 6 and float(fmt.horizontal_content_aspect or 1.0) < 1.0


def _is_panorama_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and float(fmt.horizontal_content_aspect or 1.0) > 2.0


def partial_count_parameters(fmt: FormatSpec, params: FormatParameters) -> PartialCountParameters:
    partial = params.partial_counts
    include_default = (
        _has_physical_risk(fmt, "wide_content_can_mask_separator")
        or _has_physical_risk(fmt, "holder_edge_can_mimic_separator")
    )
    return replace(partial, include_default_auto=include_default)


def separator_gate_parameters(fmt: FormatSpec, params: FormatParameters) -> SeparatorGateParameters:
    gate = params.separator_gate
    if _has_physical_risk(fmt, "holder_edge_can_mimic_separator"):
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
        enabled=_has_physical_risk(fmt, "weak_grid_may_hide_missing_separator"),
    )


def base_detection_score_parameters(fmt: FormatSpec, params: FormatParameters) -> BaseDetectionScoreParameters:
    score = params.base_detection_score
    if _is_dense_half_frame(fmt):
        score = replace(score, full_width_cv=0.008)
    elif fmt.family == "120":
        score = replace(score, full_width_cv=0.012)
    if _has_physical_risk(fmt, "holder_edge_can_mimic_separator"):
        score = replace(
            score,
            outer_max_area=1.0,
            outer_too_large=1.0,
        )
    elif _has_physical_risk(fmt, "short_axis_correction_can_overtrust_holder"):
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
    if (
        _has_physical_risk(fmt, "holder_edge_can_mimic_separator")
        or _has_physical_risk(fmt, "short_axis_correction_can_overtrust_holder")
    ):
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
        max_width_cv=base_score.full_width_cv,
        max_outer_area_ratio=base_score.outer_max_area,
    )


def partial_holder_parameters(fmt: FormatSpec, params: FormatParameters) -> PartialHolderParameters:
    holder = params.partial_holder
    if _has_physical_risk(fmt, "holder_edge_can_mimic_separator"):
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


def lucky_pass_risk_parameters(fmt: FormatSpec, params: FormatParameters) -> LuckyPassRiskParameters:
    return replace(
        params.lucky_pass_risk,
        enabled=_has_physical_risk(fmt, "weak_grid_may_hide_missing_separator"),
    )


__all__ = [
    "base_detection_score_parameters",
    "leading_grid_failure_parameters",
    "lucky_pass_risk_parameters",
    "nearby_separator_refinement_parameters",
    "partial_count_parameters",
    "partial_holder_parameters",
    "scoring_calibration_parameters",
    "separator_gate_parameters",
    "separator_geometry_support_parameters",
    "separator_support_score_parameters",
]
