from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EdgeBleedProtectionPolicy:
    enabled: bool = True
    guard_ratio: float = 0.0150
    guard_min: float = 70.0
    guard_max: float = 120.0


@dataclass(frozen=True)
class ExposureOverlapProtectionPolicy:
    required_bleed_window_fraction: float
    required_bleed_padding_px: int
    required_bleed_min_px: int
    long_axis_bleed_capacity_px: int


@dataclass(frozen=True)
class OutputPolicy:
    exposure_overlap_protection: ExposureOverlapProtectionPolicy
    apply_output_bleed: bool = True
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    edge_bleed_protection: EdgeBleedProtectionPolicy = field(default_factory=EdgeBleedProtectionPolicy)
