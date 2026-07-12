from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


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

    def __post_init__(self) -> None:
        if not self.root_measurement or not self.source:
            raise ValueError("measurement provenance requires root and source identity")


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
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise ValueError("pixel interval bounds must be finite")
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

    def __post_init__(self) -> None:
        if self.width_px.minimum <= 0.0 or self.height_px.minimum <= 0.0:
            raise ValueError("frame dimension prior must have positive extent")
        if not self.frame_size_options_mm or any(
            width <= 0.0
            or height <= 0.0
            or not math.isfinite(width)
            or not math.isfinite(height)
            for width, height in self.frame_size_options_mm
        ):
            raise ValueError("frame dimension prior requires physical size options")
        if not self.source:
            raise ValueError("frame dimension prior requires a source")


@dataclass(frozen=True)
class BoundaryPositionConstraint:
    boundary_index: int
    position: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("boundary position index must be positive")


@dataclass(frozen=True)
class SeparatorWidthConstraint:
    boundary_index: int
    width: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("separator width index must be positive")
        if self.width.minimum < 0.0:
            raise ValueError("separator width constraint cannot be negative")


def sum_pixel_intervals(intervals: tuple[PixelInterval, ...]) -> PixelInterval:
    return PixelInterval(
        sum(interval.minimum for interval in intervals),
        sum(interval.maximum for interval in intervals),
    )


@dataclass(frozen=True)
class HolderSpan:
    box: Box

    def __post_init__(self) -> None:
        if not self.box.valid():
            raise ValueError("holder span must have positive extent")


@dataclass(frozen=True)
class VisibleSequenceSpan:
    box: Box

    def __post_init__(self) -> None:
        if not self.box.valid():
            raise ValueError("visible sequence span must have positive extent")


@dataclass(frozen=True)
class CropEnvelope:
    box: Box

    def __post_init__(self) -> None:
        if not self.box.valid():
            raise ValueError("crop envelope must have positive extent")


@dataclass(frozen=True)
class SequenceHypothesis:
    name: str
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    strategy: str
    provenance: MeasurementProvenance
    boundary_observations: tuple["BoundaryObservation", ...]

    def __post_init__(self) -> None:
        if not self.name or not self.strategy:
            raise ValueError("sequence hypothesis requires name and strategy")
        visible = self.visible_sequence_span.box
        envelope = self.crop_envelope.box
        if not (
            envelope.left <= visible.left
            and envelope.top <= visible.top
            and envelope.right >= visible.right
            and envelope.bottom >= visible.bottom
        ):
            raise ValueError("crop envelope must contain the visible sequence")


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
class SeparatorCrossAxisMeasurement:
    state: EvidenceState
    coverage_ratio: float | None
    continuity_ratio: float | None
    break_count: int | None
    straightness: float | None
    reason: str

    def __post_init__(self) -> None:
        ratios = tuple(
            value
            for value in (
                self.coverage_ratio,
                self.continuity_ratio,
                self.straightness,
            )
            if value is not None
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("separator cross-axis ratios must lie in [0, 1]")
        if self.break_count is not None and self.break_count < 0:
            raise ValueError("separator cross-axis break count cannot be negative")
        if not self.reason:
            raise ValueError("separator cross-axis measurement requires a reason")


@dataclass(frozen=True)
class SeparatorBandObservation:
    start: float
    end: float
    center: float
    tonal_evidence: float
    provenance: MeasurementProvenance
    cross_axis: SeparatorCrossAxisMeasurement
    lane_box: Box | None = None

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
class FrameBoundaryReference:
    lane_index: int | None
    boundary_index: int

    def __post_init__(self) -> None:
        if self.lane_index is not None and self.lane_index <= 0:
            raise ValueError("frame boundary lane index must be positive")
        if self.boundary_index <= 0:
            raise ValueError("frame boundary index must be positive")


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

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("dimension boundary index must be positive")


@dataclass(frozen=True)
class FrameBoundary:
    boundary_index: int
    position: PixelInterval
    source: str
    provenance: MeasurementProvenance
    assignment: SeparatorAssignment | None = None
    dimension_constraint: DimensionConstrainedBoundary | None = None

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("frame boundary index must be positive")
        if self.source not in {"observed_separator", "dimension_constrained"}:
            raise ValueError(f"unsupported frame boundary source: {self.source}")
        if self.source == "observed_separator":
            if self.assignment is None or self.dimension_constraint is not None:
                raise ValueError("observed frame boundary requires one separator assignment")
            if not self.assignment.used_for_boundary:
                raise ValueError("observed frame boundary assignment must be selected")
        elif self.dimension_constraint is None:
            raise ValueError("dimension frame boundary requires a dimension constraint")
        for item in (self.assignment, self.dimension_constraint):
            if item is not None and item.boundary_index != self.boundary_index:
                raise ValueError("frame boundary components must share one index")

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
