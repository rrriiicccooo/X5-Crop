from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.output import OutputPolicy


def output_policy(params: FormatParameters) -> OutputPolicy:
    return OutputPolicy(
        exposure_overlap_protection=params.output.exposure_overlap_protection,
    )
