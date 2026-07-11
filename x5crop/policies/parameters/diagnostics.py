from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorOverlayParameters:
    tick_length_ratio: float = 0.12
    tick_length_min: int = 20
    observed_line_width: int = 2
    dimension_line_width: int = 2
    overlap_line_width: int = 3
