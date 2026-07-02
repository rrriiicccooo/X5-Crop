from __future__ import annotations

from .runtime_base import FULL, PARTIAL, FrameFitPolicy
from .runtime_separator import SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset, WideSeparatorModePreset
from .parameter_aggregate import FormatParameters
from .parameter_registry import base_medium_format_parameters

FORMAT_ID = "120-66"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        score_outer_max_area=1.0,
        score_outer_too_large=1.0,
        score_outer_too_large_cap=0.86,
        calibrate_hard_full_confidence_floor=0.86,
        partial_auto_include_default_count=True,
        gap_max_width_max=720,
        wide_gap_retry_enabled=True,
        wide_gap_retry_max_width_ratio=0.140,
        wide_gap_min_mean=0.90,
        wide_gap_min_prominence=0.015,
        separator_gate_edge_pair_min_score_without_wide=1.0,
        separator_gate_edge_pair_min_score_with_wide=0.0,
        separator_gate_min_wide_gaps_for_auto=0,
        partial_safe_extra_frames_min_wide_like_gaps=2,
        partial_safe_extra_frames_leading_content_check=True,
        partial_safe_extra_frames_frame_content_check=True,
        short_axis_aspect_retry_enabled=True,
        short_axis_aspect_retry_min_error=0.24,
        short_axis_aspect_retry_target_aspect=1.0,
        floating_outer_full_enabled=False,
        floating_outer_partial_enabled=True,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_partial_enabled=True,
        long_axis_edge_anchor_partial_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.06, 0.10),
        long_axis_edge_anchor_max_candidates=6,
        separator_local_outer_enabled=True,
        separator_local_outer_mode="fallback",
        separator_local_partial_enabled=True,
        separator_local_partial_mode="always",
        separator_full_width_outer_partial_mode="conditional",
        separator_full_width_outer_count=3,
        separator_full_width_outer_max_candidates=8,
        separator_full_width_outer_margin_ratios=(0.00, 0.018, 0.035, 0.055),
        separator_full_width_outer_source_candidates=3,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    ),
    modes={
        FULL: ModePolicyPreset(
            role="square_full_strip_wide_separator_guarded",
            notes=(
                "wide-separator outer candidates may compete, but full mode does not inherit partial extra-holder tolerance",
            ),
            frame_fit=FrameFitPolicy(
                name="medium_square_frame_fit",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=2,
                nominal_min_ratio=0.65,
                nominal_max_ratio=1.20,
                inlier_tolerance_ratio=0.045,
            ),
            wide_separator=WideSeparatorModePreset(
                mode="conditional",
                full_selection_enabled=True,
                separator_outer_allow_oversized_band=True,
            ),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="square_partial_strip_wide_separator_edge_guarded",
            notes=(
                "wide-separator outer candidates must still pass separator/content/geometry gates",
                "safe extra holder frames require wide-like separator evidence and stable frame content",
            ),
            wide_separator=WideSeparatorModePreset(
                mode="conditional",
                full_selection_enabled=True,
                separator_outer_allow_oversized_band=True,
            ),
            diagnostics_overlap_bleed=True,
        ),
    },
)


def build_policy(strip_mode: str):
    return build_policy_from_preset(FORMAT_POLICY_PRESET, strip_mode)


def full_policy():
    return build_policy(FULL)


def partial_policy():
    return build_policy(PARTIAL)
