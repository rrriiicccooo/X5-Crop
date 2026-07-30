from __future__ import annotations

from dataclasses import dataclass
import math

from ..domain import Box
from .grid.model import ProtectedCropEnvelope, SafeCropEnvelope
from .source_core import SourceLaneEvidence


@dataclass(frozen=True)
class OutputProtectionSpec:
    format_id: str
    long_axis_mm_per_side: float
    short_axis_mm_per_side: float

    def __post_init__(self) -> None:
        if (
            not self.format_id
            or self.long_axis_mm_per_side <= 0.0
            or self.short_axis_mm_per_side <= 0.0
        ):
            raise ValueError("output protection requires positive millimetres")


_OUTPUT_PROTECTION_BY_FORMAT = {
    "half": OutputProtectionSpec("half", 0.15, 0.25),
    "135": OutputProtectionSpec("135", 0.25, 0.25),
    "135-dual": OutputProtectionSpec("135-dual", 0.25, 0.25),
    "120-645": OutputProtectionSpec("120-645", 0.30, 0.25),
    "120-66": OutputProtectionSpec("120-66", 0.40, 0.25),
    "xpan": OutputProtectionSpec("xpan", 0.45, 0.25),
    "120-67": OutputProtectionSpec("120-67", 0.50, 0.25),
}


def output_protection_spec(format_id: str) -> OutputProtectionSpec:
    return _OUTPUT_PROTECTION_BY_FORMAT[format_id]


def apply_fixed_output_protection(
    lane: SourceLaneEvidence,
    envelopes: tuple[SafeCropEnvelope, ...],
    protection: OutputProtectionSpec,
) -> tuple[ProtectedCropEnvelope, ...]:
    scales = lane.scan_canvas.axis_scales
    if scales is None:
        raise ValueError("fixed protection requires scan-canvas scale authority")
    long_px = int(
        math.ceil(
            protection.long_axis_mm_per_side
            * scales.long_axis_px_per_mm.maximum
        )
    )
    short_px = int(
        math.ceil(
            protection.short_axis_mm_per_side
            * scales.short_axis_px_per_mm.maximum
        )
    )
    domain = lane.domain.work_box
    protected: list[ProtectedCropEnvelope] = []
    for envelope in envelopes:
        safe = envelope.work_box
        if (
            safe.left < domain.left
            or safe.top < domain.top
            or safe.right > domain.right
            or safe.bottom > domain.bottom
        ):
            raise ValueError(
                "safe envelope exceeds lane authority before protection"
            )
        requested = Box(
            safe.left - long_px,
            safe.top - short_px,
            safe.right + long_px,
            safe.bottom + short_px,
        )
        saturated: list[str] = []
        if requested.left < domain.left:
            saturated.append("left")
        if requested.top < domain.top:
            saturated.append("top")
        if requested.right > domain.right:
            saturated.append("right")
        if requested.bottom > domain.bottom:
            saturated.append("bottom")
        protected.append(
            ProtectedCropEnvelope(
                lane_id=envelope.lane_id,
                lane_ordinal=envelope.lane_ordinal,
                safe_work_box=safe,
                protected_work_box=Box(
                    max(domain.left, requested.left),
                    max(domain.top, requested.top),
                    min(domain.right, requested.right),
                    min(domain.bottom, requested.bottom),
                ),
                saturated_sides=tuple(saturated),
                long_axis_protection_mm=protection.long_axis_mm_per_side,
                short_axis_protection_mm=protection.short_axis_mm_per_side,
            )
        )
    return tuple(protected)
