from __future__ import annotations

from dataclasses import dataclass

from ...domain import (
    BoundaryAxis,
    BoundarySide,
    EvidenceState,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    MeasurementProvenance,
    PixelInterval,
    SeparatorBandObservation,
    SeparatorCrossAxisMeasurement,
)
from .model import (
    BoundaryGeometryState,
    FrameBoundarySource,
    ResolvedFrameBoundary,
)


MINIMUM_POSITIVE_PIXEL_EXTENT = 1.0


@dataclass(frozen=True)
class EdgeConstraint:
    position: PixelInterval
    basis: FrameBoundarySource
    state: EvidenceState
    geometry_state: BoundaryGeometryState
    provenance: MeasurementProvenance
    path: GrayBoundaryPathObservation | None = None
    separator: SeparatorBandObservation | None = None
    separator_cross_axis: SeparatorCrossAxisMeasurement | None = None
    external_side: BoundarySide | None = None

    def __post_init__(self) -> None:
        if self.basis == FrameBoundarySource.GRAY_PATH_OBSERVATION:
            if (
                self.path is None
                or self.separator is not None
                or self.separator_cross_axis is not None
            ):
                raise ValueError("measured frame-slot constraint requires one raw path")
            if self.path.axis != BoundaryAxis.LONG:
                raise ValueError("long-axis frame-slot constraint requires a long path")
            if self.state != EvidenceState.UNAVAILABLE:
                raise ValueError(
                    "generic gray path cannot claim a supported photo-edge role"
                )
            if not self.path.position.intersects(self.position):
                raise ValueError("measured frame-slot constraint must preserve its path")
        elif self.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION:
            if (
                self.separator is None
                or self.separator_cross_axis is None
                or self.path is not None
            ):
                raise ValueError("separator frame-slot constraint requires one band")
            if self.state not in {
                EvidenceState.UNAVAILABLE,
                EvidenceState.SUPPORTED,
            }:
                raise ValueError(
                    "separator edge role must be unavailable or supported"
                )
            if self.external_side is not None:
                if self.external_side == BoundarySide.LEADING:
                    expected = self.separator.trailing_edge
                elif self.external_side == BoundarySide.TRAILING:
                    expected = self.separator.leading_edge
                else:
                    raise ValueError(
                        "holder-adjacent separator edge requires a long-axis side"
                    )
                if self.position != expected:
                    raise ValueError(
                        "holder-adjacent band must expose its photo-facing edge"
                    )
        elif self.basis == FrameBoundarySource.DIMENSION_CONSTRAINED:
            if (
                self.separator is not None
                or self.separator_cross_axis is not None
                or self.path is not None
                or self.external_side is not None
            ):
                raise ValueError(
                    "dimension-constrained frame-slot edge cannot claim an observation"
                )
            if self.state != EvidenceState.UNAVAILABLE:
                raise ValueError("dimension-constrained frame-slot edge must be unavailable")
        else:
            raise ValueError("unsupported frame slot constraint basis")
        if not isinstance(self.geometry_state, BoundaryGeometryState):
            raise TypeError("frame-slot constraint requires typed geometry state")
        if (
            self.basis != FrameBoundarySource.DIMENSION_CONSTRAINED
            and self.geometry_state != BoundaryGeometryState.RESOLVED
        ):
            raise ValueError("observed frame-slot constraints have resolved positions")

    @property
    def measurement_quality(self) -> float:
        return self.observation_quality if self.state == EvidenceState.SUPPORTED else 0.0

    @property
    def observation_quality(self) -> float:
        if self.path is not None:
            return min(
                self.path.lower_appearance.spatial_continuity,
                self.path.upper_appearance.spatial_continuity,
            )
        if self.separator is None or self.separator_cross_axis is None:
            return 0.0
        return float(
            separator_edge_path_measurement(self).longest_supported_ratio or 0.0
        )


@dataclass(frozen=True)
class MeasuredFrameConstraint:
    leading: EdgeConstraint
    trailing: EdgeConstraint
    width_px: PixelInterval
    full_width_hypothesis_admissible: bool
    leading_holder_clip_supported: bool
    trailing_holder_clip_supported: bool
    search_order_residual: float
    frame_width_hint_residual: float = 0.0

    def allowed_at(self, frame_index: int, count: int) -> bool:
        return bool(
            self.full_width_hypothesis_admissible
            or (frame_index == 1 and self.leading_holder_clip_supported)
            or (frame_index == count and self.trailing_holder_clip_supported)
        )


def positive_interval(interval: PixelInterval) -> PixelInterval | None:
    if interval.minimum < MINIMUM_POSITIVE_PIXEL_EXTENT:
        return None
    return interval


def interval_envelope(intervals: tuple[PixelInterval, ...]) -> PixelInterval:
    if not intervals:
        raise ValueError("interval envelope requires at least one measurement")
    return PixelInterval(
        min(interval.minimum for interval in intervals),
        max(interval.maximum for interval in intervals),
    )


def interval_distance(left: PixelInterval, right: PixelInterval) -> float:
    if left.intersects(right):
        return 0.0
    if left.maximum < right.minimum:
        return right.minimum - left.maximum
    return left.minimum - right.maximum


def measurement_intervals_are_compatible(
    first: PixelInterval,
    second: PixelInterval,
) -> bool:
    if first.intersects(second):
        return True
    measurement_uncertainty = max(
        first.maximum - first.minimum,
        second.maximum - second.minimum,
    )
    return interval_distance(first, second) <= measurement_uncertainty


def interval_midpoint_residual(
    measured: PixelInterval,
    reference: PixelInterval,
) -> float:
    return abs(measured.midpoint - reference.midpoint) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        reference.midpoint,
    )


def normalized_interval_contradiction(
    measured: PixelInterval,
    reference: PixelInterval,
) -> float:
    return interval_distance(measured, reference) / max(
        MINIMUM_POSITIVE_PIXEL_EXTENT,
        reference.midpoint,
    )


def minimum_width_residual(
    width: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
) -> float:
    if not search_widths:
        raise ValueError("frame-width search requires at least one interval")
    return min(
        normalized_interval_contradiction(width, candidate)
        for candidate in search_widths
    )


def width_search_order_key(
    width: PixelInterval,
    search_widths: tuple[PixelInterval, ...],
) -> tuple[float, ...]:
    return tuple(
        interval_distance(width, candidate)
        / max(MINIMUM_POSITIVE_PIXEL_EXTENT, candidate.midpoint)
        for candidate in search_widths
    )


def largest_strict_intersection_indexes(
    intervals: tuple[PixelInterval, ...],
    minimum_count: int,
) -> tuple[int, ...]:
    if minimum_count <= 0:
        raise ValueError("strict interval group requires a positive minimum count")
    if len(intervals) < minimum_count:
        return ()
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for interval in intervals
            for coordinate in (
                interval.minimum,
                interval.midpoint,
                interval.maximum,
            )
        )
    )
    candidates: list[tuple[tuple[int, float, tuple[int, ...]], tuple[int, ...]]] = []
    for coordinate in coordinates:
        indexes = tuple(
            index
            for index, interval in enumerate(intervals)
            if interval.minimum <= coordinate <= interval.maximum
        )
        if len(indexes) < minimum_count:
            continue
        shared = PixelInterval.common_intersection(
            tuple(intervals[index] for index in indexes)
        )
        if shared is None:
            continue
        candidates.append(
            (
                (
                    len(indexes),
                    -(shared.maximum - shared.minimum),
                    tuple(-index for index in indexes),
                ),
                indexes,
            )
        )
    return () if not candidates else max(candidates, key=lambda item: item[0])[1]


def largest_measurement_compatible_interval_indexes(
    intervals: tuple[PixelInterval, ...],
    minimum_count: int,
) -> tuple[int, ...]:
    if minimum_count <= 0:
        raise ValueError("common interval group requires a positive minimum count")
    if len(intervals) < minimum_count:
        return ()
    coordinates = tuple(
        dict.fromkeys(
            coordinate
            for interval in intervals
            for coordinate in (
                interval.minimum,
                interval.midpoint,
                interval.maximum,
            )
        )
    )
    candidates: list[tuple[tuple[int, float, tuple[int, ...]], tuple[int, ...]]] = []
    for coordinate in coordinates:
        center = PixelInterval.exact(coordinate)
        indexes = tuple(
            index
            for index, interval in enumerate(intervals)
            if measurement_intervals_are_compatible(interval, center)
        )
        if len(indexes) < minimum_count:
            continue
        if any(
            not measurement_intervals_are_compatible(
                intervals[left_index],
                intervals[right_index],
            )
            for offset, left_index in enumerate(indexes)
            for right_index in indexes[offset + 1 :]
        ):
            continue
        envelope = interval_envelope(tuple(intervals[index] for index in indexes))
        candidates.append(
            (
                (
                    len(indexes),
                    -(envelope.maximum - envelope.minimum),
                    tuple(-index for index in indexes),
                ),
                indexes,
            )
        )
    return () if not candidates else max(candidates, key=lambda item: item[0])[1]


def separator_edge_path_measurement(constraint: EdgeConstraint):
    observation = constraint.separator
    measurement = constraint.separator_cross_axis
    if (
        constraint.basis != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        or observation is None
        or measurement is None
    ):
        raise ValueError("separator edge measurement requires a raw band constraint")
    if constraint.position == observation.leading_edge:
        return measurement.edge_path(BoundarySide.LEADING)
    if constraint.position == observation.trailing_edge:
        return measurement.edge_path(BoundarySide.TRAILING)
    raise ValueError("separator edge constraint must preserve one observed band edge")


def separator_edge_path_is_supported(constraint: EdgeConstraint) -> bool:
    return bool(
        constraint.basis == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
        and constraint.separator is not None
        and constraint.separator_cross_axis is not None
        and separator_edge_path_measurement(constraint).state
        == EvidenceState.SUPPORTED
    )


def visible_width(
    leading: EdgeConstraint,
    trailing: EdgeConstraint,
) -> PixelInterval | None:
    return positive_interval(trailing.position.minus(leading.position))


def boundary_matches_holder(
    boundary: ResolvedFrameBoundary,
    holder_boundary: HolderBoundaryObservation | None,
) -> bool:
    if holder_boundary is None or boundary.boundary_anchor is None:
        return False
    observation = boundary.boundary_anchor.observation
    if isinstance(observation, SeparatorBandObservation):
        band_span = PixelInterval(
            observation.leading_edge.minimum,
            observation.trailing_edge.maximum,
        )
        photo_facing_edge = (
            observation.trailing_edge
            if holder_boundary.side == BoundarySide.LEADING
            else observation.leading_edge
        )
        return bool(
            boundary.boundary_anchor.physical_role == holder_boundary.side
            and boundary.position == photo_facing_edge
            and band_span.intersects(holder_boundary.position)
        )
    return bool(
        boundary.position.intersects(holder_boundary.position)
        and boundary.measurement_provenance.observation_id
        in {
            path.provenance.observation_id
            for path in holder_boundary.supporting_paths
        }
    )
