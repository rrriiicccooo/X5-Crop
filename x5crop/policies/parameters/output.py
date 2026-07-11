from __future__ import annotations

from dataclasses import dataclass, field

from ...units import PhysicalLength


@dataclass(frozen=True)
class OverlapBleedParameters:
    required_bleed_window_fraction: float = 0.5
    required_bleed_padding_px: int = 0
    required_bleed_min_px: int = 1
    long_axis_bleed_capacity: PhysicalLength = field(
        default_factory=lambda: PhysicalLength(
            mm=0.55,
            fallback_ratio=0.02,
            min_px=50,
            max_px=240,
        )
    )
