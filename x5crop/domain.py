from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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

@dataclass(frozen=True)
class MeasurementProvenance:
    root_measurement: str
    source: str
    dependencies: tuple[str, ...]
    boundary_anchors: tuple[str, ...] = ()


class EvidenceState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, order=True)
class PixelInterval:
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.maximum < self.minimum:
            raise ValueError("pixel interval maximum must not be below minimum")

    @classmethod
    def exact(cls, value: float) -> "PixelInterval":
        return cls(float(value), float(value))

    @classmethod
    def zero(cls) -> "PixelInterval":
        return cls.exact(0.0)

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.minimum + self.maximum)

    def intersects(self, other: "PixelInterval") -> bool:
        return max(self.minimum, other.minimum) <= min(self.maximum, other.maximum)

    def plus(self, other: "PixelInterval") -> "PixelInterval":
        return PixelInterval(
            self.minimum + other.minimum,
            self.maximum + other.maximum,
        )

    def minus(self, other: "PixelInterval") -> "PixelInterval":
        return PixelInterval(
            self.minimum - other.maximum,
            self.maximum - other.minimum,
        )

    def scaled(self, factor: float) -> "PixelInterval":
        low = self.minimum * float(factor)
        high = self.maximum * float(factor)
        return PixelInterval(min(low, high), max(low, high))


@dataclass(frozen=True)
class FrameDimensionPrior:
    width_px: PixelInterval
    height_px: PixelInterval
    frame_size_options_mm: tuple[tuple[float, float], ...]
    source: str
    provenance: MeasurementProvenance


@dataclass(frozen=True)
class BoundaryPositionConstraint:
    boundary_index: int
    position: PixelInterval
    provenance: MeasurementProvenance


@dataclass(frozen=True)
class SeparatorWidthConstraint:
    boundary_index: int
    width: PixelInterval
    provenance: MeasurementProvenance


def sum_pixel_intervals(intervals: tuple[PixelInterval, ...]) -> PixelInterval:
    return PixelInterval(
        sum(interval.minimum for interval in intervals),
        sum(interval.maximum for interval in intervals),
    )


@dataclass(frozen=True)
class HolderSpan:
    box: Box


@dataclass(frozen=True)
class VisibleSequenceSpan:
    box: Box


@dataclass(frozen=True)
class CropEnvelope:
    box: Box


@dataclass(frozen=True)
class SequenceHypothesis:
    name: str
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    strategy: str
    provenance: MeasurementProvenance
    boundary_observations: tuple["BoundaryObservation", ...]


BOUNDARY_SIDES = frozenset({"leading", "trailing", "top", "bottom"})
BOUNDARY_KINDS = frozenset(
    {
        "white_holder_transition",
        "tonal_transition",
        "texture_transition",
        "canvas_clip",
    }
)


@dataclass(frozen=True)
class BoundaryObservation:
    side: str
    position: PixelInterval
    kind: str
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.side not in BOUNDARY_SIDES:
            raise ValueError(f"unsupported boundary side: {self.side}")
        if self.kind not in BOUNDARY_KINDS:
            raise ValueError(f"unsupported boundary kind: {self.kind}")


@dataclass(frozen=True)
class SeparatorBandObservation:
    start: float
    end: float
    center: float
    tonal_evidence: float
    provenance: MeasurementProvenance
    lane_box: Box | None = None
    continuity: float | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("separator observation must have positive width")
        if not self.start <= self.center <= self.end:
            raise ValueError("separator center must lie inside its observed band")

    @property
    def width(self) -> float:
        return float(self.end) - float(self.start)

    @property
    def interval(self) -> PixelInterval:
        return PixelInterval(float(self.start), float(self.end))


@dataclass(frozen=True)
class SeparatorAssignment:
    boundary_index: int
    observation: SeparatorBandObservation
    position_constraint: BoundaryPositionConstraint
    width_constraint: SeparatorWidthConstraint
    state: EvidenceState
    geometry_dependent: bool
    used_for_boundary: bool
    reason: str

    @property
    def independent(self) -> bool:
        return self.state == EvidenceState.SUPPORTED and not self.geometry_dependent


@dataclass(frozen=True)
class DimensionConstrainedBoundary:
    boundary_index: int
    position: PixelInterval
    provenance: MeasurementProvenance
    focused_observation: SeparatorBandObservation | None = None


@dataclass(frozen=True)
class FrameBoundary:
    boundary_index: int
    position: PixelInterval
    source: str
    provenance: MeasurementProvenance
    assignment: SeparatorAssignment | None = None
    dimension_constraint: DimensionConstrainedBoundary | None = None

    def __post_init__(self) -> None:
        if self.source not in {"observed_separator", "dimension_constrained"}:
            raise ValueError(f"unsupported frame boundary source: {self.source}")

    @property
    def coordinate(self) -> float:
        return self.position.midpoint

    @property
    def hard_separator(self) -> bool:
        return bool(
            self.source == "observed_separator"
            and self.assignment is not None
            and self.assignment.independent
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

    def __post_init__(self) -> None:
        if self.long_axis < 0 or self.short_axis < 0:
            raise ValueError("output bleed must be non-negative")


@dataclass(frozen=True)
class ProcessResult:
    record: dict[str, Any]
