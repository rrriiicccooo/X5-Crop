from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugGapOverlayParameters:
    overlap_tolerance_ratio: float = 0.012
    overlap_tolerance_min: float = 4.0
    overlap_tolerance_max: float = 80.0
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    hard_line_width: int = 2
    model_line_width: int = 2
    diagnostic_line_width: int = 3
