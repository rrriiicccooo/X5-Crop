from __future__ import annotations

from dataclasses import dataclass, field
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
class WorkspaceExtent:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("workspace extent must have positive dimensions")


class MeasurementIdentity(str, Enum):
    BOUNDARY_PATHS = "boundary_paths"
    BOUNDARY_CORRIDOR = "boundary_corridor"
    CANVAS = "canvas"
    CONTENT_EVIDENCE_IMAGE = "content_evidence_image"
    FORMAT_PHYSICAL_SPEC = "format_physical_spec"
    FRAME_DIMENSIONS = "frame_dimensions"
    FRAME_GEOMETRY = "frame_geometry"
    FRAME_WIDTH_PATTERN = "frame_width_pattern"
    GRAY_WORK = "gray_work"
    IMAGE_MEASUREMENT_STATISTICS = "image_measurement_statistics"
    LANE_DIVIDER_PROFILE = "lane_divider_profile"
    PHYSICAL_FRAME_ASPECT = "physical_frame_aspect"
    PHOTO_EDGES = "photo_edges"
    SEPARATOR_PROFILE = "separator_profile"
    WORKSPACE_TRANSFORM = "workspace_transform"


class ObservationId(str):
    def __new__(cls, value: str) -> "ObservationId":
        if not isinstance(value, str) or not value:
            raise ValueError("observation identity must be a non-empty string")
        return str.__new__(cls, value)


@dataclass(frozen=True)
class MeasurementProvenance:
    root_measurement: MeasurementIdentity
    observation_id: ObservationId
    dependencies: tuple[MeasurementIdentity, ...]
    description: str
    boundary_anchors: tuple[ObservationId, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.root_measurement, MeasurementIdentity):
            raise ValueError("measurement provenance requires a typed root identity")
        if not isinstance(self.observation_id, ObservationId):
            raise ValueError("measurement provenance requires a typed observation identity")
        if not self.description:
            raise ValueError("measurement provenance requires a description")
        if any(
            not isinstance(dependency, MeasurementIdentity)
            for dependency in self.dependencies
        ):
            raise ValueError("measurement dependencies require typed identities")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("measurement dependencies must be unique")
        if self.root_measurement in self.dependencies:
            raise ValueError("measurement provenance cannot depend on its own root")
        if any(
            not isinstance(anchor, ObservationId)
            for anchor in self.boundary_anchors
        ):
            raise ValueError("boundary anchors require typed observation identities")
        if len(set(self.boundary_anchors)) != len(self.boundary_anchors):
            raise ValueError("boundary anchors must be unique")


class EvidenceState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class PhysicalSearchFact(str, Enum):
    SOLUTION_FOUND = "solution_found"
    CONSTRAINTS_CONTRADICTED = "constraints_contradicted"
    MEASUREMENTS_UNAVAILABLE = "measurements_unavailable"
    EXECUTION_BUDGET_EXHAUSTED = "execution_budget_exhausted"


@dataclass(frozen=True)
class PhysicalSearchOutcome:
    facts: tuple[PhysicalSearchFact, ...]

    def __post_init__(self) -> None:
        if not self.facts:
            raise ValueError("physical search outcome requires at least one fact")
        if any(not isinstance(fact, PhysicalSearchFact) for fact in self.facts):
            raise TypeError("physical search facts must be typed")
        if len(set(self.facts)) != len(self.facts):
            raise ValueError("physical search facts must be unique")
        if (
            PhysicalSearchFact.CONSTRAINTS_CONTRADICTED in self.facts
            and len(self.facts) != 1
        ):
            raise ValueError(
                "global physical contradiction cannot coexist with other search facts"
            )
        object.__setattr__(
            self,
            "facts",
            tuple(fact for fact in PhysicalSearchFact if fact in self.facts),
        )

    @property
    def state(self) -> EvidenceState:
        if any(
            fact
            in {
                PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
                PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
            }
            for fact in self.facts
        ):
            return EvidenceState.UNAVAILABLE
        if PhysicalSearchFact.SOLUTION_FOUND in self.facts:
            return EvidenceState.SUPPORTED
        return EvidenceState.CONTRADICTED

    @property
    def budget_exhausted(self) -> bool:
        return PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED in self.facts


def combined_physical_search_outcome(
    outcomes: tuple[PhysicalSearchOutcome, ...],
) -> PhysicalSearchOutcome:
    if not outcomes:
        raise ValueError("physical search outcome aggregation requires inputs")
    observed = {
        fact
        for outcome in outcomes
        for fact in outcome.facts
    }
    facts = tuple(
        fact
        for fact in (
            PhysicalSearchFact.SOLUTION_FOUND,
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
        )
        if fact in observed
    )
    return PhysicalSearchOutcome(
        facts or (PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,)
    )


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

    @staticmethod
    def common_intersection(
        intervals: tuple["PixelInterval", ...],
    ) -> "PixelInterval | None":
        if not intervals:
            raise ValueError("common intersection requires at least one interval")
        shared = intervals[0]
        for interval in intervals[1:]:
            shared = shared.intersection(interval)
            if shared is None:
                return None
        return shared

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.minimum + self.maximum)

    def intersects(self, other: "PixelInterval") -> bool:
        return max(self.minimum, other.minimum) <= min(self.maximum, other.maximum)

    def intersection(self, other: "PixelInterval") -> "PixelInterval | None":
        minimum = max(self.minimum, other.minimum)
        maximum = min(self.maximum, other.maximum)
        return None if maximum < minimum else PixelInterval(minimum, maximum)

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

    def expanded(self, radius: float) -> "PixelInterval":
        radius = float(radius)
        if not math.isfinite(radius) or radius < 0.0:
            raise ValueError("pixel interval expansion must be finite and non-negative")
        return PixelInterval(self.minimum - radius, self.maximum + radius)


@dataclass(frozen=True)
class FrameDimensionPrior:
    frame_size_mm: tuple[float, float]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        width_mm, height_mm = self.frame_size_mm
        if (
            width_mm <= 0.0
            or height_mm <= 0.0
            or not math.isfinite(width_mm)
            or not math.isfinite(height_mm)
        ):
            raise ValueError("frame dimension prior requires a physical size")
        if (
            not isinstance(self.provenance, MeasurementProvenance)
            or self.provenance.root_measurement
            != MeasurementIdentity.PHYSICAL_FRAME_ASPECT
            or MeasurementIdentity.FORMAT_PHYSICAL_SPEC
            not in self.provenance.dependencies
        ):
            raise ValueError(
                "frame dimension prior requires physical-spec aspect provenance"
            )

    @property
    def aspect(self) -> float:
        return float(self.frame_size_mm[0]) / float(self.frame_size_mm[1])


@dataclass(frozen=True)
class FrameCropEnvelope:
    frame_index: int
    box: Box

    def __post_init__(self) -> None:
        if self.frame_index <= 0:
            raise ValueError("frame crop envelope index must be positive")
        if not self.box.valid():
            raise ValueError("frame crop envelope must have positive extent")


@dataclass(frozen=True)
class ContainmentFallback:
    box: Box
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not self.box.valid():
            raise ValueError("containment fallback must have positive extent")


class BoundarySide(str, Enum):
    LEADING = "leading"
    TRAILING = "trailing"
    TOP = "top"
    BOTTOM = "bottom"


class BoundaryAxis(str, Enum):
    LONG = "long_axis"
    SHORT = "short_axis"


def boundary_axis_for_side(side: BoundarySide) -> BoundaryAxis:
    if side in {BoundarySide.LEADING, BoundarySide.TRAILING}:
        return BoundaryAxis.LONG
    if side in {BoundarySide.TOP, BoundarySide.BOTTOM}:
        return BoundaryAxis.SHORT
    raise ValueError(f"unsupported boundary side: {side}")


class BoundaryKind(str, Enum):
    EDGE_ADJACENT_TRANSITION = "edge_adjacent_transition"
    TONAL_TRANSITION = "tonal_transition"
    TEXTURE_TRANSITION = "texture_transition"


class GrayIntensityTail(str, Enum):
    LOW = "low"
    HIGH = "high"
    MIDRANGE = "midrange"


def gray_intensity_tail(
    intensity: float,
    low_reference: float,
    high_reference: float,
) -> GrayIntensityTail:
    values = (float(intensity), float(low_reference), float(high_reference))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("gray intensity tail requires finite measurements")
    if high_reference < low_reference:
        raise ValueError("gray intensity references must be ordered")
    if intensity <= low_reference:
        return GrayIntensityTail.LOW
    if intensity >= high_reference:
        return GrayIntensityTail.HIGH
    return GrayIntensityTail.MIDRANGE


@dataclass(frozen=True)
class GrayAppearanceObservation:
    intensity_median: float
    intensity_mad: float
    texture_median: float
    gradient_median: float
    spatial_continuity: float
    intensity_tail: GrayIntensityTail
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        values = (
            self.intensity_median,
            self.intensity_mad,
            self.texture_median,
            self.gradient_median,
            self.spatial_continuity,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("gray appearance measurements must be finite and non-negative")
        if self.spatial_continuity > 1.0:
            raise ValueError("gray appearance continuity must lie in [0, 1]")
        if not isinstance(self.intensity_tail, GrayIntensityTail):
            raise TypeError("gray appearance requires a typed intensity tail")


@dataclass(frozen=True)
class BoundaryPathSample:
    orthogonal_interval: PixelInterval
    position: PixelInterval

    def __post_init__(self) -> None:
        if (
            self.orthogonal_interval.maximum
            <= self.orthogonal_interval.minimum
        ):
            raise ValueError("boundary path sample requires positive orthogonal extent")


@dataclass(frozen=True)
class BoundaryLineFit:
    slope: float
    intercept: float
    residual: float

    def bounds_within(self, interval: PixelInterval) -> tuple[float, float]:
        predictions = (
            self.intercept + self.slope * interval.minimum,
            self.intercept + self.slope * interval.maximum,
        )
        return (
            min(predictions) - self.residual,
            max(predictions) + self.residual,
        )


def _boundary_path_fit_components(
    samples: tuple[BoundaryPathSample, ...],
) -> tuple[PixelInterval, BoundaryLineFit, BoundaryLineFit]:
    if not samples:
        raise ValueError("boundary path fit requires local samples")
    extent = PixelInterval(
        min(sample.orthogonal_interval.minimum for sample in samples),
        max(sample.orthogonal_interval.maximum for sample in samples),
    )
    if len(samples) == 1:
        position = samples[0].position
        return (
            extent,
            BoundaryLineFit(0.0, position.minimum, 0.0),
            BoundaryLineFit(0.0, position.maximum, 0.0),
        )

    coordinates = tuple(sample.orthogonal_interval.midpoint for sample in samples)
    center = sum(coordinates) / float(len(coordinates))
    denominator = sum((coordinate - center) ** 2 for coordinate in coordinates)
    if denominator <= 0.0:
        return (
            extent,
            BoundaryLineFit(
                0.0,
                min(sample.position.minimum for sample in samples),
                0.0,
            ),
            BoundaryLineFit(
                0.0,
                max(sample.position.maximum for sample in samples),
                0.0,
            ),
        )

    def line_fit(attribute: str) -> BoundaryLineFit:
        values = tuple(
            float(getattr(sample.position, attribute)) for sample in samples
        )
        value_center = sum(values) / float(len(values))
        slope = sum(
            (coordinate - center) * (value - value_center)
            for coordinate, value in zip(coordinates, values, strict=True)
        ) / denominator
        intercept = value_center - slope * center
        residual = max(
            abs(value - (intercept + slope * coordinate))
            for coordinate, value in zip(coordinates, values, strict=True)
        )
        return BoundaryLineFit(slope, intercept, residual)

    return extent, line_fit("minimum"), line_fit("maximum")


@dataclass(frozen=True)
class BoundaryPathFit:
    observation: "GrayBoundaryPathObservation"
    orthogonal_extent: PixelInterval = field(init=False)
    minimum_line: BoundaryLineFit = field(init=False)
    maximum_line: BoundaryLineFit = field(init=False)

    def __post_init__(self) -> None:
        extent, minimum_line, maximum_line = _boundary_path_fit_components(
            self.observation.samples
        )
        object.__setattr__(self, "orthogonal_extent", extent)
        object.__setattr__(self, "minimum_line", minimum_line)
        object.__setattr__(self, "maximum_line", maximum_line)

    @property
    def observation_id(self) -> ObservationId:
        return self.observation.provenance.observation_id

    def position_within(
        self,
        orthogonal_interval: PixelInterval,
    ) -> PixelInterval | None:
        measured_interval = self.orthogonal_extent.intersection(
            orthogonal_interval
        )
        if measured_interval is None:
            return None
        minimum_lower, minimum_upper = self.minimum_line.bounds_within(
            measured_interval
        )
        maximum_lower, maximum_upper = self.maximum_line.bounds_within(
            measured_interval
        )
        return PixelInterval(
            min(minimum_lower, maximum_lower),
            max(minimum_upper, maximum_upper),
        )


def _fitted_path_interval(
    samples: tuple[BoundaryPathSample, ...],
    orthogonal_interval: PixelInterval,
) -> PixelInterval:
    extent, minimum_line, maximum_line = _boundary_path_fit_components(samples)
    measured_interval = extent.intersection(orthogonal_interval)
    if measured_interval is None:
        raise ValueError("boundary path fit interval must overlap its samples")
    minimum_lower, minimum_upper = minimum_line.bounds_within(measured_interval)
    maximum_lower, maximum_upper = maximum_line.bounds_within(measured_interval)
    return PixelInterval(
        min(minimum_lower, maximum_lower),
        max(minimum_upper, maximum_upper),
    )


@dataclass(frozen=True)
class GrayBoundaryPathObservation:
    axis: BoundaryAxis
    kind: BoundaryKind
    samples: tuple[BoundaryPathSample, ...]
    lower_appearance: GrayAppearanceObservation
    upper_appearance: GrayAppearanceObservation
    provenance: MeasurementProvenance
    position: PixelInterval = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.axis, BoundaryAxis):
            raise TypeError("boundary observation requires a typed axis")
        if not isinstance(self.kind, BoundaryKind):
            raise TypeError("boundary observation requires a typed kind")
        if not self.samples:
            raise ValueError("boundary path requires local samples")
        sample_coordinates = tuple(
            sample.orthogonal_interval.midpoint for sample in self.samples
        )
        if tuple(sorted(sample_coordinates)) != sample_coordinates or len(
            set(sample_coordinates)
        ) != len(sample_coordinates):
            raise ValueError(
                "boundary path samples must have unique ordered coordinates"
            )
        orthogonal_extent = PixelInterval(
            min(sample.orthogonal_interval.minimum for sample in self.samples),
            max(sample.orthogonal_interval.maximum for sample in self.samples),
        )
        object.__setattr__(
            self,
            "position",
            _fitted_path_interval(self.samples, orthogonal_extent),
        )
        if any(
            appearance.provenance != self.provenance
            for appearance in (self.lower_appearance, self.upper_appearance)
        ):
            raise ValueError("boundary appearances must share path provenance")

    @property
    def orthogonal_extent(self) -> PixelInterval:
        return PixelInterval(
            min(sample.orthogonal_interval.minimum for sample in self.samples),
            max(sample.orthogonal_interval.maximum for sample in self.samples),
        )

    def position_within(
        self,
        orthogonal_interval: PixelInterval,
    ) -> PixelInterval | None:
        measured_interval = self.orthogonal_extent.intersection(
            orthogonal_interval
        )
        if measured_interval is None:
            return None
        return _fitted_path_interval(self.samples, measured_interval)


@dataclass(frozen=True)
class HolderBoundaryObservation:
    side: BoundarySide
    position: PixelInterval
    supporting_paths: tuple[GrayBoundaryPathObservation, ...]

    def __post_init__(self) -> None:
        if not self.supporting_paths:
            raise ValueError("holder boundary requires supporting paths")
        ordered = tuple(
            sorted(
                self.supporting_paths,
                key=lambda path: str(path.provenance.observation_id),
            )
        )
        observation_ids = tuple(
            path.provenance.observation_id for path in ordered
        )
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError(
                "holder boundary supporting path identities must be unique"
            )
        if any(
            path.axis != boundary_axis_for_side(self.side)
            or path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION
            for path in ordered
        ):
            raise ValueError(
                "holder boundary requires edge-adjacent paths on one axis"
            )
        shared = PixelInterval.common_intersection(
            tuple(path.position for path in ordered)
        )
        if (
            shared is None
            or self.position.intersection(shared) != self.position
        ):
            raise ValueError(
                "holder boundary position must lie within the shared path interval"
            )
        object.__setattr__(self, "supporting_paths", ordered)

    @property
    def provenance(self) -> MeasurementProvenance:
        anchors = tuple(
            path.provenance.observation_id for path in self.supporting_paths
        )
        dependencies = tuple(
            sorted(
                {
                    dependency
                    for path in self.supporting_paths
                    for dependency in (
                        path.provenance.root_measurement,
                        *path.provenance.dependencies,
                    )
                    if dependency != MeasurementIdentity.BOUNDARY_PATHS
                },
                key=lambda item: item.value,
            )
        )
        return MeasurementProvenance(
            root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
            observation_id=ObservationId(
                f"holder_boundary:{self.side.value}:" + ":".join(map(str, anchors))
            ),
            dependencies=dependencies,
            description="consensus edge-adjacent holder boundary",
            boundary_anchors=anchors,
        )

    @property
    def outer_appearances(self) -> tuple[GrayAppearanceObservation, ...]:
        if self.side in {BoundarySide.LEADING, BoundarySide.TOP}:
            return tuple(path.lower_appearance for path in self.supporting_paths)
        return tuple(path.upper_appearance for path in self.supporting_paths)


@dataclass(frozen=True)
class HolderSafetyEnvelope:
    boundaries: tuple[HolderBoundaryObservation, ...]
    containment_fallback: ContainmentFallback
    state: EvidenceState = field(init=False)
    provenance: MeasurementProvenance = field(init=False)

    def __post_init__(self) -> None:
        by_side = {boundary.side: boundary for boundary in self.boundaries}
        if len(by_side) != len(self.boundaries):
            raise ValueError("holder safety boundaries must have unique sides")
        fallback = self.containment_fallback.box
        limits = {
            BoundarySide.LEADING: (float(fallback.left), float(fallback.right)),
            BoundarySide.TRAILING: (float(fallback.left), float(fallback.right)),
            BoundarySide.TOP: (float(fallback.top), float(fallback.bottom)),
            BoundarySide.BOTTOM: (float(fallback.top), float(fallback.bottom)),
        }
        if any(
            boundary.position.minimum < limits[boundary.side][0]
            or boundary.position.maximum > limits[boundary.side][1]
            for boundary in self.boundaries
        ):
            raise ValueError("holder safety boundary must lie inside containment")
        state = (
            EvidenceState.SUPPORTED
            if set(by_side) == set(BoundarySide)
            else EvidenceState.UNAVAILABLE
        )
        object.__setattr__(self, "state", state)
        if not self.boundaries:
            object.__setattr__(
                self,
                "provenance",
                self.containment_fallback.provenance,
            )
            return
        inputs = tuple(boundary.provenance for boundary in self.boundaries)
        object.__setattr__(
            self,
            "provenance",
            MeasurementProvenance(
                root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
                observation_id=ObservationId(
                    "holder_safety_envelope:"
                    + ":".join(
                        f"{boundary.side.value}={boundary.provenance.observation_id}"
                        for boundary in sorted(
                            self.boundaries,
                            key=lambda item: item.side.value,
                        )
                    )
                ),
                dependencies=tuple(
                    dict.fromkeys(
                        dependency
                        for item in inputs
                        for dependency in (
                            item.root_measurement,
                            *item.dependencies,
                        )
                        if dependency != MeasurementIdentity.BOUNDARY_PATHS
                    )
                ),
                description="holder safety envelope from edge-adjacent boundaries",
                boundary_anchors=tuple(
                    item.observation_id for item in inputs
                ),
            ),
        )

    def boundary(
        self,
        side: BoundarySide,
    ) -> HolderBoundaryObservation | None:
        return next(
            (boundary for boundary in self.boundaries if boundary.side == side),
            None,
        )

    def safe_axis_interval(self, axis: BoundaryAxis) -> PixelInterval:
        fallback = self.containment_fallback.box
        if axis == BoundaryAxis.LONG:
            lower_side = BoundarySide.LEADING
            upper_side = BoundarySide.TRAILING
            fallback_interval = PixelInterval(
                float(fallback.left),
                float(fallback.right),
            )
        elif axis == BoundaryAxis.SHORT:
            lower_side = BoundarySide.TOP
            upper_side = BoundarySide.BOTTOM
            fallback_interval = PixelInterval(
                float(fallback.top),
                float(fallback.bottom),
            )
        else:
            raise ValueError("holder safety requires a spatial axis")

        lower = self.boundary(lower_side)
        upper = self.boundary(upper_side)
        if (
            lower is not None
            and upper is not None
            and upper.position.minimum > lower.position.maximum
        ):
            return PixelInterval(
                lower.position.minimum,
                upper.position.maximum,
            )

        candidates: list[PixelInterval] = []
        if (
            lower is not None
            and fallback_interval.maximum > lower.position.maximum
        ):
            candidates.append(
                PixelInterval(
                    lower.position.minimum,
                    fallback_interval.maximum,
                )
            )
        if (
            upper is not None
            and upper.position.minimum > fallback_interval.minimum
        ):
            candidates.append(
                PixelInterval(
                    fallback_interval.minimum,
                    upper.position.maximum,
                )
            )
        return max(
            candidates,
            key=lambda interval: (
                interval.maximum - interval.minimum,
                -interval.minimum,
                interval.maximum,
            ),
            default=fallback_interval,
        )

    def contains_axis_interval(
        self,
        axis: BoundaryAxis,
        interval: PixelInterval,
    ) -> bool:
        safety = self.safe_axis_interval(axis)
        return bool(
            interval.minimum >= math.floor(safety.minimum)
            and interval.maximum <= math.ceil(safety.maximum)
        )

    @property
    def box(self) -> Box:
        long_axis = self.safe_axis_interval(BoundaryAxis.LONG)
        short_axis = self.safe_axis_interval(BoundaryAxis.SHORT)
        box = Box(
            math.floor(long_axis.minimum),
            math.floor(short_axis.minimum),
            math.ceil(long_axis.maximum),
            math.ceil(short_axis.maximum),
        )
        if not box.valid():
            raise ValueError("holder safety envelope must have positive extent")
        return box

@dataclass(frozen=True)
class FrameSequenceSearchScope:
    holder_safety: HolderSafetyEnvelope
    raw_boundary_paths: tuple[GrayBoundaryPathObservation, ...]
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if any(
            path not in self.raw_boundary_paths
            for item in self.holder_safety.boundaries
            for path in item.supporting_paths
        ):
            raise ValueError("holder boundaries must reference raw boundary paths")


@dataclass(frozen=True)
class BoundaryMeasurementSet:
    raw_paths: tuple[GrayBoundaryPathObservation, ...]
    holder_boundaries: tuple[HolderBoundaryObservation, ...]
    containment_fallback: ContainmentFallback

    def __post_init__(self) -> None:
        if any(
            path not in self.raw_paths
            for item in self.holder_boundaries
            for path in item.supporting_paths
        ):
            raise ValueError("holder boundaries must reference raw boundary paths")


class CrossAxisPathOutcome(str, Enum):
    BAND_OUTSIDE_CORRIDOR = "band_outside_corridor"
    APPEARANCE_REFERENCE_UNAVAILABLE = "appearance_reference_unavailable"
    PATH_SUPPORTED = "path_supported"
    CONTINUITY_WEAK = "continuity_weak"


@dataclass(frozen=True)
class ShortAxisMeasurementSpan:
    top: PixelInterval
    bottom: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.bottom.minimum <= self.top.maximum:
            raise ValueError("short-axis measurement span must have positive extent")

    @property
    def height_px(self) -> PixelInterval:
        return self.bottom.minus(self.top)


@dataclass(frozen=True)
class CrossAxisPathMeasurement:
    outcome: CrossAxisPathOutcome
    coverage_ratio: float | None
    longest_supported_ratio: float | None
    break_count: int | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, CrossAxisPathOutcome):
            raise TypeError("cross-axis path measurement requires a typed outcome")
        ratios = tuple(
            value
            for value in (
                self.coverage_ratio,
                self.longest_supported_ratio,
            )
            if value is not None
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("separator cross-axis ratios must lie in [0, 1]")
        if self.break_count is not None and self.break_count < 0:
            raise ValueError("separator cross-axis break count cannot be negative")
        unavailable = self.outcome in {
            CrossAxisPathOutcome.BAND_OUTSIDE_CORRIDOR,
            CrossAxisPathOutcome.APPEARANCE_REFERENCE_UNAVAILABLE,
        }
        measurements = (
            self.coverage_ratio,
            self.longest_supported_ratio,
            self.break_count,
        )
        if unavailable != all(value is None for value in measurements):
            raise ValueError(
                "cross-axis outcome must match measurement availability"
            )
        state, reason = {
            CrossAxisPathOutcome.BAND_OUTSIDE_CORRIDOR: (
                EvidenceState.UNAVAILABLE,
                "cross_axis_path_outside_measurement_corridor",
            ),
            CrossAxisPathOutcome.APPEARANCE_REFERENCE_UNAVAILABLE: (
                EvidenceState.UNAVAILABLE,
                "cross_axis_appearance_reference_unavailable",
            ),
            CrossAxisPathOutcome.PATH_SUPPORTED: (
                EvidenceState.SUPPORTED,
                "cross_axis_path_supported",
            ),
            CrossAxisPathOutcome.CONTINUITY_WEAK: (
                EvidenceState.CONTRADICTED,
                "cross_axis_continuity_weak",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class SeparatorCrossAxisMeasurement:
    observation_id: ObservationId
    short_axis_span: ShortAxisMeasurementSpan
    leading_edge_path: CrossAxisPathMeasurement
    trailing_edge_path: CrossAxisPathMeasurement
    band_path: CrossAxisPathMeasurement
    appearance_coherence_ratio: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("separator measurement requires an observation identity")
        if not isinstance(self.short_axis_span, ShortAxisMeasurementSpan):
            raise TypeError("separator measurement requires a typed short-axis span")
        paths = (
            self.leading_edge_path,
            self.trailing_edge_path,
            self.band_path,
        )
        if any(not isinstance(path, CrossAxisPathMeasurement) for path in paths):
            raise TypeError("separator measurement requires typed cross-axis paths")
        if self.appearance_coherence_ratio is not None and (
            not math.isfinite(self.appearance_coherence_ratio)
            or not 0.0 <= self.appearance_coherence_ratio <= 1.0
        ):
            raise ValueError("separator appearance coherence must lie in [0, 1]")
        all_unavailable = all(
            path.state == EvidenceState.UNAVAILABLE for path in paths
        )
        if all_unavailable != (self.appearance_coherence_ratio is None):
            raise ValueError(
                "separator appearance coherence must match path availability"
            )

    def edge_path(self, side: BoundarySide) -> CrossAxisPathMeasurement:
        if side == BoundarySide.LEADING:
            return self.leading_edge_path
        if side == BoundarySide.TRAILING:
            return self.trailing_edge_path
        raise ValueError("separator edge path requires a long-axis side")

    @property
    def supported_edge_count(self) -> int:
        return sum(
            path.state == EvidenceState.SUPPORTED
            for path in (self.leading_edge_path, self.trailing_edge_path)
        )

    @property
    def complete_separator_supported(self) -> bool:
        return all(
            path.state == EvidenceState.SUPPORTED
            for path in (self.leading_edge_path, self.trailing_edge_path)
        )

    @property
    def has_supported_path(self) -> bool:
        return any(
            path.state == EvidenceState.SUPPORTED
            for path in (
                self.leading_edge_path,
                self.trailing_edge_path,
                self.band_path,
            )
        )

    @property
    def all_paths_contradicted(self) -> bool:
        return not self.has_supported_path and all(
            path.state == EvidenceState.CONTRADICTED
            for path in (
                self.leading_edge_path,
                self.trailing_edge_path,
                self.band_path,
            )
        )


@dataclass(frozen=True)
class SeparatorBandObservation:
    leading_edge: PixelInterval
    trailing_edge: PixelInterval
    tonal_evidence: float
    appearance: GrayAppearanceObservation
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.trailing_edge.midpoint <= self.leading_edge.midpoint:
            raise ValueError("separator observation edges must be ordered")
        if self.appearance.provenance != self.provenance:
            raise ValueError("separator appearance must share band provenance")

    @property
    def width_px(self) -> PixelInterval:
        return self.trailing_edge.minus(self.leading_edge)

    @property
    def span(self) -> PixelInterval:
        return PixelInterval(
            self.leading_edge.minimum,
            self.trailing_edge.maximum,
        )

@dataclass(frozen=True)
class SeparatorBandCrossAxisSupport:
    observation: SeparatorBandObservation
    measurement: SeparatorCrossAxisMeasurement

    def __post_init__(self) -> None:
        observation_id = self.observation.provenance.observation_id
        if self.measurement.observation_id != observation_id:
            raise ValueError("separator support must preserve observation identity")


@dataclass(frozen=True)
class InterFrameBoundaryReference:
    lane_index: int | None
    boundary_index: int

    def __post_init__(self) -> None:
        if self.lane_index is not None and self.lane_index <= 0:
            raise ValueError("frame boundary lane index must be positive")
        if self.boundary_index <= 0:
            raise ValueError("frame boundary index must be positive")


class InterFrameSpacingBasis(str, Enum):
    OBSERVED = "observed"
    CORROBORATED_OVERLAP = "corroborated_overlap"
    GEOMETRY_HYPOTHESIS = "geometry_hypothesis"


class InterFrameSpacingKind(str, Enum):
    SEPARATOR = "separator"
    CONTACT = "contact"
    OVERLAP = "overlap"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class InterFrameSpacing:
    boundary: InterFrameBoundaryReference
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance
    basis: InterFrameSpacingBasis

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, InterFrameBoundaryReference):
            raise TypeError("inter-frame spacing requires a boundary reference")
        if not isinstance(self.basis, InterFrameSpacingBasis):
            raise TypeError("inter-frame spacing requires a typed basis")
        if (
            self.basis == InterFrameSpacingBasis.CORROBORATED_OVERLAP
            and self.signed_width_px.maximum >= 0.0
        ):
            raise ValueError("corroborated inter-photo spacing must be an overlap")

    @property
    def kind(self) -> InterFrameSpacingKind:
        interval = self.signed_width_px
        if interval.minimum > 0.0:
            return InterFrameSpacingKind.SEPARATOR
        if interval.maximum < 0.0:
            return InterFrameSpacingKind.OVERLAP
        if interval.minimum == 0.0 and interval.maximum == 0.0:
            return InterFrameSpacingKind.CONTACT
        return InterFrameSpacingKind.UNRESOLVED

    @property
    def state(self) -> EvidenceState:
        if self.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS:
            return EvidenceState.UNAVAILABLE
        return (
            EvidenceState.UNAVAILABLE
            if self.kind == InterFrameSpacingKind.UNRESOLVED
            else EvidenceState.SUPPORTED
        )

    @property
    def independently_observed(self) -> bool:
        return bool(
            self.basis == InterFrameSpacingBasis.OBSERVED
            and self.state == EvidenceState.SUPPORTED
        )

    @property
    def supports_output_protection(self) -> bool:
        return bool(
            self.kind == InterFrameSpacingKind.OVERLAP
            and self.basis
            in {
                InterFrameSpacingBasis.OBSERVED,
                InterFrameSpacingBasis.CORROBORATED_OVERLAP,
            }
        )

    @property
    def reason(self) -> str:
        if self.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS:
            return f"{self.kind.value}_spacing_hypothesis"
        if self.basis == InterFrameSpacingBasis.CORROBORATED_OVERLAP:
            return "independent_constraints_require_overlap"
        return f"observed_{self.kind.value}_spacing"
