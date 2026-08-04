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
from ...geometry.convex import ConvexPolygon, convex_hull, signed_area


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


class PositionSource(str, Enum):
    OBSERVED_TRANSITION = "observed_transition"
    INFERRED_OPPOSITE_EDGE = "inferred_opposite_edge"
    INFERRED_SEQUENCE = "inferred_sequence"


class DirectionAuthority(str, Enum):
    SHARED_TOP_BOTTOM_DIRECTION = "shared_top_bottom_direction"
    ORTHOGONAL_TO_SHARED_DIRECTION = "orthogonal_to_shared_direction"


class AuthoritySide(str, Enum):
    LEFT = "left"
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"


class ClippedRequirement(str, Enum):
    FULL_INTERVAL = "full_interval"
    MINIMUM_GUARD = "minimum_guard"
    VISIBLE_INTERPOLATION_GUARD = "visible_interpolation_guard"


class QueryPurpose(str, Enum):
    TOP_CORRIDOR = "top_corridor"
    BOTTOM_CORRIDOR = "bottom_corridor"
    SEQUENCE_ANCHOR_TILE = "sequence_anchor_tile"


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
    top_bottom_search_angle_degrees: float = 4.0
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
    transition_coordinate_sampling_uncertainty_px: float = 0.5
    interpolation_allowance_source_px: float = 1.0
    background_texture_ratio_minimum: float = 2.0
    background_tone_to_texture_minimum: float = 6.0
    directional_background_support_minimum: float = 0.25
    directional_role_preference_minimum: float = 0.60
    directional_sequence_support_minimum: float = 0.90

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
            self.top_bottom_search_angle_degrees,
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
            self.transition_coordinate_sampling_uncertainty_px,
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

    @property
    def contract_id(self) -> str:
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
    transition_ownership_intervals_px: tuple[FiniteInterval, ...]
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
            or len(self.trace_positions_px)
            != len(self.transition_ownership_intervals_px)
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
        if any(
            ownership.minimum < search.minimum
            or ownership.maximum > search.maximum
            for search, ownership in zip(
                self.search_intervals_px,
                self.transition_ownership_intervals_px,
                strict=True,
            )
        ):
            raise ValueError(
                "transition ownership must remain inside query coverage"
            )


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
    long_axis_extent_px: int
    authoritative_sequence_length: int
    tiles: tuple[SequenceAnchorTile, ...]
    query_execution_order: tuple[str, ...]

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
        if set(self.query_execution_order) != set(tile_ids):
            raise ValueError("query order must cover every anchor tile")
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
class SideTransitionRegion:
    """Direction-free start/end position proposal from tracked transitions."""

    region_id: str
    proposal_position_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_support_count: int
    queried_trace_count: int
    continuous_support_fraction: float
    fit_residual_px: float
    mean_gradient_z: float
    mean_tone_or_texture_z: float
    background_side_support_fraction: float
    left_background_preference_fraction: float
    right_background_preference_fraction: float
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if (
            not self.region_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or len(self.transition_ids) != self.trace_support_count
            or self.trace_support_count <= 0
            or self.queried_trace_count < self.trace_support_count
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not math.isfinite(self.mean_gradient_z)
            or self.mean_gradient_z < 0.0
            or not math.isfinite(self.mean_tone_or_texture_z)
            or self.mean_tone_or_texture_z < 0.0
            or not 0.0 <= self.background_side_support_fraction <= 1.0
            or not 0.0
            <= self.left_background_preference_fraction
            <= 1.0
            or not 0.0
            <= self.right_background_preference_fraction
            <= 1.0
        ):
            raise ValueError("side transition region is invalid")

    @property
    def measurement_uncertainty_px(self) -> float:
        return self.proposal_position_interval_px.width / 2.0


MAXIMUM_OUTPUT_ROTATION_DEGREES = 2.0


@dataclass(frozen=True)
class SharedStripDirection:
    """The sole canonical direction plus all retained angle uncertainty."""

    direction_id: str
    selected_observation_ids: tuple[ObservationId, ...]
    full_angle_interval_degrees: FiniteInterval
    canonical_angle_degrees: float

    def __post_init__(self) -> None:
        if (
            not self.direction_id
            or not self.selected_observation_ids
            or len(set(self.selected_observation_ids))
            != len(self.selected_observation_ids)
            or not self.full_angle_interval_degrees.contains(
                self.canonical_angle_degrees,
                epsilon=1.0e-12,
            )
            or abs(self.canonical_angle_degrees)
            > MAXIMUM_OUTPUT_ROTATION_DEGREES
        ):
            raise ValueError("shared strip direction is invalid")


@dataclass(frozen=True)
class FrameBoundaryGeometry:
    role: BoundaryRole
    line: SourceCoordinateLine
    reference_trace_px: float
    canonical_position_px: float
    full_position_interval_px: FiniteInterval
    full_direction_interval_degrees: FiniteInterval
    position_source: PositionSource
    position_observation_ids: tuple[ObservationId, ...]
    named_position_inference: str | None
    direction_authority: DirectionAuthority
    direction_reference_id: str

    def __post_init__(self) -> None:
        if not self.full_position_interval_px.contains(
            self.canonical_position_px,
            epsilon=1.0e-8,
        ):
            raise ValueError(
                "frame boundary interval must contain its canonical position"
            )
        if not math.isfinite(self.reference_trace_px):
            raise ValueError("frame boundary reference trace must be finite")
        observed = self.position_source == PositionSource.OBSERVED_TRANSITION
        if observed:
            if (
                not self.position_observation_ids
                or self.named_position_inference is not None
            ):
                raise ValueError("observed boundary requires pixel provenance")
        elif (
            not self.position_observation_ids
            or not self.named_position_inference
        ):
            raise ValueError("inferred boundary requires named observed inputs")
        if not self.direction_reference_id:
            raise ValueError("frame boundary requires direction provenance")
        if self.role in {BoundaryRole.START, BoundaryRole.END}:
            if (
                self.direction_authority
                != DirectionAuthority.ORTHOGONAL_TO_SHARED_DIRECTION
            ):
                raise ValueError("start/end must be orthogonal to shared direction")
        elif (
            self.direction_authority
            != DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ):
            raise ValueError("top/bottom must use shared canonical direction")

    @property
    def outward_uncertainty_px(self) -> float:
        return max(
            self.canonical_position_px
            - self.full_position_interval_px.minimum,
            self.full_position_interval_px.maximum
            - self.canonical_position_px,
        )


@dataclass(frozen=True)
class FootprintSaturationFact:
    authority_side: AuthoritySide
    clipped_requirements: tuple[ClippedRequirement, ...]

    def __post_init__(self) -> None:
        if (
            not self.clipped_requirements
            or len(set(self.clipped_requirements))
            != len(self.clipped_requirements)
        ):
            raise ValueError("saturation fact requires unique clipped facts")


def _validate_continuous_footprint(
    footprint: ConvexPolygon,
    name: str,
) -> None:
    if (
        len(footprint) < 3
        or any(
            not math.isfinite(value)
            for point in footprint
            for value in point
        )
        or signed_area(footprint) <= 1.0e-9
    ):
        raise ValueError(f"{name} must be a finite non-degenerate CCW polygon")
    if convex_hull(footprint) != footprint:
        raise ValueError(f"{name} must be an ordered convex hull")


@dataclass(frozen=True)
class SafeCropEnvelope:
    geometry_id: str
    lane_id: str
    lane_ordinal: int
    placement_source_footprint: ConvexPolygon
    required_source_footprint: ConvexPolygon
    constrained_source_footprint: ConvexPolygon
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    authority_profile_id: str
    mapped_output_box: Box | None = None
    provenance: str = "continuous_format_placement_safety_footprint"

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or not self.sampling_authority_box.valid()
            or not self.authority_profile_id
            or (
                self.mapped_output_box is not None
                and not self.mapped_output_box.valid()
            )
            or self.provenance
            != "continuous_format_placement_safety_footprint"
        ):
            raise ValueError("safe crop envelope is invalid")
        _validate_continuous_footprint(
            self.placement_source_footprint,
            "placement source footprint",
        )
        _validate_continuous_footprint(
            self.required_source_footprint,
            "required source footprint",
        )
        _validate_continuous_footprint(
            self.constrained_source_footprint,
            "constrained source footprint",
        )
        if len({fact.authority_side for fact in self.saturation_facts}) != len(
            self.saturation_facts
        ):
            raise ValueError("saturation facts require one fact per authority side")


ResolvedOutputGeometry: TypeAlias = SafeCropEnvelope


@dataclass(frozen=True)
class DirectUseBudgetEdgeAssessment:
    role: BoundaryRole
    expansion_px: float
    expansion_mm: float
    limit_mm: float
    within_limit: bool
    worst_placement_solution_id: str

    def __post_init__(self) -> None:
        if (
            self.role
            not in {
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            }
            or any(
                not math.isfinite(value) or value < 0.0
                for value in (
                    self.expansion_px,
                    self.expansion_mm,
                    self.limit_mm,
                )
            )
            or self.within_limit
            != (self.expansion_mm <= self.limit_mm)
            or not self.worst_placement_solution_id
        ):
            raise ValueError("direct-use edge assessment is invalid")


@dataclass(frozen=True)
class DirectUseBudgetAssessment:
    geometry_id: str
    placement_solution_ids: tuple[str, ...]
    edge_assessments: tuple[DirectUseBudgetEdgeAssessment, ...]
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        available = self.state != EvidenceState.UNAVAILABLE
        if (
            not self.geometry_id
            or available != bool(self.placement_solution_ids)
            or len(set(self.placement_solution_ids))
            != len(self.placement_solution_ids)
            or available != bool(self.edge_assessments)
            or (
                available
                and tuple(item.role for item in self.edge_assessments)
                != (
                    BoundaryRole.START,
                    BoundaryRole.END,
                    BoundaryRole.TOP,
                    BoundaryRole.BOTTOM,
                )
            )
            or (
                self.state == EvidenceState.SUPPORTED
                and not all(item.within_limit for item in self.edge_assessments)
            )
            or (
                self.state == EvidenceState.CONTRADICTED
                and all(item.within_limit for item in self.edge_assessments)
            )
            or (available == (self.named_gap is not None))
        ):
            raise ValueError("direct-use budget assessment is invalid")


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
