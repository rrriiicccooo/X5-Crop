from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EdgeBleedProtectionPolicy:
    enabled: bool = True
    guard_ratio: float = 0.0150
    guard_min: float = 70.0
    guard_max: float = 120.0


@dataclass(frozen=True)
class OutputPolicy:
    apply_output_bleed: bool = True
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    output_long_axis_bleed_default: int = 20
    output_short_axis_bleed_default: int = 10
    output_overlap_long_axis_bleed: int = 50
    edge_bleed_protection: EdgeBleedProtectionPolicy = field(default_factory=EdgeBleedProtectionPolicy)


__all__ = [
    "EdgeBleedProtectionPolicy",
    "OutputPolicy",
]
