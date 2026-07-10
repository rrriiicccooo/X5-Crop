from __future__ import annotations

from dataclasses import replace

from ...formats import FORMAT_CHOICES, format_spec
from .aggregate import FormatParameters


def _with_content_min_run(params: FormatParameters, value: float) -> FormatParameters:
    return replace(
        params,
        content=replace(
            params.content,
            content_profile=replace(
                params.content.content_profile,
                min_run_ratio=float(value),
            ),
        ),
    )


def _with_partial_edge(
    params: FormatParameters,
    *,
    ratio_extras: tuple[float, ...],
    max_candidates: int,
) -> FormatParameters:
    return replace(
        params,
        outer=replace(
            params.outer,
            edge_anchored_content_position=replace(
                params.outer.edge_anchored_content_position,
                ratio_extras=ratio_extras,
                max_candidates=int(max_candidates),
            ),
        ),
    )


def _with_separator_outer(
    params: FormatParameters,
    *,
    min_score: float,
    band_score: float,
    spacing_min_ratio: float,
    spacing_max_ratio: float,
    frame_error_max: float,
    max_width_ratio: float,
    gap_max_width_ratio: float,
    source_candidates: int | None = None,
    band_candidates: int | None = None,
    pair_candidates: int | None = None,
    max_candidates: int | None = None,
) -> FormatParameters:
    return replace(
        params,
        outer=replace(
            params.outer,
            outer_strategy=replace(
                params.outer.outer_strategy,
                separator_gap_search_max_width_ratio=float(gap_max_width_ratio),
            ),
            separator_outer_band=replace(
                params.outer.separator_outer_band,
                min_score=float(min_score),
                band_score=float(band_score),
                spacing_min_ratio=float(spacing_min_ratio),
                spacing_max_ratio=float(spacing_max_ratio),
                frame_error_max=float(frame_error_max),
                max_width_ratio=float(max_width_ratio),
                source_candidate_count=(
                    params.outer.separator_outer_band.source_candidate_count
                    if source_candidates is None
                    else int(source_candidates)
                ),
                band_candidate_count=(
                    params.outer.separator_outer_band.band_candidate_count
                    if band_candidates is None
                    else int(band_candidates)
                ),
                pair_candidate_count=(
                    params.outer.separator_outer_band.pair_candidate_count
                    if pair_candidates is None
                    else int(pair_candidates)
                ),
                max_candidates=(
                    params.outer.separator_outer_band.max_candidates
                    if max_candidates is None
                    else int(max_candidates)
                ),
            ),
        ),
    )


def _with_separator_width_max(params: FormatParameters, value: float) -> FormatParameters:
    return replace(
        params,
        separator=replace(
            params.separator,
            separator_width_profile=replace(
                params.separator.separator_width_profile,
                max_width_ratio=float(value),
            ),
        ),
    )


def _with_full_width_outer(
    params: FormatParameters,
    *,
    margin_ratios: tuple[float, ...] | None = None,
    max_candidates: int | None = None,
    source_candidates: int | None = None,
) -> FormatParameters:
    return replace(
        params,
        outer=replace(
            params.outer,
            separator_full_width_outer=replace(
                params.outer.separator_full_width_outer,
                margin_ratios=(
                    params.outer.separator_full_width_outer.margin_ratios
                    if margin_ratios is None
                    else margin_ratios
                ),
                max_candidates=(
                    params.outer.separator_full_width_outer.max_candidates
                    if max_candidates is None
                    else int(max_candidates)
                ),
                source_candidate_count=(
                    params.outer.separator_full_width_outer.source_candidate_count
                    if source_candidates is None
                    else int(source_candidates)
                ),
            ),
        ),
    )


def _with_content_containment_correction(
    params: FormatParameters,
    *,
    long_margin_ratio: float | None = None,
    long_margin_cap_ratio: float | None = None,
) -> FormatParameters:
    current = params.outer.content_containment_correction
    return replace(
        params,
        outer=replace(
            params.outer,
            content_containment_correction=replace(
                current,
                long_margin_ratio=(
                    current.long_margin_ratio
                    if long_margin_ratio is None
                    else float(long_margin_ratio)
                ),
                long_margin_cap_ratio=(
                    current.long_margin_cap_ratio
                    if long_margin_cap_ratio is None
                    else float(long_margin_cap_ratio)
                ),
            ),
        ),
    )


def _with_outer_alignment_evidence(
    params: FormatParameters,
    *,
    short_excess_ratio: float | None = None,
    short_requires_hard_anchors: bool | None = None,
    short_content_height_max: float | None = None,
) -> FormatParameters:
    current = params.outer.outer_alignment_evidence
    return replace(
        params,
        outer=replace(
            params.outer,
            outer_alignment_evidence=replace(
                current,
                short_excess_ratio=(
                    current.short_excess_ratio
                    if short_excess_ratio is None
                    else float(short_excess_ratio)
                ),
                short_requires_hard_anchors=(
                    current.short_requires_hard_anchors
                    if short_requires_hard_anchors is None
                    else bool(short_requires_hard_anchors)
                ),
                short_content_height_max=(
                    current.short_content_height_max
                    if short_content_height_max is None
                    else float(short_content_height_max)
                ),
            ),
        ),
    )


def _with_candidate_scoring_profile(
    params: FormatParameters,
    *,
    full_photo_width_cv: float | None = None,
    outer_max_area: float | None = None,
    outer_too_large: float | None = None,
    separator_weight: float | None = None,
    geometry_weight: float | None = None,
    content_weight: float | None = None,
    model_grid_credit: float | None = None,
    model_equal_credit: float | None = None,
    nearby_separator_score_multiplier: float | None = None,
) -> FormatParameters:
    base_score = params.candidate.base_detection_score
    calibration = params.candidate.scoring_calibration
    support_score = params.candidate.separator_support_score
    geometry_support = params.separator.separator_geometry_support
    nearby = params.separator.nearby_separator_refinement
    resolved_photo_width_cv = (
        base_score.full_photo_width_cv
        if full_photo_width_cv is None
        else float(full_photo_width_cv)
    )
    resolved_outer_max_area = (
        base_score.outer_max_area
        if outer_max_area is None
        else float(outer_max_area)
    )
    return replace(
        params,
        candidate=replace(
            params.candidate,
            base_detection_score=replace(
                base_score,
                full_photo_width_cv=resolved_photo_width_cv,
                outer_max_area=resolved_outer_max_area,
                outer_too_large=(
                    base_score.outer_too_large
                    if outer_too_large is None
                    else float(outer_too_large)
                ),
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
            separator_support_score=replace(
                support_score,
                model_grid_credit=(
                    support_score.model_grid_credit
                    if model_grid_credit is None
                    else float(model_grid_credit)
                ),
                model_equal_credit=(
                    support_score.model_equal_credit
                    if model_equal_credit is None
                    else float(model_equal_credit)
                ),
            ),
        ),
        separator=replace(
            params.separator,
            separator_geometry_support=replace(
                geometry_support,
                max_photo_width_cv=resolved_photo_width_cv,
                max_outer_area_ratio=resolved_outer_max_area,
            ),
            nearby_separator_refinement=replace(
                nearby,
                score_multiplier=(
                    nearby.score_multiplier
                    if nearby_separator_score_multiplier is None
                    else float(nearby_separator_score_multiplier)
                ),
            ),
        ),
    )


def format_parameters(format_id: str) -> FormatParameters:
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_id}")
    fmt = format_spec(format_id)
    profile = fmt.frame_geometry_profile
    params = FormatParameters()

    if fmt.family == "120":
        params = _with_content_min_run(params, 0.18)
        params = _with_candidate_scoring_profile(
            params,
            full_photo_width_cv=0.012,
            separator_weight=0.36,
            geometry_weight=0.32,
            content_weight=0.32,
            model_grid_credit=0.18,
            model_equal_credit=0.04,
            nearby_separator_score_multiplier=1.28,
        )

    if profile == "standard_35mm":
        params = _with_separator_outer(
            params,
            min_score=0.72,
            band_score=0.52,
            spacing_min_ratio=0.92,
            spacing_max_ratio=1.10,
            frame_error_max=0.07,
            max_width_ratio=0.050,
            gap_max_width_ratio=0.060,
            source_candidates=1,
            band_candidates=12,
            pair_candidates=2,
            max_candidates=4,
        )
        params = _with_partial_edge(params, ratio_extras=(0.02, 0.04), max_candidates=4)
    elif profile == "dense_half":
        params = _with_candidate_scoring_profile(
            params,
            full_photo_width_cv=0.008,
            model_grid_credit=0.25,
            model_equal_credit=0.08,
        )
        params = _with_content_min_run(params, 0.16)
        params = _with_separator_width_max(params, 0.100)
        params = _with_separator_outer(
            params,
            min_score=0.68,
            band_score=0.48,
            spacing_min_ratio=0.90,
            spacing_max_ratio=1.12,
            frame_error_max=0.08,
            max_width_ratio=0.055,
            gap_max_width_ratio=0.055,
            source_candidates=1,
            band_candidates=14,
            pair_candidates=2,
            max_candidates=4,
        )
        params = _with_partial_edge(params, ratio_extras=(0.04, 0.06), max_candidates=4)
    elif profile == "panoramic_35mm":
        params = _with_candidate_scoring_profile(
            params,
            model_grid_credit=0.20,
            model_equal_credit=0.06,
        )
        params = _with_content_min_run(params, 0.24)
        params = _with_content_containment_correction(
            params,
            long_margin_ratio=0.008,
            long_margin_cap_ratio=0.012,
        )
        params = _with_separator_outer(
            params,
            min_score=0.66,
            band_score=0.44,
            spacing_min_ratio=0.86,
            spacing_max_ratio=1.16,
            frame_error_max=0.10,
            max_width_ratio=0.045,
            gap_max_width_ratio=0.060,
            source_candidates=1,
            band_candidates=8,
            pair_candidates=3,
            max_candidates=4,
        )
        params = _with_partial_edge(params, ratio_extras=(0.03, 0.06), max_candidates=4)
    elif profile == "medium_rectangle":
        params = _with_separator_outer(
            params,
            min_score=0.60,
            band_score=0.38,
            spacing_min_ratio=0.84,
            spacing_max_ratio=1.20,
            frame_error_max=0.14,
            max_width_ratio=0.090,
            gap_max_width_ratio=0.080,
            band_candidates=10,
            pair_candidates=3,
            max_candidates=8,
        )
        params = _with_partial_edge(params, ratio_extras=(0.04, 0.08), max_candidates=4)
    elif profile == "medium_square":
        params = _with_candidate_scoring_profile(
            params,
            outer_max_area=1.0,
            outer_too_large=1.0,
        )
        params = replace(
            params,
            separator=replace(
                params.separator,
                gap_search=replace(params.separator.gap_search, max_width_max=720),
            ),
        )
        params = _with_separator_width_max(params, 0.140)
        params = replace(
            params,
            outer=replace(
                params.outer,
                short_axis_geometry_correction=replace(
                    params.outer.short_axis_geometry_correction,
                    min_error=0.24,
                ),
            ),
        )
        params = _with_partial_edge(params, ratio_extras=(0.06, 0.10), max_candidates=6)
        params = _with_full_width_outer(
            params,
            margin_ratios=(0.00, 0.018, 0.035, 0.055),
            max_candidates=8,
            source_candidates=3,
        )
    elif profile == "medium_wide":
        params = _with_candidate_scoring_profile(
            params,
            outer_too_large=0.995,
        )
        params = _with_separator_width_max(params, 0.090)
        params = _with_outer_alignment_evidence(
            params,
            short_excess_ratio=0.024,
            short_requires_hard_anchors=True,
            short_content_height_max=0.970,
        )
        params = _with_separator_outer(
            params,
            min_score=0.58,
            band_score=0.36,
            spacing_min_ratio=0.82,
            spacing_max_ratio=1.24,
            frame_error_max=0.18,
            max_width_ratio=0.110,
            gap_max_width_ratio=0.095,
        )
        params = _with_partial_edge(params, ratio_extras=(0.04, 0.08), max_candidates=4)

    return params
