from __future__ import annotations

from dataclasses import replace

from ...formats import FormatPhysicalSpec
from .aggregate import FormatParameters


def parameter_profile_for_spec(spec: FormatPhysicalSpec) -> str:
    if spec.physical_layout == "dual_lane":
        return "dual_lane"
    aspect = spec.horizontal_content_aspect
    if spec.family == "35mm":
        if spec.default_count > 6 and aspect < 1.0:
            return "dense_half"
        if aspect > 2.0:
            return "panoramic_35mm"
        return "standard_35mm"
    if spec.family == "120":
        if abs(aspect - 1.0) <= 0.05:
            return "medium_square"
        if aspect < 1.0:
            return "medium_rectangle"
        return "medium_wide"
    raise ValueError(f"unsupported physical format family: {spec.family}")


def _with_content_min_run(
    params: FormatParameters,
    minimum_run_ratio: float,
) -> FormatParameters:
    return replace(
        params,
        content=replace(
            params.content,
            content_profile=replace(
                params.content.content_profile,
                min_run_ratio=float(minimum_run_ratio),
            ),
        ),
    )


def _with_photo_dimension_scoring(
    params: FormatParameters,
    *,
    maximum_photo_width_cv: float,
    separator_weight: float | None = None,
    geometry_weight: float | None = None,
    content_weight: float | None = None,
) -> FormatParameters:
    base = params.candidate.base_detection_score
    calibration = params.candidate.scoring_calibration
    geometry = params.candidate.geometry_support_score
    return replace(
        params,
        candidate=replace(
            params.candidate,
            base_detection_score=replace(
                base,
                photo_width_cv_norm=float(maximum_photo_width_cv),
                maximum_photo_width_cv=float(maximum_photo_width_cv),
            ),
            geometry_support_score=replace(
                geometry,
                photo_width_cv_norm=float(maximum_photo_width_cv),
            ),
            scoring_calibration=replace(
                calibration,
                separator_weight=(
                    calibration.separator_weight
                    if separator_weight is None
                    else float(separator_weight)
                ),
                geometry_weight=(
                    calibration.geometry_weight
                    if geometry_weight is None
                    else float(geometry_weight)
                ),
                content_weight=(
                    calibration.content_weight
                    if content_weight is None
                    else float(content_weight)
                ),
            ),
        ),
    )


def _with_short_axis_alignment(
    params: FormatParameters,
    *,
    excess_ratio: float,
    requires_hard_anchors: bool,
    maximum_content_height: float,
) -> FormatParameters:
    current = params.sequence.content_alignment
    return replace(
        params,
        sequence=replace(
            params.sequence,
            content_alignment=replace(
                current,
                short_excess_ratio=float(excess_ratio),
                short_requires_hard_anchors=bool(requires_hard_anchors),
                short_content_height_max=float(maximum_content_height),
            ),
        ),
    )


def format_parameters(spec: FormatPhysicalSpec) -> FormatParameters:
    profile = parameter_profile_for_spec(spec)
    params = FormatParameters()

    if spec.family == "120":
        params = _with_content_min_run(params, 0.18)
        params = _with_photo_dimension_scoring(
            params,
            maximum_photo_width_cv=0.012,
            separator_weight=0.36,
            geometry_weight=0.32,
            content_weight=0.32,
        )

    if profile == "dense_half":
        params = _with_photo_dimension_scoring(
            params,
            maximum_photo_width_cv=0.008,
        )
        params = _with_content_min_run(params, 0.16)
    elif profile == "panoramic_35mm":
        params = _with_content_min_run(params, 0.24)
    elif profile == "medium_wide":
        params = _with_short_axis_alignment(
            params,
            excess_ratio=0.024,
            requires_hard_anchors=True,
            maximum_content_height=0.970,
        )
    return params
