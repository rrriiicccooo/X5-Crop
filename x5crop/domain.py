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
    SCAN_CALIBRATION = "scan_calibration"
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


class FrameDimensionPriorSource(str, Enum):
    SCAN_CALIBRATION = "scan_calibration"
    PHYSICAL_ASPECT = "physical_aspect"


@dataclass(frozen=True)
class FrameDimensionPrior:
    frame_size_mm: tuple[float, float]
    source: FrameDimensionPriorSource
    provenance: MeasurementProvenance
    calibrated_width_px: PixelInterval | None = None
    calibrated_height_px: PixelInterval | None = None

    def __post_init__(self) -> None:
        width_mm, height_mm = self.frame_size_mm
        if (
            width_mm <= 0.0
            or height_mm <= 0.0
            or not math.isfinite(width_mm)
            or not math.isfinite(height_mm)
        ):
            raise ValueError("frame dimension prior requires a physical size")
        if not isinstance(self.source, FrameDimensionPriorSource):
            raise ValueError("frame dimension prior requires a typed source")
        calibrated = self.source == FrameDimensionPriorSource.SCAN_CALIBRATION
        intervals = (self.calibrated_width_px, self.calibrated_height_px)
        if calibrated != all(item is not None for item in intervals):
            raise ValueError("calibrated dimension prior requires both pixel axes")
        if any(item is not None and item.minimum <= 0.0 for item in intervals):
            raise ValueError("calibrated dimension intervals must be positive")

    @property
    def aspect(self) -> float:
        return float(self.frame_size_mm[0]) / float(self.frame_size_mm[1])

    @property
    def calibrated(self) -> bool:
        return self.source == FrameDimensionPriorSource.SCAN_CALIBRATION


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
class GrayBoundaryPathObservation:
    axis: BoundaryAxis
    position: PixelInterval
    kind: BoundaryKind
    local_positions: tuple[PixelInterval, ...]
    lower_appearance: GrayAppearanceObservation
    upper_appearance: GrayAppearanceObservation
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.axis, BoundaryAxis):
            raise TypeError("boundary observation requires a typed axis")
        if not isinstance(self.kind, BoundaryKind):
            raise TypeError("boundary observation requires a typed kind")
        if not self.local_positions:
            raise ValueError("boundary path requires local positions")
        envelope = PixelInterval(
            min(item.minimum for item in self.local_positions),
            max(item.maximum for item in self.local_positions),
        )
        if self.position != envelope:
            raise ValueError("boundary path position must enclose its local measurements")
        if any(
            appearance.provenance != self.provenance
            for appearance in (self.lower_appearance, self.upper_appearance)
        ):
            raise ValueError("boundary appearances must share path provenance")


@dataclass(frozen=True)
class HolderBoundaryObservation:
    side: BoundarySide
    position: PixelInterval
    path: GrayBoundaryPathObservation

    def __post_init__(self) -> None:
        if (
            self.path.axis != boundary_axis_for_side(self.side)
            or self.path.position != self.position
        ):
            raise ValueError("holder boundary must preserve its raw path identity")
        if self.path.kind != BoundaryKind.EDGE_ADJACENT_TRANSITION:
            raise ValueError("holder boundary requires an edge-adjacent measurement")

    @property
    def provenance(self) -> MeasurementProvenance:
        return self.path.provenance

    @property
    def outer_appearance(self) -> GrayAppearanceObservation:
        if self.side in {BoundarySide.LEADING, BoundarySide.TOP}:
            return self.path.lower_appearance
        return self.path.upper_appearance

    @property
    def inner_appearance(self) -> GrayAppearanceObservation:
        if self.side in {BoundarySide.LEADING, BoundarySide.TOP}:
            return self.path.upper_appearance
        return self.path.lower_appearance


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
        if any(item.path not in self.raw_boundary_paths for item in self.holder_boundaries):
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
        if any(item.path not in self.raw_paths for item in self.holder_boundaries):
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
    def kind(self) -> str:
        interval = self.signed_width_px
        if interval.minimum > 0.0:
            return "separator"
        if interval.maximum < 0.0:
            return "overlap"
        if interval.minimum == 0.0 and interval.maximum == 0.0:
            return "contact"
        return "unresolved"

    @property
    def state(self) -> EvidenceState:
        if self.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS:
            return EvidenceState.UNAVAILABLE
        return (
            EvidenceState.UNAVAILABLE
            if self.kind == "unresolved"
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
            self.kind == "overlap"
            and self.basis
            in {
                InterPhotoSpacingBasis.OBSERVED,
                InterPhotoSpacingBasis.CORROBORATED_OVERLAP,
            }
        )

    @property
    def reason(self) -> str:
        if self.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS:
            return f"{self.kind}_spacing_hypothesis"
        if self.basis == InterPhotoSpacingBasis.CORROBORATED_OVERLAP:
            return "independent_constraints_require_overlap"
        return f"observed_{self.kind}_spacing"


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
