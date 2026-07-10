from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExposureOverlapEvidenceParameters:
    model_gap_window_ratio: float = 0.012
    model_gap_window_min_px: int = 2
    model_gap_window_max_px: int = 80
    mean_min: float = 55.0
    weak_continuity: float = 0.16
    weak_activity: float = 0.04
    medium_continuity: float = 0.35
    medium_activity: float = 0.08
    strong_continuity: float = 0.70
    strong_activity: float = 0.12


@dataclass(frozen=True)
class ExposureOverlapProtectionParameters:
    required_bleed_window_fraction: float = 0.5
    required_bleed_padding_px: int = 0
    required_bleed_min_px: int = 1
    long_axis_bleed_capacity_px: int = 50
