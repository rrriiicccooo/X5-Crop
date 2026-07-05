from __future__ import annotations

from ..separator_gate_profiles import SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD
from ..runtime.base import FULL, PARTIAL, FrameFitPolicy, ReviewOnlyPolicy
from ..runtime.separator import SeparatorEdgePairPolicy
from ..assembly.factory import build_policy_from_preset
from ..assembly.presets import FormatPolicyPreset, ModePolicyPreset
from ..parameters.aggregate import FormatParameters

FORMAT_ID = "135-dual"


def parameters() -> FormatParameters:
    return FormatParameters(
        FORMAT_ID,
        separator_gate_profile=SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD,
        separator_width_profile_enabled=False,
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        separator_width_profile_partial_enabled=False,
        partial_safe_extra_frames_enabled=False,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile=SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD,
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
    ),
    modes={
        FULL: ModePolicyPreset(
            role="two_lane_full_strip_isolated",
            notes=("dual-lane detection is intentionally separate from normal strip policies",),
            detector_kind="dual_lane",
            frame_fit=FrameFitPolicy(
                name="dual_lane_frame_fit",
                edge_evidence=False,
                geometry_fallback=True,
            ),
        ),
        PARTIAL: ModePolicyPreset(
            role="two_lane_partial_review_only",
            notes=("partial two-lane scans stay review-only until real samples define a policy",),
            detector_kind="review_only",
            review_only=ReviewOnlyPolicy(
                reason="dual_lane_partial_not_supported",
                selection_override="dual_lane_partial_review_only",
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
