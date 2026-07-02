from __future__ import annotations

from .runtime_base import FULL, PARTIAL, FrameFitPolicy
from .runtime_separator import SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameter_aggregate import FormatParameters
from .parameter_registry import base_medium_format_parameters

FORMAT_ID = "120-645"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.60,
        separator_first_outer_band_score=0.38,
        separator_first_outer_spacing_min_ratio=0.84,
        separator_first_outer_spacing_max_ratio=1.20,
        separator_first_outer_frame_error_max=0.14,
        separator_first_outer_max_width_ratio=0.090,
        separator_first_outer_gap_max_width_ratio=0.080,
        separator_first_outer_band_candidates=10,
        separator_first_outer_pair_candidates=3,
        separator_first_outer_max_candidates=8,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.04, 0.08),
        long_axis_edge_anchor_max_candidates=4,
    )


FORMAT_POLICY_PRESET = FormatPolicyPreset(
    format_id=FORMAT_ID,
    parameters=parameters,
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
