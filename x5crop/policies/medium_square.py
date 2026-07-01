from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import DarkBandModePreset, FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "120-66"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    ),
    modes={
        FULL: ModePolicyPreset(
            role="square_full_strip_dark_boundary_guarded",
            notes=(
                "dark-boundary outer candidates may compete, but full mode does not inherit partial extra-holder tolerance",
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
            dark_band=DarkBandModePreset(
                mode="conditional",
                full_selection_enabled=True,
                separator_outer_allow_oversized_band=True,
            ),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="square_partial_strip_dark_boundary_edge_guarded",
            notes=(
                "dark-boundary outer candidates must still pass separator/content/geometry gates",
                "safe extra holder frames require wide-like separator evidence and stable frame content",
            ),
            dark_band=DarkBandModePreset(
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
