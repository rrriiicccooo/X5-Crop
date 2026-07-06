from __future__ import annotations

from ..separator_gate_profiles import SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD
from ..runtime.base import FULL, PARTIAL, FrameFitPolicy
from ..runtime.separator import SeparatorEdgePairPolicy
from ..assembly.factory import build_policy_from_preset
from ..assembly.presets import FormatPolicyPreset, ModePolicyPreset, SeparatorWidthProfilePreset
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_medium_format_parameters

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
        separator_width_profile_enabled=True,
        separator_width_profile_max_width_ratio=0.140,
        separator_width_profile_min_mean=0.90,
        separator_width_profile_min_prominence=0.015,
        separator_gate_edge_pair_min_score_without_broad_width=1.0,
        separator_gate_edge_pair_min_score_with_broad_width=0.0,
        separator_gate_min_broad_separator_width_gaps_for_auto=0,
        partial_safe_extra_frames_min_broad_separator_width_gaps=2,
        partial_safe_extra_frames_leading_content_check=True,
        partial_safe_extra_frames_frame_content_check=True,
        short_axis_geometry_correction_min_error=0.24,
        partial_edge_ratio_extras=(0.06, 0.10),
        partial_edge_max_candidates=6,
        separator_full_width_outer_max_candidates=8,
        separator_full_width_outer_margin_ratios=(0.00, 0.018, 0.035, 0.055),
        separator_full_width_outer_source_candidates=3,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile=SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD,
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    ),
    modes={
        FULL: ModePolicyPreset(
            role="square_full_strip_separator_width_profile_guarded",
            notes=(
                "width-aware separator evidence may use broad observed bands, but full mode does not inherit partial extra-holder tolerance",
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
            separator_width_profile=SeparatorWidthProfilePreset(
                mode="conditional",
                full_selection_enabled=True,
                separator_outer_allow_oversized_band=True,
            ),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="square_partial_strip_separator_width_profile_edge_guarded",
            notes=(
                "width-aware separator evidence must still pass separator/content/geometry gates",
                "safe extra holder frames require broad separator width evidence and stable frame content",
            ),
            separator_width_profile=SeparatorWidthProfilePreset(
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
