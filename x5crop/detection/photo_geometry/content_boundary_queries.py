"""Vectorized topology queries for negative-only content interpretation."""

from __future__ import annotations

import numpy as np

from ...domain import FiniteInterval, ObservationId
from .boundary_geometry import outward_boundary_projection
from .content_topology import ContentSpanIndex, ContentTopologyIndex
from .model import (
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .output_model import FrameBoundaryGeometry


def _projected_bounds(
    boundary: FrameBoundaryGeometry | FiniteInterval,
    coordinate_minimum: np.ndarray,
    coordinate_maximum: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(boundary, FiniteInterval):
        return (
            np.full(coordinate_minimum.size, boundary.minimum),
            np.full(coordinate_minimum.size, boundary.maximum),
        )
    projection = outward_boundary_projection(boundary)
    offsets_minimum = coordinate_minimum - projection.reference_trace_px
    offsets_maximum = coordinate_maximum - projection.reference_trace_px
    values = np.stack(
        tuple(
            projection.outward_position_px + slope * offsets
            for slope in projection.slopes
            for offsets in (offsets_minimum, offsets_maximum)
        )
    )
    return np.min(values, axis=0), np.max(values, axis=0)


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


def content_cross_boundary_ids(
    content_index: ContentTopologyIndex,
    *,
    slot_core: FiniteInterval,
    boundary: FrameBoundaryGeometry | FiniteInterval,
) -> tuple[ObservationId, ...]:
    index = content_index.by_sequence
    overlap = (
        (
            index.coordinate_minimum
            >= slot_core.minimum + index.coordinate_support_depth_px
        )
        & (
            index.coordinate_maximum
            <= slot_core.maximum - index.coordinate_support_depth_px
        )
    )
    if not np.any(overlap):
        return ()
    projected_minimum, projected_maximum = _projected_bounds(
        boundary,
        index.coordinate_minimum,
        index.coordinate_maximum,
    )
    return _identities(
        index,
        overlap
        & (
            index.orthogonal_minimum + index.support_depth_px
            <= projected_minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px
            >= projected_maximum
        ),
    )


def content_sequence_boundary_ids(
    content_index: ContentTopologyIndex,
    *,
    boundary: FrameBoundaryGeometry | FiniteInterval,
    cross_core: FiniteInterval,
) -> tuple[ObservationId, ...]:
    index = content_index.by_cross
    overlap = (
        (
            index.coordinate_minimum
            >= cross_core.minimum + index.coordinate_support_depth_px
        )
        & (
            index.coordinate_maximum
            <= cross_core.maximum - index.coordinate_support_depth_px
        )
    )
    if not np.any(overlap):
        return ()
    projected_minimum, projected_maximum = _projected_bounds(
        boundary,
        index.coordinate_minimum,
        index.coordinate_maximum,
    )
    return _identities(
        index,
        overlap
        & (
            index.orthogonal_minimum + index.support_depth_px
            <= projected_minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px
            >= projected_maximum
        ),
    )


def content_occupies_sequence_core(
    content_index: ContentTopologyIndex,
    *,
    sequence_core: FiniteInterval,
    cross_core: FiniteInterval,
) -> tuple[ObservationId, ...]:
    """Require content through a positive gap in two transverse thirds."""

    index = content_index.by_cross
    mask = (
        (
            index.coordinate_minimum
            >= cross_core.minimum + index.coordinate_support_depth_px
        )
        & (
            index.coordinate_maximum
            <= cross_core.maximum - index.coordinate_support_depth_px
        )
        & (
            index.orthogonal_minimum + index.support_depth_px
            <= sequence_core.minimum
        )
        & (
            index.orthogonal_maximum - index.support_depth_px
            >= sequence_core.maximum
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


def separator_core_content_contradictions(
    content_index: ContentTopologyIndex,
    *,
    sequence_core: FiniteInterval,
    cross_core: FiniteInterval,
) -> tuple[ObservationId, ...]:
    if sequence_core.width <= 0.0 or cross_core.width <= 0.0:
        return ()
    return content_occupies_sequence_core(
        content_index,
        sequence_core=sequence_core,
        cross_core=cross_core,
    )
