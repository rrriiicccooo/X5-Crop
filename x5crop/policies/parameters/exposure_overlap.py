from __future__ import annotations

from dataclasses import dataclass, field

from ...units import PhysicalLength


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
    long_axis_bleed_capacity: PhysicalLength = field(
        default_factory=lambda: PhysicalLength(
            mm=0.55,
            fallback_ratio=0.02,
            min_px=50,
            max_px=240,
        )
    )


@dataclass(frozen=True)
class EdgeBleedProtectionParameters:
    guard: PhysicalLength = field(
        default_factory=lambda: PhysicalLength(
            mm=0.55,
            fallback_ratio=0.015,
            min_px=70,
            max_px=120,
        )
    )
