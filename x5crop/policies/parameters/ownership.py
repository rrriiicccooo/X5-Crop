from __future__ import annotations

FORMAT_TOLERANCE_PARAMETER_FIELDS = frozenset(
    {
        "gap_max_width_max",
        "outer_align_long_margin_ratio",
        "outer_align_long_margin_cap_ratio",
        "outer_align_short_excess_ratio",
        "outer_align_short_requires_hard_anchors",
        "outer_align_short_content_height_max",
        "partial_edge_ratio_extras",
        "separator_outer_min_score",
        "separator_outer_band_score",
        "separator_outer_spacing_min_ratio",
        "separator_outer_spacing_max_ratio",
        "separator_outer_frame_error_max",
        "separator_outer_max_width_ratio",
        "separator_outer_gap_max_width_ratio",
        "separator_width_profile_max_width_ratio",
        "short_axis_geometry_correction_min_error",
    }
)

FORMAT_SIGNAL_TOLERANCE_PARAMETER_FIELDS = frozenset(
    {
        "content_profile_min_run_ratio",
        "separator_width_profile_min_mean",
        "separator_width_profile_min_prominence",
    }
)

FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS = frozenset(
    {
        "partial_edge_max_candidates",
        "separator_full_width_outer_margin_ratios",
        "separator_full_width_outer_max_candidates",
        "separator_full_width_outer_source_candidates",
        "separator_outer_source_candidates",
        "separator_outer_band_candidates",
        "separator_outer_pair_candidates",
        "separator_outer_max_candidates",
    }
)

FORMAT_PARAMETER_OVERRIDE_FIELDS = frozenset(
    FORMAT_TOLERANCE_PARAMETER_FIELDS
    | FORMAT_SIGNAL_TOLERANCE_PARAMETER_FIELDS
    | FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS
)


def validate_format_parameter_overrides(overrides: dict[str, object]) -> None:
    invalid = sorted(set(overrides) - FORMAT_PARAMETER_OVERRIDE_FIELDS)
    if invalid:
        joined = ", ".join(invalid)
        raise ValueError(
            "Format modules may only override physical tolerance, signal tolerance, "
            f"or search budget parameters; invalid override(s): {joined}"
        )


__all__ = [
    "FORMAT_PARAMETER_OVERRIDE_FIELDS",
    "FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS",
    "FORMAT_SIGNAL_TOLERANCE_PARAMETER_FIELDS",
    "FORMAT_TOLERANCE_PARAMETER_FIELDS",
    "validate_format_parameter_overrides",
]
