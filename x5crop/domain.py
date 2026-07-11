from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def clamp(self, width: int, height: int) -> "Box":
        return Box(
            max(0, min(width, self.left)),
            max(0, min(height, self.top)),
            max(0, min(width, self.right)),
            max(0, min(height, self.bottom)),
        )

    def expand(self, bleed_x: int, bleed_y: int, width: int, height: int) -> "Box":
        return Box(
            self.left - bleed_x,
            self.top - bleed_y,
            self.right + bleed_x,
            self.bottom + bleed_y,
        ).clamp(width, height)


@dataclass(frozen=True)
class MeasurementProvenance:
    root_measurement: str
    source: str
    dependencies: tuple[str, ...]
    boundary_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeparatorBandObservation:
    index: int
    center: float
    score: float
    method: str
    provenance: MeasurementProvenance
    start: Optional[float] = None
    end: Optional[float] = None
    lane_box: Optional[Box] = None
    continuity: Optional[float] = None
    tonal_evidence: Optional[float] = None

    @property
    def width(self) -> float:
        if self.start is None or self.end is None:
            return 0.0
        return max(0.0, float(self.end) - float(self.start))


@dataclass
class ImageProfile:
    shape: tuple[int, ...]
    dtype: str
    axes: str
    photometric: str
    compression: str
    sample_format: Optional[Any]
    bits_per_sample: Optional[Any]
    samples_per_pixel: Optional[int]
    planar_config: Optional[str]
    resolution: Optional[tuple[Any, Any]]
    resolution_unit: Optional[Any]
    icc_profile: Optional[bytes]


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int


@dataclass(frozen=True)
class OutputProtectionPlan:
    base_bleed: AxisBleedParameters
    output_bleed: AxisBleedParameters
    exposure_overlap_detected: bool
    required_long_axis_bleed_px: int
    available_long_axis_bleed_px: int
    feasible: bool
    reason: str

@dataclass(frozen=True)
class ProcessResult:
    record: dict[str, Any]
