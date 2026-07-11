from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class OuterCandidate:
    name: str
    box: Box
    strategy: str = "unknown_outer"
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionCandidate:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    outer: Box
    frames: list[Box]
    gaps: list[SeparatorBandObservation]
    confidence: float
    detail: dict[str, Any]


@dataclass
class FinalDetection(DetectionCandidate):
    status: str
    final_review_reasons: list[str]

    @classmethod
    def from_candidate(
        cls,
        candidate: DetectionCandidate,
        *,
        status: str,
        final_review_reasons: list[str],
    ) -> "FinalDetection":
        return cls(
            format_id=candidate.format_id,
            layout=candidate.layout,
            strip_mode=candidate.strip_mode,
            count=candidate.count,
            outer=candidate.outer,
            frames=deepcopy(candidate.frames),
            gaps=deepcopy(candidate.gaps),
            confidence=candidate.confidence,
            detail=deepcopy(candidate.detail),
            status=status,
            final_review_reasons=list(final_review_reasons),
        )


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


@dataclass(frozen=True)
class ProcessResult:
    record: dict[str, Any]
