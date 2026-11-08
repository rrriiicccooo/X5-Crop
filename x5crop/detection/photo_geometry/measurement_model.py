"""Registered photo-boundary measurement field, query, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import TYPE_CHECKING

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
from .model import (
    BoundaryAxis,
    QueryPurpose,
    SPATIAL_SUPPORT_REGION_COUNT,
    spatial_support_region_index,
)
from .physical_identity import physical_fact_id
from .transition_peak_source import (
    TransitionPeakGroupSource, TransitionPeakReference, TransitionPeakTraceSource,
)

if TYPE_CHECKING:
    from .broad_material_association import BroadAssociationResult


@dataclass(frozen=True)
class PhotoBoundaryMeasurementField:
    source_gray: np.ndarray = field(repr=False, compare=False)
    layout: str
    source_rgb: np.ndarray = field(repr=False, compare=False, kw_only=True)
    source_extent: WorkspaceExtent = field(init=False)
    provenance: MeasurementProvenance = field(init=False)
    source_id: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_gray, np.ndarray)
            or self.source_gray.ndim != 2
            or self.source_gray.dtype != np.uint8
            or min(self.source_gray.shape) <= 0
        ):
            raise ValueError("photo-boundary field requires source uint8 gray")
        if (
            not isinstance(self.source_rgb, np.ndarray)
            or self.source_rgb.dtype != np.uint16
            or self.source_rgb.shape != (*self.source_gray.shape, 3)
        ):
            raise ValueError("native measurement requires canonical uint16 RGB")
        if self.layout not in {"horizontal", "vertical"}:
            raise ValueError(
                "photo-boundary field requires a canonical layout"
            )
        self.source_gray.flags.writeable = False
        self.source_rgb.flags.writeable = False
        object.__setattr__(self, "source_id", physical_fact_id("photo-boundary-field", object()))
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
                dependencies=(MeasurementIdentity.BASE_GRAY, MeasurementIdentity.NATIVE_RGB),
                description=(
                    "immutable canonical gray and native RGB with fixed "
                    "registered photo-boundary query authority"
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
    registration_provenance_ids: tuple[str, ...]

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
            or not self.registration_provenance_ids
        ):
            raise ValueError("photo-boundary query is incomplete")
        if len(set(self.registration_provenance_ids)) != len(
            self.registration_provenance_ids
        ):
            raise ValueError("registration provenance identities must be unique")
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


NATIVE_BACKGROUND_TEXTURE_REVISION = "native-rgb-rec709-two-axis-texture-v1"
NATIVE_BACKGROUND_TEXTURE_QUANTUM = 1.0


@dataclass(frozen=True)
class NativeBackgroundTextureQuery:
    """A frozen local pixel domain with no role or placement input."""

    query_id: str
    boundary_axis: BoundaryAxis
    trace_coordinate_px: int
    boundary_coordinate_px: int
    source_extent: WorkspaceExtent
    window_px: int
    gap_px: int
    trace_radius_px: int
    basis: str = NATIVE_BACKGROUND_TEXTURE_REVISION

    @property
    def requested_box(self) -> Box:
        low = self.boundary_coordinate_px - self.window_px - self.gap_px - 1
        high = self.boundary_coordinate_px + self.window_px + self.gap_px + 2
        first = self.trace_coordinate_px - self.trace_radius_px
        last = self.trace_coordinate_px + self.trace_radius_px + 1
        return (Box(first, low, last, high) if self.boundary_axis == BoundaryAxis.Y
                else Box(low, first, high, last))

    @property
    def observable(self) -> bool:
        box = self.requested_box
        return (box.left >= 0 and box.top >= 0 and box.right <= self.source_extent.width
                and box.bottom <= self.source_extent.height)

    @property
    def pixel_query_count(self) -> int:
        if not self.observable:
            return 0
        h, w = 2 * (self.window_px + self.gap_px) + 3, 2 * self.trace_radius_px + 1
        edges = h * (w - 1) + (h - 1) * w
        return 3 * h * w + 4 * edges + 8 * h + 4 * self.window_px

    @property
    def peak_temporary_bytes(self) -> int:
        if not self.observable:
            return 0
        h, w = 2 * (self.window_px + self.gap_px) + 3, 2 * self.trace_radius_px + 1
        return 32 * h * w + 64 * h

    def __post_init__(self) -> None:
        if (not isinstance(self.query_id, str) or not self.query_id or self.basis != NATIVE_BACKGROUND_TEXTURE_REVISION
                or not isinstance(self.boundary_axis, BoundaryAxis)
                or not isinstance(self.source_extent, WorkspaceExtent)
                or any(type(value) is not int or value < 0 for value in (
                    self.trace_coordinate_px, self.boundary_coordinate_px))
                or any(type(value) is not int or value <= 0 for value in (
                    self.window_px, self.gap_px, self.trace_radius_px))):
            raise ValueError("native background texture lost its registered kernel")


@dataclass(frozen=True)
class NativeBackgroundTexture:
    """A local texture fact, not a photo identity or continuity certificate."""

    query: NativeBackgroundTextureQuery
    state: EvidenceState
    left_texture_mean: float | None
    right_texture_mean: float | None

    @property
    def background_preference_side(self) -> int:
        if self.state != EvidenceState.SUPPORTED:
            return 0
        if self.left_texture_mean + NATIVE_BACKGROUND_TEXTURE_QUANTUM < self.right_texture_mean:
            return -1
        if self.right_texture_mean + NATIVE_BACKGROUND_TEXTURE_QUANTUM < self.left_texture_mean:
            return 1
        return 0

    def __post_init__(self) -> None:
        if (not isinstance(self.query, NativeBackgroundTextureQuery) or not isinstance(self.state, EvidenceState)
                or self.state not in (EvidenceState.SUPPORTED, EvidenceState.UNAVAILABLE)):
            raise ValueError("native background texture requires its registered query")
        if self.query.observable != (self.state == EvidenceState.SUPPORTED):
            raise ValueError("native background texture cannot clip its kernel")
        means = self.left_texture_mean, self.right_texture_mean
        if (self.state == EvidenceState.UNAVAILABLE and means != (None, None)) or (
                self.state == EvidenceState.SUPPORTED and any(
                    type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 2 * 65535
                    for value in means)):
            raise ValueError("native background texture has invalid native intensity units")


@dataclass(frozen=True)
class PhotoBoundaryTransition:
    transition_id: ObservationId
    query_id: str
    trace_ordinal: int
    trace_coordinate_px: int
    canonical_coordinate_px: float
    localization_interval_px: FiniteInterval
    physical_position_interval_px: FiniteInterval
    gradient_z: float
    tone_z: float
    texture_z: float
    left_tone_mean: float
    right_tone_mean: float
    left_texture_mean: float
    right_texture_mean: float
    polarity: int
    peak_width_px: float
    prominence: float
    local_noise: float
    texture_sample_coordinate_px: int | None = None
    native_background_texture: NativeBackgroundTexture | None = None
    peak_source: TransitionPeakReference | None = None

    def __post_init__(self) -> None:
        if (
            not self.query_id
            or self.trace_ordinal < 0
            or self.polarity not in {-1, 0, 1}
            or not math.isfinite(self.canonical_coordinate_px)
            or not self.localization_interval_px.contains(
                self.canonical_coordinate_px,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.minimum,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.maximum,
                epsilon=1.0e-12,
            )
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
                    self.peak_width_px,
                    self.prominence,
                    self.local_noise,
                )
            )
            or self.peak_width_px <= 0.0
        ):
            raise ValueError("photo-boundary transition is invalid")
        native = self.native_background_texture
        if native is not None and (not isinstance(native, NativeBackgroundTexture)
                or native.query.query_id != self.query_id
                or native.query.trace_coordinate_px != self.trace_coordinate_px
                or native.query.boundary_coordinate_px != self.texture_sample_coordinate_px):
            raise ValueError("native texture changed its original transition or localization")
        if self.texture_sample_coordinate_px is not None and (
                type(self.texture_sample_coordinate_px) is not int
                or not self.localization_interval_px.contains(self.texture_sample_coordinate_px, epsilon=1.0e-12)):
            raise ValueError("texture sampling coordinate left its original localization peak")
        if self.peak_source is not None and (
            not isinstance(self.peak_source, TransitionPeakReference)
            or self.peak_source.polarity != self.polarity
            or not self.physical_position_interval_px.contains(self.peak_source.source_coordinate_px)
            or self.texture_sample_coordinate_px is not None
            and self.texture_sample_coordinate_px != self.peak_source.source_coordinate_px
        ):
            raise ValueError("transition changed its original peak source")

    @property
    def coordinate_px(self) -> float:
        return self.canonical_coordinate_px

    @property
    def background_preference_side(self) -> int:
        return transition_background_preference_side(self)


def transition_background_preference_side(transition) -> int:
    native = getattr(transition, "native_background_texture", None)
    if native is not None:
        return native.background_preference_side
    return (int(transition.right_texture_mean < transition.left_texture_mean)
            - int(transition.left_texture_mean < transition.right_texture_mean))


class MaterialBackgroundSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class CrossHeightTransitionRegionObservation:
    """One fixed height-region aggregate from a registered sequence query.

    This is not a synthetic single-trace transition.  Its representative
    trace only locates the aggregate in line geometry; the complete tuple of
    contributing registered traces remains explicit provenance.
    """

    transition_id: ObservationId
    query_id: str
    spatial_region_index: int
    trace_ordinal: int
    trace_coordinate_px: int
    contributing_trace_ordinals: tuple[int, ...]
    contributing_trace_coordinates_px: tuple[int, ...]
    canonical_coordinate_px: float
    localization_interval_px: FiniteInterval
    physical_position_interval_px: FiniteInterval
    gradient_z: float
    tone_z: float
    texture_z: float
    left_tone_mean: float
    right_tone_mean: float
    left_texture_mean: float
    right_texture_mean: float
    polarity: int
    polarity_support_count: int
    peak_width_px: float
    prominence: float
    local_noise: float

    def __post_init__(self) -> None:
        numeric = (
            self.gradient_z,
            self.tone_z,
            self.texture_z,
            self.left_tone_mean,
            self.right_tone_mean,
            self.left_texture_mean,
            self.right_texture_mean,
            self.peak_width_px,
            self.prominence,
            self.local_noise,
        )
        if (
            not self.query_id
            or not 0
            <= self.spatial_region_index
            < SPATIAL_SUPPORT_REGION_COUNT
            or self.trace_ordinal < 0
            or self.polarity not in {-1, 0, 1}
            or len(self.contributing_trace_ordinals) < 2
            or tuple(sorted(set(self.contributing_trace_ordinals)))
            != self.contributing_trace_ordinals
            or len(self.contributing_trace_ordinals)
            != len(self.contributing_trace_coordinates_px)
            or tuple(sorted(set(self.contributing_trace_coordinates_px)))
            != self.contributing_trace_coordinates_px
            or self.trace_ordinal not in self.contributing_trace_ordinals
            or self.trace_coordinate_px
            not in self.contributing_trace_coordinates_px
            or not 0
            <= self.polarity_support_count
            <= len(self.contributing_trace_ordinals)
            or (
                self.polarity == 0
                and self.polarity_support_count != 0
            )
            or (
                self.polarity != 0
                and self.polarity_support_count
                <= len(self.contributing_trace_ordinals) // 2
            )
            or not math.isfinite(self.canonical_coordinate_px)
            or not self.localization_interval_px.contains(
                self.canonical_coordinate_px,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.minimum,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.maximum,
                epsilon=1.0e-12,
            )
            or any(
                not math.isfinite(value) or value < 0.0
                for value in numeric
            )
            or self.peak_width_px <= 0.0
        ):
            raise ValueError(
                "cross-height transition-region observation is invalid"
            )

    @property
    def coordinate_px(self) -> float:
        return self.canonical_coordinate_px


@dataclass(frozen=True)
class BroadMaterialTraceObservation:
    """One two-scale material peak at its actual registered trace.

    The observation is produced from the same registered sequence traces as
    local transitions.  Its polarity comes from a two-scale signed tone
    change; its background side must also remain the lower-texture side at
    both physical scales.  It is therefore not a zero-gradient alias for a
    local edge.
    """

    transition_id: ObservationId
    query_id: str
    spatial_region_index: int
    trace_ordinal: int
    trace_coordinate_px: int
    canonical_coordinate_px: float
    localization_interval_px: FiniteInterval
    physical_position_interval_px: FiniteInterval
    window_scales_mm: tuple[float, ...]
    scale_tone_contrasts: tuple[float, ...]
    material_contrast_z: float
    material_contrast_lower_bound: float
    background_uniformity_upper_bound: float
    left_tone_mean: float
    right_tone_mean: float
    left_texture_mean: float
    right_texture_mean: float
    polarity: int
    background_side: MaterialBackgroundSide
    peak_width_px: float
    prominence: float
    local_noise: float

    def __post_init__(self) -> None:
        numeric = (
            self.material_contrast_z,
            self.material_contrast_lower_bound,
            self.background_uniformity_upper_bound,
            self.left_tone_mean,
            self.right_tone_mean,
            self.left_texture_mean,
            self.right_texture_mean,
            self.peak_width_px,
            self.prominence,
            self.local_noise,
        )
        if (
            not self.query_id
            or not 0
            <= self.spatial_region_index
            < SPATIAL_SUPPORT_REGION_COUNT
            or self.trace_ordinal < 0
            or self.polarity not in {-1, 1}
            or not isinstance(self.background_side, MaterialBackgroundSide)
            or len(self.window_scales_mm) < 2
            or tuple(sorted(set(self.window_scales_mm)))
            != self.window_scales_mm
            or len(self.window_scales_mm) != len(self.scale_tone_contrasts)
            or any(
                not math.isfinite(value) or value <= 0.0
                for value in self.window_scales_mm
            )
            or any(
                not math.isfinite(value) or value <= 0.0
                for value in self.scale_tone_contrasts
            )
            or not math.isfinite(self.canonical_coordinate_px)
            or not self.localization_interval_px.contains(
                self.canonical_coordinate_px,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.minimum,
                epsilon=1.0e-12,
            )
            or not self.physical_position_interval_px.contains(
                self.localization_interval_px.maximum,
                epsilon=1.0e-12,
            )
            or any(not math.isfinite(value) or value < 0.0 for value in numeric)
            or self.material_contrast_lower_bound
            > min(self.scale_tone_contrasts) + 1.0e-9
            or self.peak_width_px <= 0.0
        ):
            raise ValueError(
                "broad material trace observation is invalid"
            )

    @property
    def coordinate_px(self) -> float:
        return self.canonical_coordinate_px

    @property
    def gradient_z(self) -> float:
        return 0.0

    @property
    def tone_z(self) -> float:
        return self.material_contrast_z

    @property
    def texture_z(self) -> float:
        return 0.0

    def validate_query(self, query: PhotoBoundaryMeasurementQuery) -> None:
        if (
            self.query_id != query.query_id
            or query.purpose not in {QueryPurpose.COARSE_STRIP_SHORT, QueryPurpose.SEQUENCE_ANCHOR_WINDOW}
            or not isinstance(self.trace_ordinal, int)
            or not 0 <= self.trace_ordinal < len(query.trace_positions_px)
            or query.trace_positions_px[self.trace_ordinal] != self.trace_coordinate_px
            or spatial_support_region_index(query.trace_positions_px, self.trace_coordinate_px)
            != self.spatial_region_index
        ):
            raise ValueError("broad material peak leaves its registered trace or region")


SequenceTransitionObservation = (
    PhotoBoundaryTransition
    | CrossHeightTransitionRegionObservation
    | BroadMaterialTraceObservation
)


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
    native_texture_query_count: int = 0
    native_texture_completed_count: int = 0
    native_texture_pixel_query_count: int = 0
    native_texture_bound_exceeded: bool = False
    peak_source_value_visit_bound: int = 0
    peak_source_group_count: int = 0
    peak_source_reference_count: int = 0
    peak_source_retained_bytes: int = 0
    peak_source_bound_exceeded: bool = False
    peak_source_capture_attempted: bool = False
    peak_source_preflight_completed: bool = False
    peak_source_planning_value_visit_bound: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.registered_trace_count,
            self.completed_trace_count,
            self.registered_coordinate_count,
            self.completed_coordinate_count,
            self.pixel_query_count,
            self.streaming_block_count,
            self.peak_temporary_bytes,
            self.native_texture_query_count,
            self.native_texture_completed_count,
            self.native_texture_pixel_query_count,
            self.peak_source_value_visit_bound,
            self.peak_source_group_count,
            self.peak_source_reference_count,
            self.peak_source_retained_bytes,
            self.peak_source_planning_value_visit_bound,
        )
        if not self.query_id or any(value < 0 for value in counts):
            raise ValueError("measurement coverage receipt is invalid")
        if (type(self.peak_source_bound_exceeded) is not bool
                or type(self.peak_source_capture_attempted) is not bool
                or type(self.peak_source_preflight_completed) is not bool
                or not self.peak_source_preflight_completed and (
                    self.peak_source_capture_attempted or self.peak_source_value_visit_bound
                    or self.peak_source_retained_bytes or self.peak_source_planning_value_visit_bound)
                or self.peak_source_group_count and not self.peak_source_capture_attempted
                or any(type(value) is not int for value in (
                    self.peak_source_value_visit_bound, self.peak_source_group_count,
                    self.peak_source_reference_count, self.peak_source_retained_bytes,
                    self.peak_source_planning_value_visit_bound))
                or self.peak_source_bound_exceeded and (self.peak_source_group_count or self.peak_source_reference_count)
                or self.peak_temporary_bytes < self.peak_source_retained_bytes):
            raise ValueError("peak source coverage exceeds its retained memory or whole-query state")
        derived = (
            self.registered_trace_count == self.completed_trace_count
            and self.registered_coordinate_count
            == self.completed_coordinate_count
            and self.native_texture_query_count == self.native_texture_completed_count
            and not self.native_texture_bound_exceeded
        )
        if (type(self.native_texture_bound_exceeded) is not bool
                or any(type(value) is not int for value in (self.native_texture_query_count,
                    self.native_texture_completed_count, self.native_texture_pixel_query_count))
                or self.native_texture_query_count > 2 * self.completed_coordinate_count
                or self.native_texture_completed_count > self.native_texture_query_count
                or self.native_texture_pixel_query_count > self.pixel_query_count):
            raise ValueError("native texture work lost its coverage bounds")
        if self.complete != derived:
            raise ValueError(
                "measurement coverage completion is inconsistent"
            )


@dataclass(frozen=True)
class CoarseAggregatePeak:
    canonical_coordinate_px: float
    physical_position_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (not math.isfinite(self.canonical_coordinate_px)
                or not isinstance(self.physical_position_interval_px, FiniteInterval)
                or not self.physical_position_interval_px.contains(self.canonical_coordinate_px)):
            raise ValueError("coarse aggregate peak lost its physical position")


@dataclass(frozen=True)
class CoarseAggregateShortEvidence:
    """All peaks from the fixed sharp-trace median, before endpoint reduction."""

    query_id: str
    trace_ordinals: tuple[int, ...]
    peaks: tuple[CoarseAggregatePeak, ...]

    def __post_init__(self) -> None:
        if (not self.query_id or not self.trace_ordinals
                or any(type(value) is not int or value < 0 for value in self.trace_ordinals)
                or tuple(sorted(set(self.trace_ordinals))) != self.trace_ordinals
                or any(not isinstance(peak, CoarseAggregatePeak) for peak in self.peaks)
                or tuple(sorted(self.peaks, key=lambda peak: peak.canonical_coordinate_px)) != self.peaks):
            raise ValueError("coarse aggregate evidence is incomplete or unordered")


@dataclass(frozen=True)
class PhotoBoundaryMeasurementSet:
    query: PhotoBoundaryMeasurementQuery
    state: EvidenceState
    transitions: tuple[PhotoBoundaryTransition, ...]
    cross_height_transitions: tuple[
        CrossHeightTransitionRegionObservation,
        ...,
    ]
    coverage: PhotoBoundaryCoverageReceipt
    broad_material_transitions: tuple[
        BroadMaterialTraceObservation,
        ...,
    ] = ()
    broad_material_association: BroadAssociationResult | None = None
    coarse_aggregate: CoarseAggregateShortEvidence | None = None
    peak_trace_sources: tuple[TransitionPeakTraceSource, ...] = ()
    peak_source_groups: tuple[TransitionPeakGroupSource, ...] = ()

    def __post_init__(self) -> None:
        if (any(not isinstance(source, TransitionPeakTraceSource) for source in self.peak_trace_sources)
                or any(not isinstance(group, TransitionPeakGroupSource) for group in self.peak_source_groups)):
            raise ValueError("measurement changed its complete peak group ledger")
        group_by_id = {group.primitive_id: group for group in self.peak_source_groups}
        if (len(group_by_id) != len(self.peak_source_groups)
                or self.coverage.peak_source_group_count != len(self.peak_source_groups)):
            raise ValueError("measurement changed its complete peak group ledger")
        trace_positions = frozenset(self.query.trace_positions_px)
        for source in (*self.peak_trace_sources, *(group.source for group in self.peak_source_groups)):
            if (source.boundary_axis != self.query.boundary_axis
                    or source.trace_coordinate_px not in trace_positions):
                raise ValueError("peak source left its original query lattice")
        references = tuple(item for item in self.transitions if item.peak_source is not None)
        minimum_bytes = (sum(source.retained_bytes for source in self.peak_trace_sources)
            + sum(group.retained_bytes for group in self.peak_source_groups)
            + sum(item.peak_source.retained_bytes for item in references))
        minimum_visits = (sum(source.signal_value_visit_count + 32 for source in self.peak_trace_sources)
            + sum(group.logical_value_visit_count + 8 * len(group.candidate_peak_coordinates_px)
                  for group in self.peak_source_groups))
        if (self.coverage.peak_source_retained_bytes < minimum_bytes
                or self.coverage.peak_source_value_visit_bound < minimum_visits):
            raise ValueError("peak source ledger lost retained memory or value work")
        if self.query.purpose != QueryPurpose.COARSE_STRIP_SHORT and self.coverage.peak_source_reference_count != len(references):
            raise ValueError("measurement changed its original peak references")
        for transition in references:
            reference = transition.peak_source
            group = group_by_id.get(reference.group_id)
            if group is None or group.source.trace_coordinate_px != transition.trace_coordinate_px:
                raise ValueError("transition lost its original measured peak group")
            reference.validate_group(group)
            candidates = group.candidate_peak_coordinates_px
            index = reference.candidate_ordinal
            low = (group.credible_group_domain_px[0] - .5 if index == 0 else
                   math.floor((candidates[index-1] + candidates[index]) / 2) + .5)
            high = (group.credible_group_domain_px[1] + .5 if index + 1 == len(candidates) else
                    math.floor((candidates[index] + candidates[index+1]) / 2) + .5)
            if transition.physical_position_interval_px != FiniteInterval(low, high):
                raise ValueError("transition changed its original polarity partition")
        if self.coarse_aggregate is not None:
            aggregate = self.coarse_aggregate
            if (not isinstance(aggregate, CoarseAggregateShortEvidence)
                    or self.state != EvidenceState.SUPPORTED
                    or self.query.purpose != QueryPurpose.COARSE_STRIP_SHORT
                    or aggregate.query_id != self.query.query_id
                    or aggregate.trace_ordinals[-1] >= len(self.query.trace_positions_px)
                    or len(set(self.query.search_intervals_px)) != 1):
                raise ValueError("coarse aggregate lost its registered measurement source")
            search = self.query.search_intervals_px[0]
            coordinate_count = max(0, math.floor(search.maximum) - math.ceil(search.minimum) + 1)
            if (len(aggregate.peaks) > coordinate_count
                    or any(not search.contains(peak.canonical_coordinate_px) for peak in aggregate.peaks)):
                raise ValueError("coarse aggregate peak leaves its single registered profile")
        if self.query.query_id != self.coverage.query_id:
            raise ValueError("measurement set query identity disagrees")
        if self.state == EvidenceState.SUPPORTED:
            if not self.coverage.complete:
                raise ValueError(
                    "supported measurement requires complete coverage"
                )
        elif (
            self.transitions
            or self.cross_height_transitions
            or self.broad_material_transitions
        ):
            raise ValueError("incomplete measurement cannot expose transitions")
        if self.cross_height_transitions and self.query.purpose != (
            QueryPurpose.SEQUENCE_ANCHOR_WINDOW
        ):
            raise ValueError(
                "cross-height transitions require a sequence window"
            )
        if self.broad_material_transitions and self.query.purpose not in {
            QueryPurpose.COARSE_STRIP_SHORT,
            QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        }:
            raise ValueError(
                "broad material regions require a registered spatial query"
            )
        identities = tuple(
            item.transition_id
            for item in (
                *self.transitions,
                *self.cross_height_transitions,
                *self.broad_material_transitions,
            )
        )
        if len(set(identities)) != len(identities):
            raise ValueError("transition identities must be unique")
        if any(
            item.query_id != self.query.query_id
            for item in (
                *self.transitions,
                *self.cross_height_transitions,
                *self.broad_material_transitions,
            )
        ):
            raise ValueError("measurement set contains a foreign transition")
        for item in self.cross_height_transitions:
            expected_coordinates = tuple(
                self.query.trace_positions_px[index]
                for index in item.contributing_trace_ordinals
            )
            if (
                expected_coordinates
                != item.contributing_trace_coordinates_px
                or self.query.trace_positions_px[item.trace_ordinal]
                != item.trace_coordinate_px
            ):
                raise ValueError(
                    "cross-height transition leaves its registered traces"
                )
        for item in self.broad_material_transitions:
            if not isinstance(item, BroadMaterialTraceObservation):
                raise ValueError("broad material requires actual trace observations")
            item.validate_query(self.query)
        if self.broad_material_association is None:
            if self.broad_material_transitions:
                raise ValueError("broad material requires a completed or bounded association receipt")
        else:
            from .broad_material_association import BroadAssociationResult

            if not isinstance(self.broad_material_association, BroadAssociationResult):
                raise TypeError("broad material requires a typed association receipt")
            self.broad_material_association.validate_query(self.query, self.broad_material_transitions)
