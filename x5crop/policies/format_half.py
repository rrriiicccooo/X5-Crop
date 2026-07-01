from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import FormatPolicyPreset, ModePolicyPreset, build_policy_from_preset

FORMAT_ID = "half"

FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    separator_gate_profile="geometry_support",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.090, 0.003, 0.060, 0.46, 0.66, 1.05, 0.70, 0.95, 0.040
    ),
    content_mismatch_review_enabled=True,
    modes={
        FULL: ModePolicyPreset(
            role="dense_full_strip_geometry_supported",
            notes=("dense full strips can use stable grid or wide geometry support without borrowing dark-boundary gates",),
            frame_fit=FrameFitPolicy(
                name="half",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=4,
                nominal_min_ratio=0.78,
                nominal_max_ratio=1.08,
                inlier_tolerance_ratio=0.030,
            ),
            separator_geometry_support_modes=("wide_geometry", "stable_grid"),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="dense_partial_strip_edge_guarded",
            notes=("partial safe extra frames require explicit separator/content/geometry support",),
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
