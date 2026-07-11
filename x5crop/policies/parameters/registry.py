from __future__ import annotations

from dataclasses import replace

from ...formats import FormatPhysicalSpec
from ...geometry.detection_parameters import EdgePairParameters
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
    raise ValueError(f"Unsupported physical format family: {spec.family}")


def _edge_pair_parameters(spec: FormatPhysicalSpec) -> EdgePairParameters:
    profile = parameter_profile_for_spec(spec)
    if profile in {"medium_square", "medium_wide"}:
        return EdgePairParameters(
            window_ratio=0.100,
            min_gutter_ratio=0.001,
            max_gutter_ratio=0.080,
            min_strength=0.24,
            min_background=0.02,
            min_quality_for_model_gap=0.28,
            min_quality_for_hard_gap=0.30,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.030,
        )
    profiles = {
        "standard_35mm": EdgePairParameters(
            window_ratio=0.080,
            min_gutter_ratio=0.004,
            max_gutter_ratio=0.050,
            min_strength=0.42,
            min_background=0.62,
            min_quality_for_model_gap=0.0,
            min_quality_for_hard_gap=0.0,
            hard_gap_quality_ratio=1.0,
            max_hard_shift_ratio=0.0,
        ),
        "dense_half": EdgePairParameters(
            window_ratio=0.090,
            min_gutter_ratio=0.003,
            max_gutter_ratio=0.060,
            min_strength=0.46,
            min_background=0.66,
            min_quality_for_model_gap=1.05,
            min_quality_for_hard_gap=0.70,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.040,
        ),
        "panoramic_35mm": EdgePairParameters(
            window_ratio=0.060,
            min_gutter_ratio=0.002,
            max_gutter_ratio=0.035,
            min_strength=0.45,
            min_background=0.64,
            min_quality_for_model_gap=1.03,
            min_quality_for_hard_gap=0.70,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.035,
        ),
        "medium_rectangle": EdgePairParameters(
            window_ratio=0.075,
            min_gutter_ratio=0.001,
            max_gutter_ratio=0.055,
            min_strength=0.32,
            min_background=0.20,
            min_quality_for_model_gap=0.58,
            min_quality_for_hard_gap=0.50,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.035,
        ),
        "dual_lane": EdgePairParameters(
            window_ratio=0.080,
            min_gutter_ratio=0.004,
            max_gutter_ratio=0.050,
            min_strength=0.42,
            min_background=0.62,
            min_quality_for_model_gap=0.0,
            min_quality_for_hard_gap=0.0,
            hard_gap_quality_ratio=1.0,
            max_hard_shift_ratio=0.0,
        ),
    }
    return profiles[profile]


def _with_profile_parameters(
    params: FormatParameters,
    spec: FormatPhysicalSpec,
) -> FormatParameters:
    nominal_width_mm = float(spec.nominal_frame_size_mm.width_mm)
    nominal_height_mm = float(spec.nominal_frame_size_mm.height_mm)
    gap_search = params.separator.gap_search
    return replace(
        params,
        separator=replace(
            params.separator,
            edge_pair=_edge_pair_parameters(spec),
            gap_search=replace(
                gap_search,
                radius=replace(
                    gap_search.radius,
                    mm=nominal_width_mm * gap_search.radius.fallback_ratio,
                ),
                max_width=replace(
                    gap_search.max_width,
                    mm=nominal_width_mm * gap_search.max_width.fallback_ratio,
                ),
                min_width=replace(
                    gap_search.min_width,
                    mm=nominal_width_mm * gap_search.min_width.fallback_ratio,
                ),
                guard=replace(
                    gap_search.guard,
                    mm=nominal_width_mm * gap_search.guard.fallback_ratio,
                ),
            ),
            separator_width_profile_search=replace(
                params.separator.separator_width_profile_search,
                edge_margin=replace(
                    params.separator.separator_width_profile_search.edge_margin,
                    mm=(
                        nominal_height_mm
                        * params.separator.separator_width_profile_search.edge_margin.fallback_ratio
                    ),
                ),
            ),
        ),
        outer=replace(
            params.outer,
            separator_outer_band=replace(
                params.outer.separator_outer_band,
                edge_margin=replace(
                    params.outer.separator_outer_band.edge_margin,
                    mm=(
                        nominal_height_mm
                        * params.outer.separator_outer_band.edge_margin.fallback_ratio
                    ),
                ),
            ),
        ),
    )


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
    separator_weight: float | None = None,
    geometry_weight: float | None = None,
    content_weight: float | None = None,
    model_equal_credit: float | None = None,
    nearby_separator_score_multiplier: float | None = None,
) -> FormatParameters:
    base_score = params.candidate.base_detection_score
    calibration = params.candidate.scoring_calibration
    support_score = params.candidate.separator_support_score
    geometry_support = params.candidate.geometry_support_score
    nearby = params.separator.nearby_separator_refinement
    resolved_photo_width_cv = (
        base_score.unstable_photo_width_cv
        if full_photo_width_cv is None
        else float(full_photo_width_cv)
    )
    return replace(
        params,
        candidate=replace(
            params.candidate,
            base_detection_score=replace(
                base_score,
                photo_width_cv_norm=resolved_photo_width_cv,
                unstable_photo_width_cv=resolved_photo_width_cv,
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
                model_equal_credit=(
                    support_score.model_equal_credit
                    if model_equal_credit is None
                    else float(model_equal_credit)
                ),
            ),
            geometry_support_score=replace(
                geometry_support,
                photo_width_cv_norm=resolved_photo_width_cv,
            ),
        ),
        separator=replace(
            params.separator,
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


def format_parameters(spec: FormatPhysicalSpec) -> FormatParameters:
    profile = parameter_profile_for_spec(spec)
    params = _with_profile_parameters(FormatParameters(), spec)

    if spec.family == "120":
        params = _with_content_min_run(params, 0.18)
        params = _with_candidate_scoring_profile(
            params,
            full_photo_width_cv=0.012,
            separator_weight=0.36,
            geometry_weight=0.32,
            content_weight=0.32,
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
            model_equal_credit=0.08,
        )
        params = _with_content_min_run(params, 0.16)
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
            model_equal_credit=0.06,
        )
        params = _with_content_min_run(params, 0.24)
        params = _with_content_containment_correction(
            params,
            long_margin_ratio=0.008,
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
        params = replace(
            params,
            separator=replace(
                params.separator,
                gap_search=replace(
                    params.separator.gap_search,
                    max_width=replace(
                        params.separator.gap_search.max_width,
                        max_px=720,
                    ),
                ),
            ),
        )
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
