from __future__ import annotations

from dataclasses import dataclass

from ..parameters.finalization import ApprovedGeometryAdjustmentParameters


@dataclass(frozen=True)
class FinalizationPolicy:
    approved_geometry_adjustment: ApprovedGeometryAdjustmentParameters
