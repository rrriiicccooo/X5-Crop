from __future__ import annotations

from ...geometry.detection_parameters import EdgePairParameters
from ..runtime.base import FULL, FrameFitPolicy


def separator_edge_pair_profile(profile: str) -> EdgePairParameters:
    medium_square_like = EdgePairParameters(
        0.100, 0.001, 0.080, 0.24, 0.02, 0.28, 0.30, 0.95, 0.030
    )
    profiles = {
        "standard_35mm": EdgePairParameters(
            0.080, 0.004, 0.050, 0.42, 0.62, 0.0, 0.0, 1.0, 0.0
        ),
        "dense_half": EdgePairParameters(
            0.090, 0.003, 0.060, 0.46, 0.66, 1.05, 0.70, 0.95, 0.040
        ),
        "panoramic_35mm": EdgePairParameters(
            0.060, 0.002, 0.035, 0.45, 0.64, 1.03, 0.70, 0.95, 0.035
        ),
        "medium_rectangle": EdgePairParameters(
            0.075, 0.001, 0.055, 0.32, 0.20, 0.58, 0.50, 0.95, 0.035
        ),
        "medium_square": medium_square_like,
    }
    return profiles[profile]


def frame_fit_profile(profile: str, strip_mode: str) -> FrameFitPolicy | None:
    if strip_mode != FULL:
        return None
    profiles = {
        "standard_strip": FrameFitPolicy(
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


__all__ = ["frame_fit_profile", "separator_edge_pair_profile"]
