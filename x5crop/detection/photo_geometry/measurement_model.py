"""Registered photo-boundary measurement field, query, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

import numpy as np

from ...domain import (
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
)


@dataclass(frozen=True)
class PhotoBoundaryMeasurementField:
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
            raise ValueError(
                "photo-boundary field requires a canonical layout"
            )
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

    @property
    def coordinate_px(self) -> float:
        return self.canonical_coordinate_px


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
class BroadMaterialTransitionRegionObservation:
    """One registered spatial region supporting a broad material boundary.

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
    contributing_trace_ordinals: tuple[int, ...]
    contributing_trace_coordinates_px: tuple[int, ...]
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
    polarity_support_count: int
    background_side: MaterialBackgroundSide
    background_side_support_count: int
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
        support_count = len(self.contributing_trace_ordinals)
        if (
            not self.query_id
            or not 0
            <= self.spatial_region_index
            < SPATIAL_SUPPORT_REGION_COUNT
            or self.trace_ordinal < 0
            or self.polarity not in {-1, 1}
            or support_count < 2
            or tuple(sorted(set(self.contributing_trace_ordinals)))
            != self.contributing_trace_ordinals
            or support_count != len(self.contributing_trace_coordinates_px)
            or tuple(sorted(set(self.contributing_trace_coordinates_px)))
            != self.contributing_trace_coordinates_px
            or self.trace_ordinal not in self.contributing_trace_ordinals
            or self.trace_coordinate_px
            not in self.contributing_trace_coordinates_px
            or not support_count // 2
            < self.polarity_support_count
            <= support_count
            or not support_count // 2
            < self.background_side_support_count
            <= support_count
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
                "broad material transition-region observation is invalid"
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


SequenceTransitionObservation = (
    PhotoBoundaryTransition
    | CrossHeightTransitionRegionObservation
    | BroadMaterialTransitionRegionObservation
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
            raise ValueError(
                "measurement coverage completion is inconsistent"
            )


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
        BroadMaterialTransitionRegionObservation,
        ...,
    ] = ()

    def __post_init__(self) -> None:
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
        for item in (
            *self.cross_height_transitions,
            *self.broad_material_transitions,
        ):
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
