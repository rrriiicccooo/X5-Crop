from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL, ReviewOnlyPolicy
from ...formats import FormatPhysicalSpec
from .factory import build_policy_from_preset
from .presets import (
    FormatPolicyPreset,
    ModePolicyPreset,
)
from .profile_presets import frame_fit_profile, separator_edge_pair_profile


def _detector_kind(spec: FormatPhysicalSpec, strip_mode: str) -> str:
    if spec.physical_layout == "dual_lane" and strip_mode == FULL:
        return "dual_lane"
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def _review_only(
    spec: FormatPhysicalSpec,
    strip_mode: str,
) -> ReviewOnlyPolicy | None:
    if spec.physical_layout == "dual_lane" and strip_mode == PARTIAL:
        return ReviewOnlyPolicy(
            reason="dual_lane_partial_not_supported",
        )
    return None


def mode_policy_preset(spec: FormatPhysicalSpec, strip_mode: str) -> ModePolicyPreset:
    return ModePolicyPreset(
        detector_kind=_detector_kind(spec, strip_mode),
        frame_fit=frame_fit_profile(spec.frame_geometry_profile, strip_mode),
        review_only=_review_only(spec, strip_mode),
    )


def format_policy_preset(
    spec: FormatPhysicalSpec,
    parameters: FormatParameters,
) -> FormatPolicyPreset:
    return FormatPolicyPreset(
        format_spec=spec,
        parameters=parameters,
        separator_edge_pair=separator_edge_pair_profile(spec.frame_geometry_profile),
        modes={
            FULL: mode_policy_preset(spec, FULL),
            PARTIAL: mode_policy_preset(spec, PARTIAL),
        },
    )


def build_policy_from_format(
    spec: FormatPhysicalSpec,
    parameters: FormatParameters,
    strip_mode: str,
):
    return build_policy_from_preset(format_policy_preset(spec, parameters), strip_mode)
