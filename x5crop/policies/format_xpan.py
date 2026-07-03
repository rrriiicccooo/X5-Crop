from __future__ import annotations

from .runtime_base import FULL, PARTIAL, FrameFitPolicy
from .runtime_separator import SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameter_aggregate import FormatParameters

FORMAT_ID = "xpan"


def parameters() -> FormatParameters:
    return FormatParameters(
        FORMAT_ID,
        outer_align_long_margin_ratio=0.008,
        outer_align_long_margin_cap_ratio=0.012,
        content_profile_min_run_ratio=0.24,
        separator_model_grid_credit=0.20,
        separator_model_equal_credit=0.06,
        separator_gate_profile="all_internal_gaps_hard",
        relaxed_separator_width_retry_enabled=False,
        partial_auto_include_default_count=True,
        separator_local_partial_mode="always",
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        separator_local_outer_enabled=True,
        separator_outer_min_score=0.66,
        separator_outer_band_score=0.44,
        separator_outer_spacing_min_ratio=0.86,
        separator_outer_spacing_max_ratio=1.16,
        separator_outer_frame_error_max=0.10,
        separator_outer_max_width_ratio=0.045,
        separator_outer_gap_max_width_ratio=0.060,
        separator_outer_source_candidates=1,
        separator_outer_band_candidates=8,
        separator_outer_pair_candidates=3,
        separator_outer_max_candidates=4,
        partial_edge_ratio_extras=(0.03, 0.06),
        partial_edge_max_candidates=4,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile="all_internal_gaps_hard",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.060, 0.002, 0.035, 0.45, 0.64, 1.03, 0.70, 0.95, 0.035
    ),
    modes={
        FULL: ModePolicyPreset(
            role="panoramic_full_strip_separator_guarded",
            notes=("panoramic full strips remain conservative and separator-driven",),
            frame_fit=FrameFitPolicy(
                name="panoramic_strip_frame_fit",
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
