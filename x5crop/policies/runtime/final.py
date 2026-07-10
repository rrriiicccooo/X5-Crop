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
    side_band_trim_ratio: float = 0.12
    content_threshold_u8: int = 242
    min_active_column_fraction: float = 0.018


@dataclass(frozen=True)
class FinalizationPolicy:
    apply_approved_geometry_adjustment: bool = True
    approved_geometry_adjustment: ApprovedGeometryAdjustmentPolicy = field(default_factory=ApprovedGeometryAdjustmentPolicy)
