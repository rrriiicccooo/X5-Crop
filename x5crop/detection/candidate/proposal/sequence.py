from __future__ import annotations

from ....cache import MeasurementCache
from ....configuration.boundary import BoundaryPathParameters
from ....domain import (
    BoundaryMeasurementSet,
    HolderSpan,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoSequenceSearchScope,
)
from ...physical.boundary_detection import boundary_measurements


def cached_boundary_measurements(
    cache: MeasurementCache,
    parameters: BoundaryPathParameters,
) -> BoundaryMeasurementSet:
    found = parameters in cache.boundary_measurements
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.boundary_measurements[parameters] = boundary_measurements(
            cache.gray_work,
            cache.image_statistics,
            parameters,
        )
    return cache.boundary_measurements[parameters]


def photo_sequence_search_scope(
    cache: MeasurementCache,
    parameters: BoundaryPathParameters,
) -> PhotoSequenceSearchScope:
    measured = cached_boundary_measurements(cache, parameters)
    return PhotoSequenceSearchScope(
        holder_span=HolderSpan(measured.containment_fallback.box),
        raw_boundary_paths=measured.raw_paths,
        holder_boundaries=measured.holder_boundaries,
        containment_fallback=measured.containment_fallback,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
            source="count_independent_photo_aperture_search_scope",
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
            ),
            boundary_anchors=tuple(
                f"{item.side.value}:{item.position.midpoint:.3f}"
                for item in measured.holder_boundaries
            ),
        ),
    )
