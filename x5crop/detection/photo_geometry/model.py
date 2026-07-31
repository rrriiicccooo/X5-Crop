from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
import math
from typing import TypeAlias

import numpy as np

from ...domain import (
    Box,
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
    WorkspaceExtent,
)
from ...formats import FrameDesignApertureMm


class BoundaryAxis(str, Enum):
    """Source-raster coordinate varied while looking for a transition."""

    X = "x"
    Y = "y"


class BoundaryRole(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    START = "start"
    END = "end"
    LONG_BOUNDARY = "long_boundary"


class BoundarySource(str, Enum):
    OBSERVED = "observed"
    INFERRED_OPPOSITE_EDGE = "inferred_opposite_edge"
    INFERRED_SEQUENCE = "inferred_sequence"


class QueryPurpose(str, Enum):
    TOP_CORRIDOR = "top_corridor"
    BOTTOM_CORRIDOR = "bottom_corridor"
    SEQUENCE_ANCHOR_TILE = "sequence_anchor_tile"
    OUTER_PROPOSAL_REMEASUREMENT = "outer_proposal_remeasurement"


class AdjacencyKind(str, Enum):
    EDGE_PAIR = "edge_pair"
    ONE_SIDED = "one_sided"
    CONTACT = "contact"
    OVERLAP = "overlap"
    MODEL_ONLY = "model_only"


@dataclass(frozen=True)
class PhotoBoundaryMeasurementSpec:
    """The one tracked V4.9 measurement and fitting contract."""

    lattice_support_divisor: float = 12.0
    lattice_minimum_mm: float = 2.0
    lattice_maximum_mm: float = 4.0
    local_window_mm: float = 0.25
    transition_gap_mm: float = 0.05
    maximum_transition_interval_mm: float = 1.0
    gradient_z_minimum: float = 3.0
    tone_or_texture_z_minimum: float = 3.0
    maximum_search_angle_degrees: float = 4.0
    line_connection_allowance_mm: float = 0.10
    maximum_missing_lattice_steps: int = 1
    huber_irls_rounds: int = 4
    huber_minimum_threshold_mm: float = 0.05
    huber_mad_multiplier: float = 2.5
    inlier_minimum_threshold_mm: float = 0.10
    inlier_mad_multiplier: float = 3.0
    angle_endpoint_uncertainty_multiplier: float = 2.0
    minimum_trace_count: int = 4
    minimum_trace_fraction: float = 0.60
    minimum_continuous_support_fraction: float = 0.50
    geometry_equivalence_mm: float = 0.05
    maximum_streaming_block_pixels: int = 1_048_576
    dimension_search_allowance_mm: float = 1.0
    center_offset_allowance_mm: float = 1.0
    anchor_tile_width_mm: float = 6.0
    interpolation_allowance_source_px: float = 1.0
    background_texture_ratio_minimum: float = 2.0
    background_tone_to_texture_minimum: float = 6.0
    directional_background_support_minimum: float = 0.25
    directional_role_preference_minimum: float = 0.60
    directional_sequence_support_minimum: float = 0.90
    nominal_calibration_sample_ids: tuple[str, ...] = (
        "S027",
        "S035",
        "S051",
        "S055",
        "S062",
        "S091",
        "S094",
        "S109",
    )
    stress_excluded_sample_id: str = "S098"

    def __post_init__(self) -> None:
        positive = (
            self.lattice_support_divisor,
            self.lattice_minimum_mm,
            self.lattice_maximum_mm,
            self.local_window_mm,
            self.transition_gap_mm,
            self.maximum_transition_interval_mm,
            self.gradient_z_minimum,
            self.tone_or_texture_z_minimum,
            self.maximum_search_angle_degrees,
            self.line_connection_allowance_mm,
            self.huber_minimum_threshold_mm,
            self.huber_mad_multiplier,
            self.inlier_minimum_threshold_mm,
            self.inlier_mad_multiplier,
            self.angle_endpoint_uncertainty_multiplier,
            self.minimum_trace_fraction,
            self.minimum_continuous_support_fraction,
            self.geometry_equivalence_mm,
            self.dimension_search_allowance_mm,
            self.center_offset_allowance_mm,
            self.anchor_tile_width_mm,
            self.interpolation_allowance_source_px,
            self.background_texture_ratio_minimum,
            self.background_tone_to_texture_minimum,
            self.directional_background_support_minimum,
            self.directional_role_preference_minimum,
            self.directional_sequence_support_minimum,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("photo-boundary measurement spec must be positive")
        if self.lattice_minimum_mm > self.lattice_maximum_mm:
            raise ValueError("measurement lattice bounds are reversed")
        if (
            self.maximum_missing_lattice_steps != 1
            or self.huber_irls_rounds != 4
            or self.minimum_trace_count != 4
            or self.maximum_streaming_block_pixels != 1_048_576
        ):
            raise ValueError("photo-boundary discrete limits are not canonical")
        if not (
            0.0 < self.minimum_trace_fraction <= 1.0
            and 0.0 < self.minimum_continuous_support_fraction <= 1.0
            and 0.0 < self.directional_role_preference_minimum <= 1.0
            and 0.0 < self.directional_sequence_support_minimum <= 1.0
        ):
            raise ValueError("measurement support fractions are invalid")
        if len(set(self.nominal_calibration_sample_ids)) != 8:
            raise ValueError("nominal calibration receipt must name eight samples")
        if (
            self.stress_excluded_sample_id
            in self.nominal_calibration_sample_ids
        ):
            raise ValueError("stress sample cannot calibrate nominal thresholds")

    @property
    def calibration_receipt_id(self) -> str:
        payload = json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + sha256(payload).hexdigest()

    def lattice_spacing_mm(self, expected_support_mm: float) -> float:
        if not math.isfinite(expected_support_mm) or expected_support_mm <= 0.0:
            raise ValueError("lattice support must be finite and positive")
        return min(
            self.lattice_maximum_mm,
            max(
                self.lattice_minimum_mm,
                expected_support_mm / self.lattice_support_divisor,
            ),
        )


PHOTO_BOUNDARY_MEASUREMENT_SPEC = PhotoBoundaryMeasurementSpec()


@dataclass(frozen=True)
class PhotoBoundaryMeasurementField:
    """Count/offset-independent source gray and exact local query authority."""

    source_gray: np.ndarray = field(repr=False, compare=False)
    layout: str
    source_extent: WorkspaceExtent = field(init=False)
    provenance: MeasurementProvenance = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_gray, np.ndarray)
            or self.source_gray.ndim != 2
            or self.source_gray.dtype != np.uint8
            or min(self.source_gray.shape) <= 0
        ):
            raise ValueError("photo-boundary field requires source uint8 gray")
        if self.layout not in {"horizontal", "vertical"}:
            raise ValueError("photo-boundary field requires a canonical layout")
        self.source_gray.flags.writeable = False
        object.__setattr__(
            self,
            "source_extent",
            WorkspaceExtent(
                width=int(self.source_gray.shape[1]),
                height=int(self.source_gray.shape[0]),
            ),
        )
        object.__setattr__(
            self,
            "provenance",
            MeasurementProvenance(
                root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
                observation_id=ObservationId("photo_boundary:source_gray"),
                dependencies=(MeasurementIdentity.BASE_GRAY,),
                description=(
                    "immutable source-coordinate gray with streaming local "
                    "photo-boundary query authority"
                ),
            ),
        )


@dataclass(frozen=True)
class PhotoBoundaryMeasurementQuery:
    query_id: str
    registration_index: int
    lane_id: str
    purpose: QueryPurpose
    boundary_axis: BoundaryAxis
    trace_positions_px: tuple[int, ...]
    search_intervals_px: tuple[FiniteInterval, ...]
    expected_support_px: float
    boundary_axis_scale_px_per_mm: PositiveInterval
    trace_axis_scale_px_per_mm: PositiveInterval
    measurement_halo_px: int
    search_proposal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.query_id
            or self.registration_index < 0
            or not self.lane_id
            or not isinstance(self.purpose, QueryPurpose)
            or not isinstance(self.boundary_axis, BoundaryAxis)
            or not self.trace_positions_px
            or len(self.trace_positions_px) != len(self.search_intervals_px)
            or tuple(sorted(set(self.trace_positions_px)))
            != self.trace_positions_px
            or not math.isfinite(self.expected_support_px)
            or self.expected_support_px <= 0.0
            or self.measurement_halo_px <= 0
            or not self.search_proposal_ids
        ):
            raise ValueError("photo-boundary query is incomplete")
        if len(set(self.search_proposal_ids)) != len(
            self.search_proposal_ids
        ):
            raise ValueError("search proposal identities must be unique")


@dataclass(frozen=True)
class PhotoBoundaryTransition:
    transition_id: ObservationId
    query_id: str
    trace_ordinal: int
    trace_coordinate_px: int
    coordinate_interval_px: FiniteInterval
    gradient_z: float
    tone_z: float
    texture_z: float
    left_tone_mean: float
    right_tone_mean: float
    left_texture_mean: float
    right_texture_mean: float
    polarity: int
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not self.query_id
            or self.trace_ordinal < 0
            or self.polarity not in {-1, 0, 1}
            or any(
                not math.isfinite(value) or value < 0.0
                for value in (
                    self.gradient_z,
                    self.tone_z,
                    self.texture_z,
                    self.left_tone_mean,
                    self.right_tone_mean,
                    self.left_texture_mean,
                    self.right_texture_mean,
                )
            )
            or self.provenance.root_measurement
            != MeasurementIdentity.PHOTO_BOUNDARY
        ):
            raise ValueError("photo-boundary transition is invalid")

    @property
    def coordinate_px(self) -> float:
        return self.coordinate_interval_px.center


@dataclass(frozen=True)
class PhotoBoundaryCoverageReceipt:
    query_id: str
    registered_trace_count: int
    completed_trace_count: int
    registered_coordinate_count: int
    completed_coordinate_count: int
    pixel_query_count: int
    streaming_block_count: int
    peak_temporary_bytes: int
    shared_measurement_reuse_count: int
    complete: bool

    def __post_init__(self) -> None:
        counts = (
            self.registered_trace_count,
            self.completed_trace_count,
            self.registered_coordinate_count,
            self.completed_coordinate_count,
            self.pixel_query_count,
            self.streaming_block_count,
            self.peak_temporary_bytes,
            self.shared_measurement_reuse_count,
        )
        if not self.query_id or any(value < 0 for value in counts):
            raise ValueError("measurement coverage receipt is invalid")
        derived = (
            self.registered_trace_count == self.completed_trace_count
            and self.registered_coordinate_count
            == self.completed_coordinate_count
        )
        if self.complete != derived:
            raise ValueError("measurement coverage completion is inconsistent")


@dataclass(frozen=True)
class PhotoBoundaryMeasurementSet:
    query: PhotoBoundaryMeasurementQuery
    state: EvidenceState
    transitions: tuple[PhotoBoundaryTransition, ...]
    coverage: PhotoBoundaryCoverageReceipt

    def __post_init__(self) -> None:
        if self.query.query_id != self.coverage.query_id:
            raise ValueError("measurement set query identity disagrees")
        if self.state == EvidenceState.SUPPORTED:
            if not self.coverage.complete:
                raise ValueError("supported measurement requires complete coverage")
        elif self.transitions:
            raise ValueError("incomplete measurement cannot expose transitions")
        identities = tuple(item.transition_id for item in self.transitions)
        if len(set(identities)) != len(identities):
            raise ValueError("transition identities must be unique")
        if any(item.query_id != self.query.query_id for item in self.transitions):
            raise ValueError("measurement set contains a foreign transition")


@dataclass(frozen=True)
class PhotoEdgeSearchCorridor:
    corridor_id: str
    lane_id: str
    role: BoundaryRole
    boundary_axis: BoundaryAxis
    trace_positions_px: tuple[int, ...]
    core_intervals_px: tuple[FiniteInterval, ...]
    measurement_intervals_px: tuple[FiniteInterval, ...]
    measurement_halo_px: int
    provenance: str = "scan_canvas_format_search_proposal"

    def __post_init__(self) -> None:
        count = len(self.trace_positions_px)
        if (
            not self.corridor_id
            or not self.lane_id
            or self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            or count == 0
            or len(self.core_intervals_px) != count
            or len(self.measurement_intervals_px) != count
            or self.measurement_halo_px <= 0
            or self.provenance
            != "scan_canvas_format_search_proposal"
        ):
            raise ValueError("photo-edge search corridor is invalid")
        for core, measured in zip(
            self.core_intervals_px,
            self.measurement_intervals_px,
            strict=True,
        ):
            if (
                measured.minimum > core.minimum
                or measured.maximum < core.maximum
            ):
                raise ValueError("measurement halo must contain corridor core")


@dataclass(frozen=True)
class SequenceAnchorTile:
    tile_id: str
    core_px: FiniteInterval
    measurement_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.tile_id
            or self.core_px.maximum <= self.core_px.minimum
            or self.measurement_px.minimum > self.core_px.minimum
            # Core intervals are half-open; the last measurable source
            # coordinate is therefore allowed to be exactly one pixel below
            # the final core endpoint.
            or self.measurement_px.maximum + 1.0 < self.core_px.maximum
        ):
            raise ValueError("sequence anchor tile is invalid")


@dataclass(frozen=True)
class SequenceAnchorDiscoveryDomain:
    domain_id: str
    lane_id: str
    translation_interval_px: FiniteInterval
    long_axis_extent_px: int
    authoritative_sequence_length: int
    tiles: tuple[SequenceAnchorTile, ...]
    grid_execution_order: tuple[str, ...]
    outer_execution_order: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.domain_id
            or not self.lane_id
            or self.long_axis_extent_px <= 0
            or self.authoritative_sequence_length <= 0
            or not self.tiles
        ):
            raise ValueError("sequence anchor discovery domain is invalid")
        tile_ids = tuple(item.tile_id for item in self.tiles)
        if len(set(tile_ids)) != len(tile_ids):
            raise ValueError("sequence anchor tiles must be unique")
        if set(self.grid_execution_order) != set(tile_ids):
            raise ValueError("Grid order must cover every anchor tile")
        if set(self.outer_execution_order) != set(tile_ids):
            raise ValueError("outer order must cover every anchor tile")
        ordered = sorted(self.tiles, key=lambda item: item.core_px.minimum)
        if ordered[0].core_px.minimum > 0.0:
            raise ValueError("anchor tiles must begin at lane authority")
        if ordered[-1].core_px.maximum < self.long_axis_extent_px:
            raise ValueError("anchor tiles must end at lane authority")
        for left, right in zip(ordered, ordered[1:]):
            if not math.isclose(
                left.core_px.maximum,
                right.core_px.minimum,
                abs_tol=1.0e-9,
            ):
                raise ValueError("anchor tile cores must be seamless")


@dataclass(frozen=True)
class PhotoSequenceExtentProposal:
    proposal_id: str
    lane_id: str
    source: str
    long_axis_interval_px: FiniteInterval
    query_domain_only: bool = True

    def __post_init__(self) -> None:
        if (
            not self.proposal_id
            or not self.lane_id
            or self.source
            not in {
                "outer_background",
                "outer_content",
                "outer_separator_first",
                "grid_search_order",
            }
            or not self.query_domain_only
        ):
            raise ValueError("photo-sequence extent proposal is invalid")


@dataclass(frozen=True)
class SourceCoordinateLine:
    """Normalized line ``normal_x*x + normal_y*y = offset``."""

    normal_x: float
    normal_y: float
    offset_px: float
    support_projection_px: FiniteInterval
    source_axis_long: BoundaryAxis

    def __post_init__(self) -> None:
        values = (self.normal_x, self.normal_y, self.offset_px)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("source-coordinate line must be finite")
        if not math.isclose(
            math.hypot(self.normal_x, self.normal_y),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        ):
            raise ValueError("source-coordinate line normal must be unit length")
        long_vector = (
            (1.0, 0.0)
            if self.source_axis_long == BoundaryAxis.X
            else (0.0, 1.0)
        )
        short_vector = (
            (0.0, 1.0)
            if self.source_axis_long == BoundaryAxis.X
            else (1.0, 0.0)
        )
        if max(
            abs(self.normal_x * long_vector[0] + self.normal_y * long_vector[1]),
            abs(
                self.normal_x * short_vector[0]
                + self.normal_y * short_vector[1]
            ),
        ) < math.cos(math.radians(4.0)) - 1.0e-8:
            raise ValueError("source line exceeds the four-degree authority")

    def intersection(
        self,
        other: "SourceCoordinateLine",
    ) -> tuple[float, float]:
        determinant = (
            self.normal_x * other.normal_y
            - self.normal_y * other.normal_x
        )
        if abs(determinant) <= 1.0e-12:
            raise ValueError("parallel boundary lines do not intersect")
        return (
            (
                self.offset_px * other.normal_y
                - self.normal_y * other.offset_px
            )
            / determinant,
            (
                self.normal_x * other.offset_px
                - self.offset_px * other.normal_x
            )
            / determinant,
        )


@dataclass(frozen=True)
class PhotoBoundaryObservation:
    observation_id: ObservationId
    role: BoundaryRole
    line: SourceCoordinateLine
    offset_interval_px: FiniteInterval
    fit_residual_px: float
    angle_interval_degrees: FiniteInterval
    trace_support_count: int
    queried_trace_count: int
    continuous_support_fraction: float
    transition_ids: tuple[ObservationId, ...]
    provenance: MeasurementProvenance
    background_side_support_fraction: float = 0.0
    left_background_preference_fraction: float = 0.0
    right_background_preference_fraction: float = 0.0

    def __post_init__(self) -> None:
        if (
            not self.offset_interval_px.contains(
                self.line.offset_px,
                epsilon=1.0e-8,
            )
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or self.trace_support_count <= 0
            or self.queried_trace_count < self.trace_support_count
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not 0.0 <= self.background_side_support_fraction <= 1.0
            or not 0.0
            <= self.left_background_preference_fraction
            <= 1.0
            or not 0.0
            <= self.right_background_preference_fraction
            <= 1.0
            or not self.transition_ids
            or self.provenance.root_measurement
            != MeasurementIdentity.PHOTO_BOUNDARY
        ):
            raise ValueError("photo-boundary observation is invalid")
        if len(set(self.transition_ids)) != len(self.transition_ids):
            raise ValueError("line transition identities must be unique")

    @property
    def measurement_uncertainty_px(self) -> float:
        return max(
            self.line.offset_px - self.offset_interval_px.minimum,
            self.offset_interval_px.maximum - self.line.offset_px,
        )


@dataclass(frozen=True)
class FrameBoundaryGeometry:
    role: BoundaryRole
    line: SourceCoordinateLine
    offset_interval_px: FiniteInterval
    source: BoundarySource
    observation_ids: tuple[ObservationId, ...]
    named_inference: str | None

    def __post_init__(self) -> None:
        if not self.offset_interval_px.contains(
            self.line.offset_px,
            epsilon=1.0e-8,
        ):
            raise ValueError("frame boundary interval must contain its line")
        observed = self.source == BoundarySource.OBSERVED
        if observed:
            if not self.observation_ids or self.named_inference is not None:
                raise ValueError("observed boundary requires pixel provenance")
        elif (
            not self.observation_ids
            or not self.named_inference
        ):
            raise ValueError("inferred boundary requires named observed inputs")

    @property
    def outward_uncertainty_px(self) -> float:
        return max(
            self.line.offset_px - self.offset_interval_px.minimum,
            self.offset_interval_px.maximum - self.line.offset_px,
        )


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(
            points,
            points[1:] + points[:1],
            strict=True,
        )
    )


@dataclass(frozen=True)
class FramePhotoGeometry:
    geometry_id: str
    lane_id: str
    lane_ordinal: int
    top: FrameBoundaryGeometry
    bottom: FrameBoundaryGeometry
    start: FrameBoundaryGeometry
    end: FrameBoundaryGeometry
    source_polygon: tuple[tuple[float, float], ...]
    content_component_ids: tuple[str, ...]
    ownership: str

    def __post_init__(self) -> None:
        edges = (self.top, self.bottom, self.start, self.end)
        if (
            not self.geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or tuple(item.role for item in edges)
            != (
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
                BoundaryRole.START,
                BoundaryRole.END,
            )
            or len(self.source_polygon) != 4
            or any(
                not math.isfinite(value)
                for point in self.source_polygon
                for value in point
            )
            or abs(_polygon_area(self.source_polygon)) <= 1.0e-6
            or len(set(self.content_component_ids))
            != len(self.content_component_ids)
            or self.ownership
            not in {"assigned_content", "observed_empty", "unassigned"}
        ):
            raise ValueError("frame photo geometry is invalid")

    @property
    def observed_edge_count(self) -> int:
        return sum(
            edge.source == BoundarySource.OBSERVED
            for edge in (self.top, self.bottom, self.start, self.end)
        )


@dataclass(frozen=True)
class FrameAdjacencyConstraint:
    previous_lane_ordinal: int
    next_lane_ordinal: int
    kind: AdjacencyKind
    previous_end_interval_px: FiniteInterval
    next_start_interval_px: FiniteInterval
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            self.previous_lane_ordinal <= 0
            or self.next_lane_ordinal
            != self.previous_lane_ordinal + 1
            or not isinstance(self.kind, AdjacencyKind)
        ):
            raise ValueError("frame adjacency constraint is invalid")
        if (
            self.kind == AdjacencyKind.MODEL_ONLY
        ) != (not self.observation_ids):
            raise ValueError("only model-only adjacency can omit observations")


@dataclass(frozen=True)
class FrameSequenceGeometryConstraintSet:
    constraint_set_id: str
    lane_id: str
    output_slot_count: int
    authoritative_photo_count: int | None
    aperture: FrameDesignApertureMm
    aperture_label: str
    width_interval_px: PositiveInterval
    height_interval_px: PositiveInterval
    typed_gutter_interval_px: FiniteInterval
    long_boundary_observations: tuple[PhotoBoundaryObservation, ...]
    top_observations_by_ordinal: tuple[
        tuple[PhotoBoundaryObservation, ...], ...
    ]
    bottom_observations_by_ordinal: tuple[
        tuple[PhotoBoundaryObservation, ...], ...
    ]
    adjacency_constraints: tuple[FrameAdjacencyConstraint, ...]

    def __post_init__(self) -> None:
        if (
            not self.constraint_set_id
            or not self.lane_id
            or self.output_slot_count <= 0
            or (
                self.authoritative_photo_count is not None
                and (
                    self.authoritative_photo_count <= 0
                    or self.authoritative_photo_count
                    != self.output_slot_count
                )
            )
            or not self.aperture_label
            or len(self.top_observations_by_ordinal)
            != self.output_slot_count
            or len(self.bottom_observations_by_ordinal)
            != self.output_slot_count
        ):
            raise ValueError("frame sequence constraint set is incomplete")


@dataclass(frozen=True)
class FrameGeometryState:
    state_id: str
    lane_id: str
    lane_ordinal: int
    photo_geometry: FramePhotoGeometry | None
    aperture_label: str
    rotation_class_id: str
    ownership: str
    interaction_before: AdjacencyKind | None
    interaction_after: AdjacencyKind | None
    model_only: bool
    physical_residual_px: float
    measurement_uncertainty_px: float

    def __post_init__(self) -> None:
        if (
            not self.state_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or not self.aperture_label
            or not self.rotation_class_id
            or not math.isfinite(self.physical_residual_px)
            or self.physical_residual_px < 0.0
            or not math.isfinite(self.measurement_uncertainty_px)
            or self.measurement_uncertainty_px < 0.0
            or self.model_only != (self.photo_geometry is None)
        ):
            raise ValueError("complete frame geometry state is invalid")
        if (
            self.photo_geometry is not None
            and (
                self.photo_geometry.lane_id != self.lane_id
                or self.photo_geometry.lane_ordinal != self.lane_ordinal
            )
        ):
            raise ValueError("frame state geometry identity disagrees")


class PhotoSequenceTranslationOutcome(str, Enum):
    OBSERVED_ANCHOR = "observed_anchor"
    SEQUENCE_INFERRED = "sequence_inferred"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE_NO_PHOTO_GEOMETRY = (
        "not_applicable_no_photo_geometry"
    )


@dataclass(frozen=True)
class PhotoSequenceTranslationAssessment:
    outcome: PhotoSequenceTranslationOutcome
    interval_px: FiniteInterval | None
    observation_ids: tuple[ObservationId, ...]
    competing_class_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        resolved = self.outcome in {
            PhotoSequenceTranslationOutcome.OBSERVED_ANCHOR,
            PhotoSequenceTranslationOutcome.SEQUENCE_INFERRED,
        }
        if resolved != (self.interval_px is not None):
            raise ValueError("photo translation resolution is inconsistent")
        if (
            self.outcome
            == PhotoSequenceTranslationOutcome.OBSERVED_ANCHOR
            and not self.observation_ids
        ):
            raise ValueError("observed translation requires a pixel anchor")
        if (
            self.outcome
            == PhotoSequenceTranslationOutcome.UNRESOLVED
            and not self.competing_class_ids
        ):
            raise ValueError("unresolved translation requires competing classes")


class GridSlotTranslationOutcome(str, Enum):
    OBSERVED_GRID_ANCHOR = "observed_grid_anchor"
    SCAN_CANVAS_PROFILE_BOUNDED = "scan_canvas_profile_bounded"
    MODEL_BOUNDED_OUTPUT_EQUIVALENT = "model_bounded_output_equivalent"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class GridSlotTranslationAssessment:
    outcome: GridSlotTranslationOutcome
    interval_px: FiniteInterval | None
    protected_footprint_equivalence_class_id: str | None
    competing_class_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        resolved = self.outcome != GridSlotTranslationOutcome.UNRESOLVED
        if resolved != (self.interval_px is not None):
            raise ValueError("Grid slot translation resolution is inconsistent")
        if (
            self.outcome
            == GridSlotTranslationOutcome.MODEL_BOUNDED_OUTPUT_EQUIVALENT
            and not self.protected_footprint_equivalence_class_id
        ):
            raise ValueError("model-bounded Grid requires output equivalence")
        if (
            self.outcome == GridSlotTranslationOutcome.UNRESOLVED
            and not self.competing_class_ids
        ):
            raise ValueError("unresolved Grid placement needs competing classes")


class FirstPhotoStartOutcome(str, Enum):
    OBSERVED_LEADING = "observed_leading"
    SEQUENCE_INFERRED = "sequence_inferred"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class FirstPhotoStartAssessment:
    outcome: FirstPhotoStartOutcome
    lane_ordinal: int | None
    interval_px: FiniteInterval | None
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        applicable = self.outcome != FirstPhotoStartOutcome.NOT_APPLICABLE
        if applicable != (
            self.lane_ordinal is not None and self.interval_px is not None
        ):
            raise ValueError("first-photo start assessment is inconsistent")


@dataclass(frozen=True)
class SequenceWorkReceipt:
    raw_transition_count: int
    line_family_count: int
    physical_geometry_count: int
    pre_join_state_count: int
    post_join_state_count: int
    deduplicated_state_count: int
    sequence_phase_class_count: int
    dp_state_count: int
    dp_transition_count: int
    pixel_query_count: int
    shared_measurement_reuse_count: int
    peak_temporary_memory_bytes: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in asdict(self).values()):
            raise ValueError("sequence work receipt cannot be negative")


@dataclass(frozen=True)
class FrameSequenceGeometrySolution:
    solution_id: str
    lane_id: str
    aperture_label: str
    selected_states: tuple[FrameGeometryState, ...]
    undominated_states_by_ordinal: tuple[
        tuple[FrameGeometryState, ...], ...
    ]
    photo_translation: PhotoSequenceTranslationAssessment
    grid_translation: GridSlotTranslationAssessment
    first_photo_start: FirstPhotoStartAssessment
    work: SequenceWorkReceipt
    unresolved_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.solution_id
            or not self.lane_id
            or not self.aperture_label
            or len(self.selected_states)
            != len(self.undominated_states_by_ordinal)
            or len(set(self.unresolved_codes)) != len(self.unresolved_codes)
        ):
            raise ValueError("frame sequence solution is invalid")
        if tuple(
            state.lane_ordinal for state in self.selected_states
        ) != tuple(range(1, len(self.selected_states) + 1)):
            raise ValueError("selected frame states must be ordered")
        if any(
            len(states) > 3
            for states in self.undominated_states_by_ordinal
        ):
            raise ValueError("DP K exceeds two observed plus one model state")


@dataclass(frozen=True)
class SafeCropEnvelope:
    geometry_id: str
    lane_id: str
    lane_ordinal: int
    source_safe_box: Box
    source_protected_box: Box
    interpolation_allowance_source_px: float
    long_axis_protection_mm: float
    short_axis_protection_mm: float
    saturated_sides: tuple[str, ...]
    provenance: str = "photo_geometry_uncertainty_protection"

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or not self.source_safe_box.valid()
            or not self.source_protected_box.valid()
            or self.interpolation_allowance_source_px != 1.0
            or self.long_axis_protection_mm <= 0.0
            or self.short_axis_protection_mm <= 0.0
            or self.provenance
            != "photo_geometry_uncertainty_protection"
        ):
            raise ValueError("safe crop envelope is invalid")
        if (
            self.source_protected_box.left > self.source_safe_box.left
            or self.source_protected_box.top > self.source_safe_box.top
            or self.source_protected_box.right < self.source_safe_box.right
            or self.source_protected_box.bottom < self.source_safe_box.bottom
        ):
            raise ValueError("fixed protection cannot shrink source geometry")
        if any(
            side not in {"left", "top", "right", "bottom"}
            for side in self.saturated_sides
        ):
            raise ValueError("safe envelope saturation side is invalid")

    @property
    def source_sampling_box(self) -> Box:
        return self.source_protected_box


@dataclass(frozen=True)
class GridInferredBlankOutputGeometry:
    geometry_id: str
    lane_id: str
    lane_ordinal: int
    source_safe_box: Box
    source_protected_box: Box
    grid_translation: GridSlotTranslationAssessment
    saturated_sides: tuple[str, ...]
    provenance: str = "grid_inferred_blank"

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or not self.source_safe_box.valid()
            or not self.source_protected_box.valid()
            or self.grid_translation.outcome
            == GridSlotTranslationOutcome.UNRESOLVED
            or self.provenance != "grid_inferred_blank"
        ):
            raise ValueError("Grid-inferred blank output geometry is invalid")
        if (
            self.source_protected_box.left > self.source_safe_box.left
            or self.source_protected_box.top > self.source_safe_box.top
            or self.source_protected_box.right < self.source_safe_box.right
            or self.source_protected_box.bottom < self.source_safe_box.bottom
        ):
            raise ValueError("blank protection cannot shrink its slot")

    @property
    def source_sampling_box(self) -> Box:
        return self.source_protected_box


ResolvedOutputGeometry: TypeAlias = (
    SafeCropEnvelope | GridInferredBlankOutputGeometry
)


@dataclass(frozen=True)
class UndominatedFrameSequenceCandidate:
    """One complete, physically joined photo-sequence geometry class.

    These candidates remain audit-only until DecisionGate approves one unique
    safe result.  In partial-auto mode the tuple describes only the observed
    photo sequence; capacity-only blank outputs remain owned by Grid geometry.
    """

    candidate_id: str
    lane_id: str
    aperture_label: str
    hypothesis_id: str
    photo_states: tuple[FrameGeometryState, ...]
    output_geometries: tuple[SafeCropEnvelope, ...]
    output_equivalence_class_id: str
    selection_rank: tuple[float, ...]

    def __post_init__(self) -> None:
        if (
            not self.candidate_id
            or not self.lane_id
            or not self.aperture_label
            or not self.hypothesis_id
            or not self.photo_states
            or len(self.photo_states) != len(self.output_geometries)
            or not self.output_equivalence_class_id
            or any(state.model_only for state in self.photo_states)
            or any(
                state.lane_id != self.lane_id
                for state in self.photo_states
            )
            or tuple(
                state.lane_ordinal for state in self.photo_states
            )
            != tuple(
                sorted(
                    state.lane_ordinal
                    for state in self.photo_states
                )
            )
            or len(
                {
                    state.lane_ordinal
                    for state in self.photo_states
                }
            )
            != len(self.photo_states)
            or any(
                geometry.lane_id != self.lane_id
                or geometry.lane_ordinal != state.lane_ordinal
                for state, geometry in zip(
                    self.photo_states,
                    self.output_geometries,
                    strict=True,
                )
            )
        ):
            raise ValueError(
                "undominated frame sequence candidate is invalid"
            )


@dataclass(frozen=True)
class ResolvedOutputSlots:
    lane_output_slot_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.lane_output_slot_counts or any(
            value <= 0 for value in self.lane_output_slot_counts
        ):
            raise ValueError(
                "resolved output slots require one positive count per lane"
            )

    @property
    def output_slot_count(self) -> int:
        return sum(self.lane_output_slot_counts)


@dataclass(frozen=True)
class OutputSlotIdentity:
    global_output_ordinal: int
    lane_id: str
    lane_ordinal: int

    def __post_init__(self) -> None:
        if (
            self.global_output_ordinal <= 0
            or not self.lane_id
            or self.lane_ordinal <= 0
        ):
            raise ValueError("output slot identity is invalid")
