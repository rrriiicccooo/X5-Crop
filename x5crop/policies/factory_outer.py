from __future__ import annotations

from ..geometry.detection_parameters import OuterBoxDetectionParameters, OuterMaskProfileParameters
from .factory_presets import ModePolicyPreset
from .parameter_aggregate import FormatParameters
from .runtime_base import FULL
from .runtime_outer import (
    ContentFloatingOuterPolicy,
    EdgeAnchorOuterPolicy,
    FormatGeometryRetryPolicy,
    FullWidthSeparatorOuterPolicy,
    GridOuterRefinePolicy,
    OuterContentAlignmentPolicy,
    OuterPolicy,
    SeparatorOuterBandPolicy,
    ShortAxisAspectRetryPolicy,
    WideSeparatorOuterPolicy,
)


def wide_separator_outer_policy(mode_preset: ModePolicyPreset) -> WideSeparatorOuterPolicy:
    wide_separator = mode_preset.wide_separator
    return WideSeparatorOuterPolicy(
        mode=wide_separator.mode,
        required_count=3,
        full_selection_enabled=wide_separator.full_selection_enabled,
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
    separator_full_width = params.separator_full_width_outer
    content_floating_enabled = bool(
        outer.content_floating_full if is_full else outer.content_floating_partial
    )
    wide_separator = mode_preset.wide_separator
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
        separator_local=(
            outer.separator_local_full_mode
            if is_full and outer.separator_local_full_enabled
            else outer.separator_local_partial_mode
            if (not is_full and outer.separator_local_partial_enabled)
            else "off"
        ),
        separator_full_width=(
            outer.separator_full_width_full_mode
            if is_full
            else outer.separator_full_width_partial_mode
        ),
        separator_outer_allow_oversized_band=wide_separator.separator_outer_allow_oversized_band,
        separator_outer_oversized_band_max_ratio=wide_separator.separator_outer_oversized_band_max_ratio,
        separator_outer_oversized_band_score_penalty=wide_separator.separator_outer_oversized_band_score_penalty,
        separator_gap_search_max_width_ratio=float(outer.separator_gap_search_max_width_ratio),
        wide_separator=wide_separator.mode,
        wide_separator_outer=wide_separator_outer_policy(mode_preset),
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
        base_candidates=OuterBoxDetectionParameters(
            white_x_width_multiplier=float(base_candidates.white_x_width_multiplier),
            white_x_extra_ratio=float(base_candidates.white_x_extra_ratio),
            candidate_max_area=float(base_candidates.candidate_max_area),
            mask_expand_ratio=float(base_candidates.mask_expand_ratio),
            mask_profiles=tuple(
                OuterMaskProfileParameters(
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
        separator_full_width_outer=FullWidthSeparatorOuterPolicy(
            required_count=int(separator_full_width.required_count),
            source_candidate_count=int(separator_full_width.source_candidate_count),
            margin_ratios=tuple(float(value) for value in separator_full_width.margin_ratios),
            max_candidates=int(separator_full_width.max_candidates),
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

__all__ = [
    'outer_policy',
    'wide_separator_outer_policy',
]
