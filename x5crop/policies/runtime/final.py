from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApprovedGeometryAdjustmentPolicy:
    long_limit_ratio: float = 0.018
    long_limit_min: int = 20
    long_limit_max: int = 60
    min_ext_ratio: float = 0.0100
    min_ext_min: int = 50
    min_ext_max: int = 120


@dataclass(frozen=True)
class FinalizationPolicy:
    apply_output_bleed: bool = True
    apply_approved_geometry_adjustment: bool = True
    approved_geometry_adjustment: ApprovedGeometryAdjustmentPolicy = field(default_factory=ApprovedGeometryAdjustmentPolicy)


@dataclass(frozen=True)
class EdgeBleedProtectionPolicy:
    enabled: bool = True
    guard_ratio: float = 0.0150
    guard_min: float = 70.0
    guard_max: float = 120.0


@dataclass(frozen=True)
class OutputPolicy:
    detection_long_axis_bleed: int = 0
    detection_short_axis_bleed: int = 0
    output_long_axis_bleed_default: int = 20
    output_short_axis_bleed_default: int = 10
    overlap_risk_long_axis_bleed: int = 50
    edge_bleed_protection: EdgeBleedProtectionPolicy = field(default_factory=EdgeBleedProtectionPolicy)


__all__ = [
    "ApprovedGeometryAdjustmentPolicy",
    "EdgeBleedProtectionPolicy",
    "FinalizationPolicy",
    "OutputPolicy",
]
