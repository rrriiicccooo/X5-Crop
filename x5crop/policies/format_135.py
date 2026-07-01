from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "135"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="min_hard_with_equal_cap",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
    ),
    modes={
        FULL: ModePolicyPreset(
            role="full_strip_balanced_separator_geometry",
            notes=("full strips require combined separator, geometry, content, and outer evidence",),
            frame_fit=FrameFitPolicy(
                name="135",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=2,
                nominal_min_ratio=0.72,
                nominal_max_ratio=1.10,
                inlier_tolerance_ratio=0.035,
            ),
        ),
        PARTIAL: ModePolicyPreset(
            role="partial_strip_edge_uncertainty_guarded",
            notes=("partial strips require explicit edge trust before automatic export",),
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
