from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.final import (
    ApprovedGeometryAdjustmentPolicy,
    FinalizationPolicy,
)


def finalization_policy(params: FormatParameters) -> FinalizationPolicy:
    approved_adjustment = params.output.approved_geometry_adjustment
    return FinalizationPolicy(
        apply_approved_geometry_adjustment=True,
        approved_geometry_adjustment=ApprovedGeometryAdjustmentPolicy(
            long_limit_ratio=float(approved_adjustment.long_limit_ratio),
            long_limit_min=int(approved_adjustment.long_limit_min),
            long_limit_max=int(approved_adjustment.long_limit_max),
            min_ext_ratio=float(approved_adjustment.min_ext_ratio),
            min_ext_min=int(approved_adjustment.min_ext_min),
            min_ext_max=int(approved_adjustment.min_ext_max),
            side_band_trim_ratio=float(approved_adjustment.side_band_trim_ratio),
            content_threshold_u8=int(approved_adjustment.content_threshold_u8),
            min_active_column_fraction=float(approved_adjustment.min_active_column_fraction),
        ),
    )
