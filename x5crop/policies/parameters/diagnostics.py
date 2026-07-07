from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugGapOverlayParameters:
    overlap_tolerance_ratio: float
    overlap_tolerance_min: float
    overlap_tolerance_max: float
    tick_length_ratio: float
    tick_length_min: int
    hard_line_width: int
    model_line_width: int
    diagnostic_line_width: int


@dataclass(frozen=True)
class NearbySeparatorDiagnosticsParameters:
    window_ratio: float
    window_min: int
    window_max: int
    exclude_ratio: float
    exclude_min: int
    exclude_max: int
    max_width_ratio: float
    max_width_min: int
    max_width_max: int
    detail_score_add: float
    detail_score_multiplier: float

__all__ = [
    "DebugGapOverlayParameters",
    "NearbySeparatorDiagnosticsParameters",
]
