from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.output import ExposureOverlapProtectionPolicy, OutputPolicy


def output_policy(params: FormatParameters) -> OutputPolicy:
    protection = params.output.exposure_overlap_protection
    return OutputPolicy(
        exposure_overlap_protection=ExposureOverlapProtectionPolicy(
            enabled=bool(protection.enabled),
            required_bleed_window_fraction=float(
                protection.required_bleed_window_fraction
            ),
            required_bleed_padding_px=int(protection.required_bleed_padding_px),
            required_bleed_min_px=int(protection.required_bleed_min_px),
            long_axis_bleed_capacity_px=int(protection.long_axis_bleed_capacity_px),
        )
    )


__all__ = [
    "output_policy",
]
