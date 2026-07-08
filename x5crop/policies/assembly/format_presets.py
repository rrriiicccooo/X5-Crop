from __future__ import annotations

from collections.abc import Callable

from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL, FrameFitPolicy, ReviewOnlyPolicy
from ..runtime.separator import SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .presets import (
    FormatPolicyPreset,
    ModePolicyPreset,
    SeparatorWidthProfilePreset,
)


ParameterFactory = Callable[[], FormatParameters]


def _separator_edge_pair(format_id: str) -> SeparatorEdgePairPolicy:
    medium_square_like = SeparatorEdgePairPolicy(
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    )
    presets = {
        "135": SeparatorEdgePairPolicy(
            0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
        ),
        "135-dual": SeparatorEdgePairPolicy(
            0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
        ),
        "half": SeparatorEdgePairPolicy(
            0.090, 0.003, 0.060, 0.46, 0.66, 1.05, 0.70, 0.95, 0.040
        ),
        "xpan": SeparatorEdgePairPolicy(
            0.060, 0.002, 0.035, 0.45, 0.64, 1.03, 0.70, 0.95, 0.035
        ),
        "120-645": SeparatorEdgePairPolicy(
            0.075, 0.001, 0.055, 0.32, 0.20, 0.58, 0.50, 0.95, 0.035
        ),
        "120-66": medium_square_like,
        "120-67": medium_square_like,
    }
    return presets[format_id]


def _frame_fit(format_id: str, strip_mode: str) -> FrameFitPolicy | None:
    if strip_mode != FULL:
        return None
    full_presets = {
        "135": FrameFitPolicy(
            name="standard_strip_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.72,
            nominal_max_ratio=1.10,
            inlier_tolerance_ratio=0.035,
        ),
        "135-dual": FrameFitPolicy(
            name="dual_lane_frame_fit",
            edge_evidence=False,
            geometry_fallback=True,
        ),
        "half": FrameFitPolicy(
            name="dense_half_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=4,
            nominal_min_ratio=0.78,
            nominal_max_ratio=1.08,
            inlier_tolerance_ratio=0.030,
        ),
        "xpan": FrameFitPolicy(
            name="panoramic_strip_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.12,
            inlier_tolerance_ratio=0.035,
        ),
        "120-645": FrameFitPolicy(
            name="medium_rectangle_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.15,
            inlier_tolerance_ratio=0.040,
        ),
        "120-66": FrameFitPolicy(
            name="medium_square_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.65,
            nominal_max_ratio=1.20,
            inlier_tolerance_ratio=0.045,
        ),
        "120-67": FrameFitPolicy(
            name="medium_wide_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.65,
            nominal_max_ratio=1.20,
            inlier_tolerance_ratio=0.045,
        ),
    }
    return full_presets[format_id]


def _role(format_id: str, strip_mode: str) -> str:
    roles = {
        ("135", FULL): "full_strip_balanced_separator_geometry",
        ("135", PARTIAL): "partial_strip_edge_uncertainty_guarded",
        ("135-dual", FULL): "two_lane_full_strip_isolated",
        ("135-dual", PARTIAL): "two_lane_partial_review_only",
        ("half", FULL): "dense_full_strip_geometry_supported",
        ("half", PARTIAL): "dense_partial_strip_edge_guarded",
        ("xpan", FULL): "panoramic_full_strip_separator_guarded",
        ("xpan", PARTIAL): "panoramic_partial_strip_edge_guarded",
        ("120-645", FULL): "medium_format_full_strip_separator_guarded",
        ("120-645", PARTIAL): "medium_format_partial_strip_edge_guarded",
        ("120-66", FULL): "square_full_strip_separator_width_profile_guarded",
        ("120-66", PARTIAL): "square_partial_strip_separator_width_profile_edge_guarded",
        ("120-67", FULL): "wide_medium_format_full_separator_guarded",
        ("120-67", PARTIAL): "wide_medium_format_partial_edge_guarded",
    }
    return roles[(format_id, strip_mode)]


def _notes(format_id: str, strip_mode: str) -> tuple[str, ...]:
    notes = {
        ("135", FULL): (
            "full strips require combined separator, geometry, content, and outer evidence",
        ),
        ("135", PARTIAL): (
            "partial strips require explicit edge trust before automatic export",
        ),
        ("135-dual", FULL): (
            "dual-lane detection is intentionally separate from normal strip policies",
        ),
        ("135-dual", PARTIAL): (
            "partial two-lane scans stay review-only until real samples define a policy",
        ),
        ("half", FULL): (
            "dense full strips can use stable grid or detected geometry support without borrowing medium-format holder gates",
        ),
        ("half", PARTIAL): (
            "partial safe extra frames require explicit separator/content/geometry support",
        ),
        ("xpan", FULL): (
            "panoramic full strips remain conservative and separator-driven",
        ),
        ("xpan", PARTIAL): (
            "partial panoramic strips may include the default count but still need separator/content/geometry gates",
        ),
        ("120-645", FULL): (
            "medium-format full strips use separator policy without square holder gates",
        ),
        ("120-645", PARTIAL): (
            "medium-format partial strips use conservative partial edge policy",
        ),
        ("120-66", FULL): (
            "width-aware separator evidence may use measured-width bands, including broad bands, but full mode does not inherit partial extra-holder tolerance",
        ),
        ("120-66", PARTIAL): (
            "width-aware separator evidence must still pass separator/content/geometry gates",
            "safe extra holder frames require broad separator width evidence and stable frame content",
        ),
        ("120-67", FULL): (
            "wide medium-format full strips can use width-aware separator evidence and tight short-axis correction",
        ),
        ("120-67", PARTIAL): (
            "wide medium-format partial strips use shared partial policy without square holder gates",
        ),
    }
    return notes[(format_id, strip_mode)]


def _detector_kind(format_id: str, strip_mode: str) -> str:
    if format_id == "135-dual" and strip_mode == FULL:
        return "dual_lane"
    if format_id == "135-dual" and strip_mode == PARTIAL:
        return "review_only"
    return "standard_strip"


def _review_only(format_id: str, strip_mode: str) -> ReviewOnlyPolicy:
    if format_id == "135-dual" and strip_mode == PARTIAL:
        return ReviewOnlyPolicy(
            reason="dual_lane_partial_not_supported",
            selection_override="dual_lane_partial_review_only",
        )
    return ReviewOnlyPolicy()


def _separator_width_profile(format_id: str) -> SeparatorWidthProfilePreset:
    if format_id == "120-66":
        return SeparatorWidthProfilePreset(
            mode="conditional",
            separator_outer_allow_oversized_band=True,
        )
    return SeparatorWidthProfilePreset()


def _separator_geometry_support_modes(format_id: str, strip_mode: str) -> tuple[str, ...]:
    if format_id == "half" and strip_mode == FULL:
        return ("detected_geometry", "stable_grid")
    return ()


def _output_overlap_enabled(format_id: str, strip_mode: str) -> bool:
    if strip_mode == PARTIAL:
        return True
    return format_id in {"half", "120-645", "120-66", "120-67"}


def _content_mismatch_candidate_selection_enabled(format_id: str) -> bool:
    return format_id == "half"


def mode_policy_preset(format_id: str, strip_mode: str) -> ModePolicyPreset:
    return ModePolicyPreset(
        role=_role(format_id, strip_mode),
        notes=_notes(format_id, strip_mode),
        detector_kind=_detector_kind(format_id, strip_mode),
        frame_fit=_frame_fit(format_id, strip_mode),
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
        separator_edge_pair=_separator_edge_pair(format_id),
        content_mismatch_candidate_selection_enabled=(
            _content_mismatch_candidate_selection_enabled(format_id)
        ),
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
