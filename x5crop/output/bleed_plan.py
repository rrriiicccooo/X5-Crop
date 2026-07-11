from __future__ import annotations

from math import ceil
from ..domain import AxisBleedParameters, OutputBleedPlan
from ..policies.parameters.output import OverlapBleedParameters


DEFAULT_OUTPUT_BLEED = AxisBleedParameters(long_axis=20, short_axis=10)


def output_bleed_plan(
    overlap_detected: bool,
    widest_overlap_band_px: float,
    base_bleed: AxisBleedParameters,
    protection: OverlapBleedParameters,
    *,
    long_axis_bleed_capacity_px: int,
) -> OutputBleedPlan:
    detected = bool(overlap_detected)
    widest_band = max(0.0, float(widest_overlap_band_px))
    required = 0
    if detected:
        required = max(
            int(protection.required_bleed_min_px),
            int(
                ceil(
                    widest_band * float(protection.required_bleed_window_fraction)
                    + float(protection.required_bleed_padding_px)
                )
            ),
        )
    available = max(
        int(base_bleed.long_axis),
        int(long_axis_bleed_capacity_px),
    )
    feasible = bool(not detected or required <= available)
    if not detected:
        reason = "no_inter_frame_overlap"
        output_long_axis = int(base_bleed.long_axis)
    elif feasible:
        reason = "inter_frame_overlap_bleed_planned"
        output_long_axis = max(int(base_bleed.long_axis), required)
    else:
        reason = "inter_frame_overlap_exceeds_bleed_capacity"
        output_long_axis = available
    return OutputBleedPlan(
        user_bleed=base_bleed,
        effective_bleed=AxisBleedParameters(
            long_axis=output_long_axis,
            short_axis=int(base_bleed.short_axis),
        ),
        overlap_detected=detected,
        overlap_required_long_axis_bleed_px=required,
        long_axis_bleed_capacity_px=available,
        feasible=feasible,
        reason=reason,
    )
