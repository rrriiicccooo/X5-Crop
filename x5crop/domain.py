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
    GRAY_WORK = "gray_work"
    IMAGE_MEASUREMENT_STATISTICS = "image_measurement_statistics"
    LANE_DIVIDER_PROFILE = "lane_divider_profile"
    PHYSICAL_FRAME_ASPECT = "physical_frame_aspect"
    PHOTO_EDGES = "photo_edges"
    SEPARATOR_PROFILE = "separator_profile"
    SHORT_AXIS_BOUNDARIES = "short_axis_boundaries"


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
class HolderSpan:
    box: Box

    def __post_init__(self) -> None:
        if not self.box.valid():
            raise ValueError("holder span must have positive extent")


@dataclass(frozen=True)
class FrameCropEnvelope:
    photo_index: int
    box: Box

    def __post_init__(self) -> None:
        if self.photo_index <= 0:
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
        if shared != self.position:
            raise ValueError("holder boundary position must be the shared path interval")
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

    @property
    def inner_appearances(self) -> tuple[GrayAppearanceObservation, ...]:
        if self.side in {BoundarySide.LEADING, BoundarySide.TOP}:
            return tuple(path.upper_appearance for path in self.supporting_paths)
        return tuple(path.lower_appearance for path in self.supporting_paths)


class PhotoApertureEdgeSource(str, Enum):
    MEASURED_BOUNDARY_PATH = "measured_boundary_path"
    SEPARATOR_BAND_EDGE = "separator_band_edge"
    DIMENSION_HYPOTHESIS = "dimension_hypothesis"
    CANVAS_LIMIT = "canvas_limit"


@dataclass(frozen=True)
class PhotoApertureBoundaryResolution:
    photo_index: int
    side: BoundarySide
    position: PixelInterval
    state: EvidenceState
    source: PhotoApertureEdgeSource
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.photo_index <= 0:
            raise ValueError("photo aperture boundary index must be positive")
        if not isinstance(self.side, BoundarySide):
            raise TypeError("photo aperture boundary requires a typed side")
        if not isinstance(self.state, EvidenceState):
            raise TypeError("photo aperture boundary requires a typed state")
        if not isinstance(self.source, PhotoApertureEdgeSource):
            raise TypeError("photo aperture boundary requires a typed source")
        measured_source = self.source in {
            PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
            PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE,
        }
        if self.state == EvidenceState.SUPPORTED and not measured_source:
            raise ValueError(
                "only independently measured aperture boundaries can be supported"
            )
        if self.source == PhotoApertureEdgeSource.CANVAS_LIMIT and self.state not in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.NOT_APPLICABLE,
        }:
            raise ValueError("canvas limits cannot resolve a photo aperture boundary")

    @property
    def independently_observed(self) -> bool:
        return bool(
            self.state == EvidenceState.SUPPORTED
            and self.source
            in {
                PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH,
                PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE,
            }
        )


@dataclass(frozen=True)
class PhotoApertureEdgeAssignment:
    photo_index: int
    side: BoundarySide
    observation: GrayBoundaryPathObservation
    resolution: PhotoApertureBoundaryResolution

    def __post_init__(self) -> None:
        if (
            self.photo_index != self.resolution.photo_index
            or self.side != self.resolution.side
            or self.observation.axis != boundary_axis_for_side(self.side)
            or self.observation.provenance != self.resolution.provenance
        ):
            raise ValueError("aperture edge assignment must preserve measurement identity")
        if self.resolution.source != PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH:
            raise ValueError("aperture path assignment requires a measured boundary source")
        if not self.observation.position.intersects(self.resolution.position):
            raise ValueError("aperture path assignment must intersect its resolution")


@dataclass(frozen=True)
class PhotoAperture:
    index: int
    leading: PhotoApertureBoundaryResolution
    trailing: PhotoApertureBoundaryResolution
    top: PhotoApertureBoundaryResolution
    bottom: PhotoApertureBoundaryResolution

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("photo aperture index must be positive")
        resolutions = (self.leading, self.trailing, self.top, self.bottom)
        if any(item.photo_index != self.index for item in resolutions):
            raise ValueError("photo aperture edges must share one photo identity")
        if tuple(item.side for item in resolutions) != (
            BoundarySide.LEADING,
            BoundarySide.TRAILING,
            BoundarySide.TOP,
            BoundarySide.BOTTOM,
        ):
            raise ValueError("photo aperture requires all four physical sides")
        if self.trailing.position.minimum <= self.leading.position.maximum:
            raise ValueError("photo aperture must have guaranteed positive long-axis extent")
        if self.bottom.position.minimum <= self.top.position.maximum:
            raise ValueError("photo aperture must have guaranteed positive short-axis extent")

    @property
    def frame_crop_envelope(self) -> FrameCropEnvelope:
        return FrameCropEnvelope(
            self.index,
            Box(
                int(math.floor(self.leading.position.minimum)),
                int(math.floor(self.top.position.minimum)),
                int(math.ceil(self.trailing.position.maximum)),
                int(math.ceil(self.bottom.position.maximum)),
            ),
        )

    @property
    def all_boundaries_supported(self) -> bool:
        return all(
            item.state == EvidenceState.SUPPORTED
            for item in (self.leading, self.trailing, self.top, self.bottom)
        )


@dataclass(frozen=True)
class PhotoSequenceSearchScope:
    holder_span: HolderSpan
    raw_boundary_paths: tuple[GrayBoundaryPathObservation, ...]
    holder_boundaries: tuple[HolderBoundaryObservation, ...]
    containment_fallback: ContainmentFallback
    measurement_budget_exhausted: bool
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        sides = tuple(item.side for item in self.holder_boundaries)
        if len(sides) != len(set(sides)):
            raise ValueError("photo sequence search scope holder sides must be unique")
        if any(
            path not in self.raw_boundary_paths
            for item in self.holder_boundaries
            for path in item.supporting_paths
        ):
            raise ValueError("holder boundaries must reference raw boundary paths")
        holder = self.holder_span.box
        fallback = self.containment_fallback.box
        if not (
            holder.left <= fallback.left
            and holder.top <= fallback.top
            and holder.right >= fallback.right
            and holder.bottom >= fallback.bottom
        ):
            raise ValueError("containment fallback must lie inside the holder span")


@dataclass(frozen=True)
class BoundaryMeasurementSet:
    raw_paths: tuple[GrayBoundaryPathObservation, ...]
    holder_boundaries: tuple[HolderBoundaryObservation, ...]
    containment_fallback: ContainmentFallback
    measurement_budget_exhausted: bool

    def __post_init__(self) -> None:
        if any(
            path not in self.raw_paths
            for item in self.holder_boundaries
            for path in item.supporting_paths
        ):
            raise ValueError("holder boundaries must reference raw boundary paths")


class SeparatorCrossAxisOutcome(str, Enum):
    BAND_OUTSIDE_CORRIDOR = "band_outside_corridor"
    APPEARANCE_REFERENCE_UNAVAILABLE = "appearance_reference_unavailable"
    PATH_SUPPORTED = "path_supported"
    CONTINUITY_WEAK = "continuity_weak"


@dataclass(frozen=True)
class PhotoApertureCrossAxisHypothesis:
    top_path: GrayBoundaryPathObservation
    bottom_path: GrayBoundaryPathObservation

    def __post_init__(self) -> None:
        if (
            self.top_path.axis != BoundaryAxis.SHORT
            or self.bottom_path.axis != BoundaryAxis.SHORT
        ):
            raise ValueError("photo aperture cross axis requires short-axis paths")
        if self.bottom_path.position.minimum <= self.top_path.position.maximum:
            raise ValueError("photo aperture cross axis must have positive extent")

    @property
    def height_px(self) -> PixelInterval:
        return self.bottom_path.position.minus(self.top_path.position)

    @property
    def measurement_quality(self) -> float:
        return min(
            self.top_path.lower_appearance.spatial_continuity,
            self.top_path.upper_appearance.spatial_continuity,
        ) + min(
            self.bottom_path.lower_appearance.spatial_continuity,
            self.bottom_path.upper_appearance.spatial_continuity,
        )

    @property
    def uncertainty_px(self) -> float:
        return (
            self.top_path.position.maximum
            - self.top_path.position.minimum
            + self.bottom_path.position.maximum
            - self.bottom_path.position.minimum
        )


@dataclass(frozen=True)
class SeparatorCrossAxisMeasurement:
    observation_id: ObservationId
    aperture_cross_axis: PhotoApertureCrossAxisHypothesis
    outcome: SeparatorCrossAxisOutcome
    coverage_ratio: float | None
    longest_supported_ratio: float | None
    break_count: int | None
    appearance_coherence_ratio: float | None
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, ObservationId):
            raise TypeError("separator measurement requires an observation identity")
        if not isinstance(
            self.aperture_cross_axis,
            PhotoApertureCrossAxisHypothesis,
        ):
            raise TypeError("separator measurement requires a typed aperture cross axis")
        if not isinstance(self.outcome, SeparatorCrossAxisOutcome):
            raise TypeError("separator cross-axis measurement requires a typed outcome")
        ratios = tuple(
            value
            for value in (
                self.coverage_ratio,
                self.longest_supported_ratio,
                self.appearance_coherence_ratio,
            )
            if value is not None
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in ratios):
            raise ValueError("separator cross-axis ratios must lie in [0, 1]")
        if self.break_count is not None and self.break_count < 0:
            raise ValueError("separator cross-axis break count cannot be negative")
        unavailable = self.outcome in {
            SeparatorCrossAxisOutcome.BAND_OUTSIDE_CORRIDOR,
            SeparatorCrossAxisOutcome.APPEARANCE_REFERENCE_UNAVAILABLE,
        }
        measurements = (
            self.coverage_ratio,
            self.longest_supported_ratio,
            self.break_count,
            self.appearance_coherence_ratio,
        )
        if unavailable != all(value is None for value in measurements):
            raise ValueError(
                "cross-axis outcome must match measurement availability"
            )
        state, reason = {
            SeparatorCrossAxisOutcome.BAND_OUTSIDE_CORRIDOR: (
                EvidenceState.UNAVAILABLE,
                "separator_band_outside_measurement_corridor",
            ),
            SeparatorCrossAxisOutcome.APPEARANCE_REFERENCE_UNAVAILABLE: (
                EvidenceState.UNAVAILABLE,
                "separator_appearance_reference_unavailable",
            ),
            SeparatorCrossAxisOutcome.PATH_SUPPORTED: (
                EvidenceState.SUPPORTED,
                "cross_axis_path_supported",
            ),
            SeparatorCrossAxisOutcome.CONTINUITY_WEAK: (
                EvidenceState.CONTRADICTED,
                "cross_axis_continuity_weak",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class SeparatorBandObservation:
    start: float
    end: float
    tonal_evidence: float
    appearance: GrayAppearanceObservation
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("separator observation must have positive width")
        if self.appearance.provenance != self.provenance:
            raise ValueError("separator appearance must share band provenance")

    @property
    def width(self) -> float:
        return float(self.end) - float(self.start)

    @property
    def interval(self) -> PixelInterval:
        return PixelInterval(float(self.start), float(self.end))

    @property
    def midpoint(self) -> float:
        return 0.5 * (float(self.start) + float(self.end))


@dataclass(frozen=True)
class SeparatorBandCrossAxisSupport:
    observation: SeparatorBandObservation
    measurements: tuple[SeparatorCrossAxisMeasurement, ...]

    def __post_init__(self) -> None:
        observation_id = self.observation.provenance.observation_id
        if any(
            item.observation_id != observation_id
            for item in self.measurements
        ):
            raise ValueError("separator support must preserve observation identity")
        hypotheses = tuple(item.aperture_cross_axis for item in self.measurements)
        if not hypotheses or len(set(hypotheses)) != len(hypotheses):
            raise ValueError(
                "separator support requires unique cross-axis measurements"
            )

    def measurement_for(
        self,
        hypothesis: PhotoApertureCrossAxisHypothesis,
    ) -> SeparatorCrossAxisMeasurement:
        matches = tuple(
            item
            for item in self.measurements
            if item.aperture_cross_axis == hypothesis
        )
        if len(matches) != 1:
            raise ValueError(
                "separator observation does not contain the requested cross-axis measurement"
            )
        return matches[0]


@dataclass(frozen=True)
class InterPhotoBoundaryReference:
    lane_index: int | None
    boundary_index: int

    def __post_init__(self) -> None:
        if self.lane_index is not None and self.lane_index <= 0:
            raise ValueError("frame boundary lane index must be positive")
        if self.boundary_index <= 0:
            raise ValueError("frame boundary index must be positive")


class InterPhotoSpacingBasis(str, Enum):
    OBSERVED = "observed"
    CORROBORATED_OVERLAP = "corroborated_overlap"
    GEOMETRY_HYPOTHESIS = "geometry_hypothesis"


class InterPhotoSpacingKind(str, Enum):
    SEPARATOR = "separator"
    CONTACT = "contact"
    OVERLAP = "overlap"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class InterPhotoSpacing:
    boundary: InterPhotoBoundaryReference
    signed_width_px: PixelInterval
    provenance: MeasurementProvenance
    basis: InterPhotoSpacingBasis

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, InterPhotoBoundaryReference):
            raise TypeError("inter-photo spacing requires a boundary reference")
        if not isinstance(self.basis, InterPhotoSpacingBasis):
            raise TypeError("inter-photo spacing requires a typed basis")
        if (
            self.basis == InterPhotoSpacingBasis.CORROBORATED_OVERLAP
            and self.signed_width_px.maximum >= 0.0
        ):
            raise ValueError("corroborated inter-photo spacing must be an overlap")

    @property
    def kind(self) -> InterPhotoSpacingKind:
        interval = self.signed_width_px
        if interval.minimum > 0.0:
            return InterPhotoSpacingKind.SEPARATOR
        if interval.maximum < 0.0:
            return InterPhotoSpacingKind.OVERLAP
        if interval.minimum == 0.0 and interval.maximum == 0.0:
            return InterPhotoSpacingKind.CONTACT
        return InterPhotoSpacingKind.UNRESOLVED

    @property
    def state(self) -> EvidenceState:
        if self.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS:
            return EvidenceState.UNAVAILABLE
        return (
            EvidenceState.UNAVAILABLE
            if self.kind == InterPhotoSpacingKind.UNRESOLVED
            else EvidenceState.SUPPORTED
        )

    @property
    def independently_observed(self) -> bool:
        return bool(
            self.basis == InterPhotoSpacingBasis.OBSERVED
            and self.state == EvidenceState.SUPPORTED
        )

    @property
    def supports_output_protection(self) -> bool:
        return bool(
            self.kind == InterPhotoSpacingKind.OVERLAP
            and self.basis
            in {
                InterPhotoSpacingBasis.OBSERVED,
                InterPhotoSpacingBasis.CORROBORATED_OVERLAP,
            }
        )

    @property
    def reason(self) -> str:
        if self.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS:
            return f"{self.kind.value}_spacing_hypothesis"
        if self.basis == InterPhotoSpacingBasis.CORROBORATED_OVERLAP:
            return "independent_constraints_require_overlap"
        return f"observed_{self.kind.value}_spacing"


@dataclass(frozen=True)
class SeparatorWidthConstraint:
    adjacent_photo_width_px: PixelInterval

    def __post_init__(self) -> None:
        if self.adjacent_photo_width_px.minimum <= 0.0:
            raise ValueError("separator width constraint requires positive photo width")

    def permits(self, observation: SeparatorBandObservation) -> bool:
        return observation.width < self.adjacent_photo_width_px.minimum


@dataclass(frozen=True)
class SeparatorBandAssignment:
    boundary_index: int
    observation: SeparatorBandObservation
    cross_axis_measurement: SeparatorCrossAxisMeasurement
    preceding_trailing_edge: PhotoApertureBoundaryResolution
    following_leading_edge: PhotoApertureBoundaryResolution
    width_constraint: SeparatorWidthConstraint

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("separator assignment boundary index must be positive")
        if (
            self.cross_axis_measurement.observation_id
            != self.observation.provenance.observation_id
        ):
            raise ValueError("separator assignment measurement must belong to its band")
        if self.cross_axis_measurement.state != EvidenceState.SUPPORTED:
            raise ValueError("assigned separator requires cross-axis support")
        if not self.width_constraint.permits(self.observation):
            raise ValueError(
                "assigned separator must be narrower than one adjacent photo"
            )
        if (
            self.preceding_trailing_edge.photo_index != self.boundary_index
            or self.preceding_trailing_edge.side != BoundarySide.TRAILING
            or self.following_leading_edge.photo_index != self.boundary_index + 1
            or self.following_leading_edge.side != BoundarySide.LEADING
            or self.preceding_trailing_edge.state != EvidenceState.SUPPORTED
            or self.following_leading_edge.state != EvidenceState.SUPPORTED
        ):
            raise ValueError(
                "separator assignment requires two supported adjacent aperture edges"
            )
        expected_preceding = PixelInterval.exact(self.observation.start)
        expected_following = PixelInterval.exact(self.observation.end)
        if (
            self.preceding_trailing_edge.source
            != PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
            or self.following_leading_edge.source
            != PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
            or self.preceding_trailing_edge.position != expected_preceding
            or self.following_leading_edge.position != expected_following
            or self.preceding_trailing_edge.provenance != self.observation.provenance
            or self.following_leading_edge.provenance != self.observation.provenance
        ):
            raise ValueError(
                "separator assignment aperture edges must match observed band edges"
            )

    @property
    def independent(self) -> bool:
        return True

    @property
    def state(self) -> EvidenceState:
        return EvidenceState.SUPPORTED

    @property
    def reason(self) -> str:
        return "separator_band_edges_bind_adjacent_photo_apertures"
