from __future__ import annotations

from dataclasses import replace

from ...formats import FORMAT_CHOICES, FormatSpec, format_spec
from .aggregate import FormatParameters


def _aspect(fmt: FormatSpec) -> float:
    return float(fmt.horizontal_content_aspect or 1.0)


def _is_standard_35mm_strip(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and fmt.default_count == 6 and 1.2 <= _aspect(fmt) <= 1.8


def _is_dense_half_frame(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and fmt.default_count > 6 and _aspect(fmt) < 1.0


def _is_panorama_35mm(fmt: FormatSpec) -> bool:
    return fmt.family == "35mm" and _aspect(fmt) > 2.0


def _is_medium_rectangle(fmt: FormatSpec) -> bool:
    return fmt.family == "120" and _aspect(fmt) < 1.0


def _is_medium_square(fmt: FormatSpec) -> bool:
    return fmt.family == "120" and abs(_aspect(fmt) - 1.0) <= 0.05


def _is_medium_wide(fmt: FormatSpec) -> bool:
    return fmt.family == "120" and _aspect(fmt) > 1.0


def _with_content_min_run(params: FormatParameters, value: float) -> FormatParameters:
    return replace(
        params,
        content_profile=replace(params.content_profile, min_run_ratio=float(value)),
    )


def _with_partial_edge(
    params: FormatParameters,
    *,
    ratio_extras: tuple[float, ...],
    max_candidates: int,
) -> FormatParameters:
    return replace(
        params,
        edge_anchored_content_position=replace(
            params.edge_anchored_content_position,
            ratio_extras=ratio_extras,
            max_candidates=int(max_candidates),
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
        outer_strategy=replace(
            params.outer_strategy,
            separator_gap_search_max_width_ratio=float(gap_max_width_ratio),
        ),
        separator_outer_band=replace(
            params.separator_outer_band,
            min_score=float(min_score),
            band_score=float(band_score),
            spacing_min_ratio=float(spacing_min_ratio),
            spacing_max_ratio=float(spacing_max_ratio),
            frame_error_max=float(frame_error_max),
            max_width_ratio=float(max_width_ratio),
            source_candidate_count=(
                params.separator_outer_band.source_candidate_count
                if source_candidates is None
                else int(source_candidates)
            ),
            band_candidate_count=(
                params.separator_outer_band.band_candidate_count
                if band_candidates is None
                else int(band_candidates)
            ),
            pair_candidate_count=(
                params.separator_outer_band.pair_candidate_count
                if pair_candidates is None
                else int(pair_candidates)
            ),
            max_candidates=(
                params.separator_outer_band.max_candidates
                if max_candidates is None
                else int(max_candidates)
            ),
        ),
    )


def _with_separator_width_max(params: FormatParameters, value: float) -> FormatParameters:
    return replace(
        params,
        separator_width_profile=replace(
            params.separator_width_profile,
            max_width_ratio=float(value),
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
        separator_full_width_outer=replace(
            params.separator_full_width_outer,
            margin_ratios=(
                params.separator_full_width_outer.margin_ratios
                if margin_ratios is None
                else margin_ratios
            ),
            max_candidates=(
                params.separator_full_width_outer.max_candidates
                if max_candidates is None
                else int(max_candidates)
            ),
            source_candidate_count=(
                params.separator_full_width_outer.source_candidate_count
                if source_candidates is None
                else int(source_candidates)
            ),
        ),
    )


def _with_outer_alignment(
    params: FormatParameters,
    *,
    long_margin_ratio: float | None = None,
    long_margin_cap_ratio: float | None = None,
    short_excess_ratio: float | None = None,
    short_requires_hard_anchors: bool | None = None,
    short_content_height_max: float | None = None,
) -> FormatParameters:
    current = params.content_containment_correction
    return replace(
        params,
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
    )


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    fmt = format_spec(format_name)
    params = FormatParameters(fmt.name)

    if fmt.family == "120":
        params = _with_content_min_run(params, 0.18)

    if _is_standard_35mm_strip(fmt):
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
    elif _is_dense_half_frame(fmt):
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
    elif _is_panorama_35mm(fmt):
        params = _with_content_min_run(params, 0.24)
        params = _with_outer_alignment(
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
    elif _is_medium_rectangle(fmt):
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
    elif _is_medium_square(fmt):
        params = replace(params, gap_search=replace(params.gap_search, max_width_max=720))
        params = _with_separator_width_max(params, 0.140)
        params = replace(
            params,
            short_axis_geometry_correction=replace(
                params.short_axis_geometry_correction,
                min_error=0.24,
            ),
        )
        params = _with_partial_edge(params, ratio_extras=(0.06, 0.10), max_candidates=6)
        params = _with_full_width_outer(
            params,
            margin_ratios=(0.00, 0.018, 0.035, 0.055),
            max_candidates=8,
            source_candidates=3,
        )
    elif _is_medium_wide(fmt):
        params = _with_separator_width_max(params, 0.090)
        params = _with_outer_alignment(
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


__all__ = ["format_parameters"]
