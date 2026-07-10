from __future__ import annotations

from dataclasses import dataclass, field

from ..parameters.exposure_overlap import ExposureOverlapProtectionParameters


@dataclass(frozen=True)
class EdgeBleedProtectionPolicy:
    guard_ratio: float = 0.0150
    guard_min: float = 70.0
    guard_max: float = 120.0


@dataclass(frozen=True)
class OutputPolicy:
    exposure_overlap_protection: ExposureOverlapProtectionParameters
    edge_bleed_protection: EdgeBleedProtectionPolicy = field(default_factory=EdgeBleedProtectionPolicy)
