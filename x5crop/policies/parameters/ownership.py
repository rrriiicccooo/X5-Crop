from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ParameterItems = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class FormatToleranceProfile:
    items: ParameterItems = ()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.items)


@dataclass(frozen=True)
class FormatContentProfileTolerance:
    items: ParameterItems = ()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.items)


@dataclass(frozen=True)
class SearchBudgetPolicy:
    items: ParameterItems = ()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.items)


@dataclass(frozen=True)
class FormatParameterOverrideLayers:
    tolerance: FormatToleranceProfile = FormatToleranceProfile()
    content_profile_tolerance: FormatContentProfileTolerance = (
        FormatContentProfileTolerance()
    )
    search_budget: SearchBudgetPolicy = SearchBudgetPolicy()

    def as_dict(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self.tolerance.as_dict())
        merged.update(self.content_profile_tolerance.as_dict())
        merged.update(self.search_budget.as_dict())
        return merged


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

FORMAT_CONTENT_PROFILE_TOLERANCE_PARAMETER_FIELDS = frozenset(
    {
        "content_profile_min_run_ratio",
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
    | FORMAT_CONTENT_PROFILE_TOLERANCE_PARAMETER_FIELDS
    | FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS
)


def _layer_items(overrides: dict[str, Any], fields: frozenset[str]) -> ParameterItems:
    return tuple((key, overrides[key]) for key in overrides if key in fields)


def split_format_parameter_overrides(overrides: dict[str, Any]) -> FormatParameterOverrideLayers:
    invalid = sorted(set(overrides) - FORMAT_PARAMETER_OVERRIDE_FIELDS)
    if invalid:
        joined = ", ".join(invalid)
        raise ValueError(
            "Format modules may only override physical tolerance, content profile "
            f"tolerance, or search budget parameters; invalid override(s): {joined}"
        )
    return FormatParameterOverrideLayers(
        tolerance=FormatToleranceProfile(
            _layer_items(overrides, FORMAT_TOLERANCE_PARAMETER_FIELDS)
        ),
        content_profile_tolerance=FormatContentProfileTolerance(
            _layer_items(overrides, FORMAT_CONTENT_PROFILE_TOLERANCE_PARAMETER_FIELDS)
        ),
        search_budget=SearchBudgetPolicy(
            _layer_items(overrides, FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS)
        ),
    )


def validate_format_parameter_overrides(overrides: dict[str, Any]) -> None:
    split_format_parameter_overrides(overrides)


__all__ = [
    "FORMAT_CONTENT_PROFILE_TOLERANCE_PARAMETER_FIELDS",
    "FORMAT_PARAMETER_OVERRIDE_FIELDS",
    "FORMAT_SEARCH_BUDGET_PARAMETER_FIELDS",
    "FORMAT_TOLERANCE_PARAMETER_FIELDS",
    "FormatContentProfileTolerance",
    "FormatParameterOverrideLayers",
    "FormatToleranceProfile",
    "SearchBudgetPolicy",
    "split_format_parameter_overrides",
    "validate_format_parameter_overrides",
]
