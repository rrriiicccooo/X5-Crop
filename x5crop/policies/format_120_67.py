from __future__ import annotations

from .runtime_base import FULL, PARTIAL, FrameFitPolicy
from .runtime_separator import SeparatorEdgePairPolicy
from .factory import build_policy_from_preset
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameter_aggregate import FormatParameters
from .parameter_registry import base_medium_format_parameters

FORMAT_ID = "120-67"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        score_outer_too_large=0.995,
        score_outer_too_large_cap=0.86,
        calibrate_hard_full_confidence_floor=0.86,
        wide_gap_retry_enabled=True,
        wide_gap_retry_max_width_ratio=0.090,
        outer_align_short_excess_ratio=0.024,
        outer_align_short_requires_hard_anchors=True,
        outer_align_short_content_height_max=0.970,
        separator_local_outer_enabled=True,
        separator_outer_min_score=0.58,
        separator_outer_band_score=0.36,
        separator_outer_spacing_min_ratio=0.82,
        separator_outer_spacing_max_ratio=1.24,
        separator_outer_frame_error_max=0.18,
        separator_outer_max_width_ratio=0.110,
        separator_outer_gap_max_width_ratio=0.095,
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
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    ),
    modes={
        FULL: ModePolicyPreset(
            role="wide_medium_format_full_separator_guarded",
            notes=("wide medium-format full strips can use wide separator retry and tight short-axis correction",),
            frame_fit=FrameFitPolicy(
                name="medium_wide_frame_fit",
                edge_evidence=True,
                geometry_fallback=True,
                min_edge_samples=2,
                nominal_min_ratio=0.65,
                nominal_max_ratio=1.20,
                inlier_tolerance_ratio=0.045,
            ),
            diagnostics_overlap_bleed=True,
        ),
        PARTIAL: ModePolicyPreset(
            role="wide_medium_format_partial_edge_guarded",
            notes=("wide medium-format partial strips use shared partial policy without square dark-boundary gates",),
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
