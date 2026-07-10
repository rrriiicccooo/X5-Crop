from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExposureOverlapEvidencePolicy:
    model_gap_window_ratio: float
    model_gap_window_min_px: int
    model_gap_window_max_px: int
    mean_min: float
    weak_continuity: float
    weak_activity: float
    medium_continuity: float
    medium_activity: float
    strong_continuity: float
    strong_activity: float
