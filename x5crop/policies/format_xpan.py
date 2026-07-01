from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "xpan"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.060, 0.002, 0.035, 0.45, 0.64, 1.03, 0.70, 0.95, 0.035
    ),
    modes={
        FULL: ModePolicyPreset(
            role="panoramic_full_strip_separator_guarded",
            notes=("panoramic full strips remain conservative and separator-driven",),
            frame_fit=FrameFitPolicy(
                name="xpan",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=2,
                nominal_min_ratio=0.70,
                nominal_max_ratio=1.12,
                inlier_tolerance_ratio=0.035,
            ),
        ),
        PARTIAL: ModePolicyPreset(
            role="panoramic_partial_strip_edge_guarded",
            notes=("partial panoramic strips may include the default count but still need separator/content/geometry gates",),
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
