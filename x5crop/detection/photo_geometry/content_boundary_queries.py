"""Vectorized topology queries against final safe crop boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...domain import FiniteInterval, ObservationId
from ...geometry.convex import ConvexPolygon
from .content_topology import ContentSpanIndex, ContentTopologyIndex
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)


_GEOMETRY_EPSILON = 1.0e-7


@dataclass(frozen=True)
class StripFootprint:
    """One final convex footprint in sequence/cross coordinates."""

    points: ConvexPolygon

    def __post_init__(self) -> None:
        if (
            len(self.points) < 3
            or any(
                not math.isfinite(value)
                for point in self.points
                for value in point
            )
        ):
            raise ValueError("content query requires a finite footprint")

    @property
    def sequence_bounds(self) -> FiniteInterval:
        return FiniteInterval(
            min(point[0] for point in self.points),
            max(point[0] for point in self.points),
        )

    @property
    def cross_bounds(self) -> FiniteInterval:
        return FiniteInterval(
            min(point[1] for point in self.points),
            max(point[1] for point in self.points),
        )


def _identities(
    index: ContentSpanIndex,
    mask: np.ndarray,
) -> tuple[ObservationId, ...]:
    return tuple(
        sorted(
            {index.observation_ids[int(value)] for value in np.flatnonzero(mask)},
            key=str,
        )
    )


def _axis_intersections(
    footprint: StripFootprint,
    coordinates: np.ndarray,
    *,
    coordinate_axis: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the convex-polygon orthogonal extent at exact coordinates."""

    lower = np.full(coordinates.shape, np.inf, dtype=np.float64)
    upper = np.full(coordinates.shape, -np.inf, dtype=np.float64)
    points = footprint.points
    for left, right in zip(points, (*points[1:], points[0]), strict=True):
        coordinate_left = left[coordinate_axis]
        coordinate_right = right[coordinate_axis]
        orthogonal_left = left[1 - coordinate_axis]
        orthogonal_right = right[1 - coordinate_axis]
        delta = coordinate_right - coordinate_left
        if abs(delta) <= _GEOMETRY_EPSILON:
            mask = np.isclose(
                coordinates,
                coordinate_left,
                rtol=0.0,
                atol=_GEOMETRY_EPSILON,
            )
            values = (orthogonal_left, orthogonal_right)
            lower[mask] = np.minimum(lower[mask], min(values))
            upper[mask] = np.maximum(upper[mask], max(values))
            continue
        mask = (
            coordinates >= min(coordinate_left, coordinate_right) - _GEOMETRY_EPSILON
        ) & (
            coordinates <= max(coordinate_left, coordinate_right) + _GEOMETRY_EPSILON
        )
        parameter = (coordinates[mask] - coordinate_left) / delta
        values = orthogonal_left + parameter * (
            orthogonal_right - orthogonal_left
        )
        lower[mask] = np.minimum(lower[mask], values)
        upper[mask] = np.maximum(upper[mask], values)
    return lower, upper


def _boundary_ranges(
    footprint: StripFootprint,
    coordinate_minimum: np.ndarray,
    coordinate_maximum: np.ndarray,
    *,
    coordinate_axis: int,
    lower_boundary: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Return one polygon branch's exact range over every coordinate cell."""

    lower_at_minimum, upper_at_minimum = _axis_intersections(
        footprint,
        coordinate_minimum,
        coordinate_axis=coordinate_axis,
    )
    lower_at_maximum, upper_at_maximum = _axis_intersections(
        footprint,
        coordinate_maximum,
        coordinate_axis=coordinate_axis,
    )
    first = lower_at_minimum if lower_boundary else upper_at_minimum
    second = lower_at_maximum if lower_boundary else upper_at_maximum
    result_minimum = np.minimum(first, second)
    result_maximum = np.maximum(first, second)

    for point in footprint.points:
        coordinate = point[coordinate_axis]
        orthogonal = point[1 - coordinate_axis]
        lower, upper = _axis_intersections(
            footprint,
            np.asarray((coordinate,), dtype=np.float64),
            coordinate_axis=coordinate_axis,
        )
        branch_value = lower[0] if lower_boundary else upper[0]
        if abs(orthogonal - branch_value) > _GEOMETRY_EPSILON:
            continue
        contains = (
            coordinate_minimum <= coordinate + _GEOMETRY_EPSILON
        ) & (
            coordinate_maximum >= coordinate - _GEOMETRY_EPSILON
        )
        result_minimum[contains] = np.minimum(
            result_minimum[contains],
            orthogonal,
        )
        result_maximum[contains] = np.maximum(
            result_maximum[contains],
            orthogonal,
        )
    return result_minimum, result_maximum


def _interior_rows(
    index: ContentSpanIndex,
    bounds: FiniteInterval,
) -> np.ndarray:
    return (
        index.coordinate_minimum
        >= bounds.minimum + index.coordinate_support_depth_px
    ) & (
        index.coordinate_maximum
        <= bounds.maximum - index.coordinate_support_depth_px
    )


def content_cross_boundary_ids(
    content_index: ContentTopologyIndex,
    *,
    footprint: StripFootprint,
    role: BoundaryRole,
) -> tuple[ObservationId, ...]:
    if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        raise ValueError("cross query requires top or bottom")
    index = content_index.by_sequence
    overlap = _interior_rows(index, footprint.sequence_bounds)
    if not np.any(overlap):
        return ()
    boundary_minimum, boundary_maximum = _boundary_ranges(
        footprint,
        index.coordinate_minimum,
        index.coordinate_maximum,
        coordinate_axis=0,
        lower_boundary=role == BoundaryRole.TOP,
    )
    return _identities(
        index,
        overlap
        & np.isfinite(boundary_minimum)
        & np.isfinite(boundary_maximum)
        & (
            index.orthogonal_minimum + index.support_depth_px
            <= boundary_minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px
            >= boundary_maximum
        ),
    )


def content_sequence_boundary_ids(
    content_index: ContentTopologyIndex,
    *,
    footprint: StripFootprint,
    role: BoundaryRole,
) -> tuple[ObservationId, ...]:
    if role not in {BoundaryRole.START, BoundaryRole.END}:
        raise ValueError("sequence query requires start or end")
    index = content_index.by_cross
    overlap = _interior_rows(index, footprint.cross_bounds)
    if not np.any(overlap):
        return ()
    boundary_minimum, boundary_maximum = _boundary_ranges(
        footprint,
        index.coordinate_minimum,
        index.coordinate_maximum,
        coordinate_axis=1,
        lower_boundary=role == BoundaryRole.START,
    )
    return _identities(
        index,
        overlap
        & np.isfinite(boundary_minimum)
        & np.isfinite(boundary_maximum)
        & (
            index.orthogonal_minimum + index.support_depth_px
            <= boundary_minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px
            >= boundary_maximum
        ),
    )


def content_occupies_sequence_core(
    content_index: ContentTopologyIndex,
    *,
    left: StripFootprint,
    right: StripFootprint,
) -> tuple[ObservationId, ...]:
    """Require content through a positive gap in two transverse thirds."""

    index = content_index.by_cross
    cross_minimum = max(
        left.cross_bounds.minimum,
        right.cross_bounds.minimum,
    )
    cross_maximum = min(
        left.cross_bounds.maximum,
        right.cross_bounds.maximum,
    )
    if cross_minimum >= cross_maximum:
        return ()
    cross_core = FiniteInterval(cross_minimum, cross_maximum)
    overlap = _interior_rows(index, cross_core)
    left_minimum, left_maximum = _boundary_ranges(
        left,
        index.coordinate_minimum,
        index.coordinate_maximum,
        coordinate_axis=1,
        lower_boundary=False,
    )
    right_minimum, right_maximum = _boundary_ranges(
        right,
        index.coordinate_minimum,
        index.coordinate_maximum,
        coordinate_axis=1,
        lower_boundary=True,
    )
    mask = (
        overlap
        & np.isfinite(left_minimum)
        & np.isfinite(left_maximum)
        & np.isfinite(right_minimum)
        & np.isfinite(right_maximum)
        & (left_maximum < right_minimum)
        & (
            index.orthogonal_minimum + index.support_depth_px <= left_minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px >= right_maximum
        )
    )
    selected = np.flatnonzero(mask)
    if selected.size == 0 or cross_core.width <= 0.0:
        return ()
    centers = np.clip(
        (
            index.coordinate_minimum[selected]
            + index.coordinate_maximum[selected]
        )
        * 0.5,
        cross_core.minimum,
        cross_core.maximum,
    )
    regions = np.minimum(
        SPATIAL_SUPPORT_REGION_COUNT - 1,
        np.floor(
            SPATIAL_SUPPORT_REGION_COUNT
            * (centers - cross_core.minimum)
            / cross_core.width
        ).astype(np.int8),
    )
    if np.unique(regions).size < MINIMUM_INDEPENDENT_SUPPORT_REGIONS:
        return ()
    return _identities(index, mask)
