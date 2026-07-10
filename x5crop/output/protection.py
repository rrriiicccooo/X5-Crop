from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Protocol


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int


DEFAULT_OUTPUT_BLEED = AxisBleedParameters(long_axis=20, short_axis=10)


class ExposureOverlapProtectionPolicyLike(Protocol):
    required_bleed_window_fraction: float
    required_bleed_padding_px: int
    required_bleed_min_px: int
    long_axis_bleed_capacity_px: int


class OutputProtectionPolicyLike(Protocol):
    apply_output_bleed: bool
    exposure_overlap_protection: ExposureOverlapProtectionPolicyLike


@dataclass(frozen=True)
class OutputProtectionPlan:
    base_bleed: AxisBleedParameters
    output_bleed: AxisBleedParameters
    exposure_overlap_detected: bool
    required_long_axis_bleed_px: int
    available_long_axis_bleed_px: int
    feasible: bool
    reason: str

    def report_detail(self) -> dict[str, Any]:
        return {
            "base_long_axis_bleed_px": int(self.base_bleed.long_axis),
            "base_short_axis_bleed_px": int(self.base_bleed.short_axis),
            "output_long_axis_bleed_px": int(self.output_bleed.long_axis),
            "output_short_axis_bleed_px": int(self.output_bleed.short_axis),
            "exposure_overlap_detected": bool(self.exposure_overlap_detected),
            "required_long_axis_bleed_px": int(self.required_long_axis_bleed_px),
            "available_long_axis_bleed_px": int(self.available_long_axis_bleed_px),
            "feasible": bool(self.feasible),
            "reason": self.reason,
        }


def output_protection_plan(
    exposure_overlap_evidence: dict[str, Any],
    base_bleed: AxisBleedParameters,
    policy: OutputProtectionPolicyLike,
) -> OutputProtectionPlan:
    protection = policy.exposure_overlap_protection
    detected = bool(exposure_overlap_evidence.get("exposure_overlap_detected", False))
    widest_band = max(
        0.0,
        float(exposure_overlap_evidence.get("widest_overlap_band_px", 0.0) or 0.0),
    )
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
        int(protection.long_axis_bleed_capacity_px),
    )
    protection_enabled = bool(policy.apply_output_bleed)
    feasible = bool(not detected or (protection_enabled and required <= available))
    if not detected:
        reason = "no_exposure_overlap"
        output_long_axis = int(base_bleed.long_axis)
    elif not protection_enabled:
        reason = "output_bleed_disabled"
        output_long_axis = int(base_bleed.long_axis)
    elif feasible:
        reason = "exposure_overlap_protection_planned"
        output_long_axis = max(int(base_bleed.long_axis), required)
    else:
        reason = "exposure_overlap_exceeds_bleed_capacity"
        output_long_axis = available
    return OutputProtectionPlan(
        base_bleed=base_bleed,
        output_bleed=AxisBleedParameters(
            long_axis=output_long_axis,
            short_axis=int(base_bleed.short_axis),
        ),
        exposure_overlap_detected=detected,
        required_long_axis_bleed_px=required,
        available_long_axis_bleed_px=available,
        feasible=feasible,
        reason=reason,
    )


__all__ = [
    "AxisBleedParameters",
    "DEFAULT_OUTPUT_BLEED",
    "OutputProtectionPlan",
    "output_protection_plan",
]
