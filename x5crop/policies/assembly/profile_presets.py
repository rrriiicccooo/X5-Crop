from __future__ import annotations

from ...geometry.detection_parameters import EdgePairParameters
from ..runtime.base import FULL, FrameFitPolicy


def separator_edge_pair_profile(profile: str) -> EdgePairParameters:
    medium_square_like = EdgePairParameters(
        window_ratio=0.100,
        min_gutter_ratio=0.001,
        max_gutter_ratio=0.080,
        min_strength=0.24,
        min_background=0.02,
        min_quality_for_model_gap=0.28,
        min_quality_for_hard_gap=0.30,
        hard_gap_quality_ratio=0.95,
        max_hard_shift_ratio=0.030,
    )
    profiles = {
        "standard_35mm": EdgePairParameters(
            window_ratio=0.080,
            min_gutter_ratio=0.004,
            max_gutter_ratio=0.050,
            min_strength=0.42,
            min_background=0.62,
            min_quality_for_model_gap=0.0,
            min_quality_for_hard_gap=0.0,
            hard_gap_quality_ratio=1.0,
            max_hard_shift_ratio=0.0,
        ),
        "dense_half": EdgePairParameters(
            window_ratio=0.090,
            min_gutter_ratio=0.003,
            max_gutter_ratio=0.060,
            min_strength=0.46,
            min_background=0.66,
            min_quality_for_model_gap=1.05,
            min_quality_for_hard_gap=0.70,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.040,
        ),
        "panoramic_35mm": EdgePairParameters(
            window_ratio=0.060,
            min_gutter_ratio=0.002,
            max_gutter_ratio=0.035,
            min_strength=0.45,
            min_background=0.64,
            min_quality_for_model_gap=1.03,
            min_quality_for_hard_gap=0.70,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.035,
        ),
        "medium_rectangle": EdgePairParameters(
            window_ratio=0.075,
            min_gutter_ratio=0.001,
            max_gutter_ratio=0.055,
            min_strength=0.32,
            min_background=0.20,
            min_quality_for_model_gap=0.58,
            min_quality_for_hard_gap=0.50,
            hard_gap_quality_ratio=0.95,
            max_hard_shift_ratio=0.035,
        ),
        "medium_square": medium_square_like,
        "medium_wide": medium_square_like,
        "dual_lane": EdgePairParameters(
            window_ratio=0.080,
            min_gutter_ratio=0.004,
            max_gutter_ratio=0.050,
            min_strength=0.42,
            min_background=0.62,
            min_quality_for_model_gap=0.0,
            min_quality_for_hard_gap=0.0,
            hard_gap_quality_ratio=1.0,
            max_hard_shift_ratio=0.0,
        ),
    }
    return profiles[profile]


def frame_fit_profile(profile: str, strip_mode: str) -> FrameFitPolicy | None:
    if strip_mode != FULL:
        return None
    profiles = {
        "standard_35mm": FrameFitPolicy(
            name="standard_strip_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.72,
            nominal_max_ratio=1.10,
            inlier_tolerance_ratio=0.035,
        ),
        "dual_lane": FrameFitPolicy(
            name="dual_lane_frame_fit",
            edge_evidence=False,
            geometry_fallback=True,
        ),
        "dense_half": FrameFitPolicy(
            name="dense_half_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=4,
            nominal_min_ratio=0.78,
            nominal_max_ratio=1.08,
            inlier_tolerance_ratio=0.030,
        ),
        "panoramic_35mm": FrameFitPolicy(
            name="panoramic_strip_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.12,
            inlier_tolerance_ratio=0.035,
        ),
        "medium_rectangle": FrameFitPolicy(
            name="medium_rectangle_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.70,
            nominal_max_ratio=1.15,
            inlier_tolerance_ratio=0.040,
        ),
        "medium_square": FrameFitPolicy(
            name="medium_square_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.65,
            nominal_max_ratio=1.20,
            inlier_tolerance_ratio=0.045,
        ),
        "medium_wide": FrameFitPolicy(
            name="medium_wide_frame_fit",
            edge_evidence=True,
            geometry_fallback=True,
            min_edge_samples=2,
            nominal_min_ratio=0.65,
            nominal_max_ratio=1.20,
            inlier_tolerance_ratio=0.045,
        ),
    }
    return profiles[profile]
