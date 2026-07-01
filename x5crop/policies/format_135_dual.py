from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset
from .parameters import FormatParameters

FORMAT_ID = "135-dual"


def parameters() -> FormatParameters:
    return FormatParameters(
        FORMAT_ID,
        separator_gate_profile="all_internal_gaps_hard",
        wide_gap_retry_enabled=False,
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        outer_retry_enabled=False,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_partial_enabled=False,
        separator_first_partial_enabled=False,
        floating_outer_partial_enabled=False,
        wide_gap_retry_partial_enabled=False,
        partial_safe_extra_frames_enabled=False,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
    ),
    modes={
        FULL: ModePolicyPreset(
            role="two_lane_full_strip_isolated",
            notes=("dual-lane detection is intentionally separate from normal strip policies",),
            detector_kind="dual_lane",
            frame_fit=FrameFitPolicy(
                name="parallel_lane_frame_fit",
                edge_evidence=False,
                geometry_fallback=True,
            ),
        ),
        PARTIAL: ModePolicyPreset(
            role="two_lane_partial_review_only",
            notes=("partial two-lane scans stay review-only until real samples define a policy",),
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
