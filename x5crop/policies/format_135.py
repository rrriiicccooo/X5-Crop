from __future__ import annotations

from .base import FULL, PARTIAL, FrameFitPolicy, SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameters import FormatParameters

FORMAT_ID = "135"


def parameters() -> FormatParameters:
    return FormatParameters(
        FORMAT_ID,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.72,
        separator_first_outer_band_score=0.52,
        separator_first_outer_spacing_min_ratio=0.92,
        separator_first_outer_spacing_max_ratio=1.10,
        separator_first_outer_frame_error_max=0.07,
        separator_first_outer_max_width_ratio=0.050,
        separator_first_outer_gap_max_width_ratio=0.060,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=12,
        separator_first_outer_pair_candidates=2,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.02, 0.04),
        long_axis_edge_anchor_max_candidates=4,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
    separator_gate_profile="min_hard_with_equal_cap",
    separator_edge_pair=SeparatorEdgePairPolicy(
        0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
    ),
    modes={
        FULL: ModePolicyPreset(
            role="full_strip_balanced_separator_geometry",
            notes=("full strips require combined separator, geometry, content, and outer evidence",),
            frame_fit=FrameFitPolicy(
                name="standard_strip_frame_fit",
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
