from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "135-dual"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
    ),
    modes={
        FULL: ModePolicyPreset(
            role="dedicated_dual_lane_full_strip",
            notes=("dual-lane detection is intentionally separate from normal strip policies",),
            detector_kind="dual_lane",
            frame_fit=FrameFitPolicy(
                name="135-dual-lane",
                edge_evidence=False,
                geometry_fallback=True,
            ),
        ),
        PARTIAL: ModePolicyPreset(
            role="unsupported_dual_lane_partial",
            notes=("partial dual-lane scans stay review-only until real samples define a policy",),
            detector_kind="review_only",
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
