from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.final import FinalizationPolicy


def finalization_policy(params: FormatParameters) -> FinalizationPolicy:
    return FinalizationPolicy(
        approved_geometry_adjustment=params.output.approved_geometry_adjustment,
    )
