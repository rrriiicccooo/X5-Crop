from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "120-645"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.075, 0.001, 0.055, 0.32, 0.20, 0.58, 0.50, 0.95, 0.035
    ),
    modes={
        FULL: ModePolicyPreset(
            role="medium_format_full_strip_separator_guarded",
            notes=("medium-format full strips use separator policy without square dark-boundary gates",),
            frame_fit=FrameFitPolicy(
                name="medium_rectangle_frame_fit",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=2,
                nominal_min_ratio=0.70,
                nominal_max_ratio=1.15,
                inlier_tolerance_ratio=0.040,
            ),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="medium_format_partial_strip_edge_guarded",
            notes=("medium-format partial strips use conservative partial edge policy",),
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
