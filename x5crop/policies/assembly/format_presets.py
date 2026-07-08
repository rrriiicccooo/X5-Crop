from __future__ import annotations

from collections.abc import Callable

from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL, ReviewOnlyPolicy
from ...formats import format_spec
from ..reporting.mode_descriptions import mode_notes_for_spec, mode_role_for_spec
from .factory import build_policy_from_preset
from .presets import (
    FormatPolicyPreset,
    ModePolicyPreset,
    SeparatorWidthProfilePreset,
)
from .profile_presets import frame_fit_profile, separator_edge_pair_profile


ParameterFactory = Callable[[], FormatParameters]


def _detector_kind(format_id: str, strip_mode: str) -> str:
    spec = format_spec(format_id)
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def _review_only(format_id: str, strip_mode: str) -> ReviewOnlyPolicy:
    spec = format_spec(format_id)
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return ReviewOnlyPolicy(
            reason="dual_lane_partial_not_supported",
            selection_override="dual_lane_partial_review_only",
        )
    return ReviewOnlyPolicy()


def _separator_width_profile(format_id: str) -> SeparatorWidthProfilePreset:
    spec = format_spec(format_id)
    if spec.separator_width_profile == "broad":
        return SeparatorWidthProfilePreset(
            mode="conditional",
            separator_outer_allow_oversized_band=True,
        )
    return SeparatorWidthProfilePreset()


def _separator_geometry_support_modes(format_id: str, strip_mode: str) -> tuple[str, ...]:
    spec = format_spec(format_id)
    if spec.geometry_support_profile == "stable_dense_grid" and strip_mode == FULL:
        return ("detected_geometry", "stable_grid")
    return ()


def _output_overlap_enabled(format_id: str, strip_mode: str) -> bool:
    if strip_mode == PARTIAL:
        return True
    return format_spec(format_id).output_overlap_profile == "sensitive"


def mode_policy_preset(format_id: str, strip_mode: str) -> ModePolicyPreset:
    spec = format_spec(format_id)
    return ModePolicyPreset(
        role=mode_role_for_spec(spec, strip_mode),
        notes=mode_notes_for_spec(spec, strip_mode),
        detector_kind=_detector_kind(format_id, strip_mode),
        frame_fit=frame_fit_profile(spec.frame_fit_profile, strip_mode),
        review_only=_review_only(format_id, strip_mode),
        separator_width_profile=_separator_width_profile(format_id),
        separator_geometry_support_modes=_separator_geometry_support_modes(
            format_id,
            strip_mode,
        ),
        output_overlap_enabled=_output_overlap_enabled(format_id, strip_mode),
    )


def format_policy_preset(
    format_id: str,
    parameters: ParameterFactory,
) -> FormatPolicyPreset:
    return FormatPolicyPreset(
        format_id=format_id,
        parameters=parameters,
        separator_edge_pair=separator_edge_pair_profile(format_spec(format_id).edge_pair_profile),
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
