from __future__ import annotations

from collections.abc import Callable

from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL, ReviewOnlyPolicy
from ...formats import FormatPhysicalSpec, format_spec
from ...formats.traits import FormatRuntimeTraits, runtime_traits_for_spec
from .factory import build_policy_from_preset
from .presets import (
    FormatPolicyPreset,
    ModePolicyPreset,
    SeparatorWidthProfilePreset,
)
from .profile_presets import frame_fit_profile, separator_edge_pair_profile


ParameterFactory = Callable[[], FormatParameters]


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def _review_only(spec: FormatPhysicalSpec, strip_mode: str) -> ReviewOnlyPolicy:
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return ReviewOnlyPolicy(
            reason="dual_lane_partial_not_supported",
            selection_override="dual_lane_partial_review_only",
        )
    return ReviewOnlyPolicy()


def _separator_width_profile(traits: FormatRuntimeTraits) -> SeparatorWidthProfilePreset:
    if traits.separator_width_profile == "broad":
        return SeparatorWidthProfilePreset(
            mode="conditional",
            separator_outer_allow_oversized_band=True,
        )
    return SeparatorWidthProfilePreset()


def _separator_geometry_support_modes(
    traits: FormatRuntimeTraits,
    strip_mode: str,
) -> tuple[str, ...]:
    if traits.geometry_support_profile == "stable_dense_grid" and strip_mode == FULL:
        return ("detected_geometry", "stable_grid")
    return ()


def mode_policy_preset(format_id: str, strip_mode: str) -> ModePolicyPreset:
    spec = format_spec(format_id)
    traits = runtime_traits_for_spec(spec)
    return ModePolicyPreset(
        detector_kind=_detector_kind(spec, strip_mode),
        frame_fit=frame_fit_profile(traits.frame_fit_profile, strip_mode),
        review_only=_review_only(spec, strip_mode),
        separator_width_profile=_separator_width_profile(traits),
        separator_geometry_support_modes=_separator_geometry_support_modes(
            traits,
            strip_mode,
        ),
    )


def format_policy_preset(
    format_id: str,
    parameters: ParameterFactory,
) -> FormatPolicyPreset:
    spec = format_spec(format_id)
    traits = runtime_traits_for_spec(spec)
    return FormatPolicyPreset(
        format_spec=spec,
        parameters=parameters,
        separator_edge_pair=separator_edge_pair_profile(traits.edge_pair_profile),
        modes={
            FULL: mode_policy_preset(format_id, FULL),
            PARTIAL: mode_policy_preset(format_id, PARTIAL),
        },
    )


def build_policy_from_format(
    format_id: str,
    parameters: ParameterFactory,
    strip_mode: str,
):
    return build_policy_from_preset(format_policy_preset(format_id, parameters), strip_mode)


__all__ = [
    "build_policy_from_format",
    "format_policy_preset",
    "mode_policy_preset",
]
