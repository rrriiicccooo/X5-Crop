from __future__ import annotations

from .runtime_policy import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameters import FormatParameters

FORMAT_ID = "half"


def parameters() -> FormatParameters:
    return FormatParameters(
        FORMAT_ID,
        score_full_width_cv=0.008,
        content_profile_min_run_ratio=0.16,
        separator_model_grid_credit=0.25,
        separator_model_equal_credit=0.08,
        separator_gate_profile="geometry_support",
        wide_gap_retry_enabled=True,
        wide_gap_retry_max_width_ratio=0.100,
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.68,
        separator_first_outer_band_score=0.48,
        separator_first_outer_spacing_min_ratio=0.90,
        separator_first_outer_spacing_max_ratio=1.12,
        separator_first_outer_frame_error_max=0.08,
        separator_first_outer_max_width_ratio=0.055,
        separator_first_outer_gap_max_width_ratio=0.055,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=14,
        separator_first_outer_pair_candidates=2,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.04, 0.06),
        long_axis_edge_anchor_max_candidates=4,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
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
                name="dense_half_frame_fit",
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
