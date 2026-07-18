from __future__ import annotations

from dataclasses import dataclass

from ....cache import MeasurementCache, MeasurementParametersKey
from ....cache.separator import cached_separator_profile_measurement
from ....configuration.boundary import BoundaryPathParameters
from ....configuration.separator import SeparatorConfiguration
from ....domain import (
    BoundarySide,
    BoundaryMeasurementSet,
    Box,
    HolderSafetyEnvelope,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    FrameSequenceSearchScope,
)
from ...physical.boundary_detection import boundary_measurements
from ...physical.frame_sequence_construction import (
    FrameSequenceSearchIndex,
    prepare_frame_sequence_search_index,
)
from ...physical.short_axis import SharedShortAxisPlan
from ...physical.separator.observations import (
    SeparatorObservationSet,
    SeparatorSupportSet,
    measure_separator_cross_axis_support,
    propose_separator_bands,
)


@dataclass(frozen=True)
class FrameSequenceObservations:
    separator_observations: SeparatorObservationSet
    search_index: FrameSequenceSearchIndex


def cached_boundary_measurements(
    cache: MeasurementCache,
    parameters: BoundaryPathParameters,
) -> BoundaryMeasurementSet:
    key = MeasurementParametersKey(parameters)
    found = key in cache.boundary_measurements
    cache.lookup_statistics.record_lookup(found=found)
    if not found:
        cache.boundary_measurements[key] = boundary_measurements(
            cache.gray_work,
            cache.image_statistics,
            parameters,
            transform_position_uncertainty_px=(
                cache.transform_position_uncertainty_px
            ),
        )
    return cache.boundary_measurements[key]


def frame_sequence_search_scope(
    cache: MeasurementCache,
    parameters: BoundaryPathParameters,
) -> FrameSequenceSearchScope:
    measured = cached_boundary_measurements(cache, parameters)
    return FrameSequenceSearchScope(
        holder_safety=HolderSafetyEnvelope(
            measured.holder_boundaries,
            measured.containment_fallback,
        ),
        raw_boundary_paths=measured.raw_paths,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.BOUNDARY_PATHS,
            observation_id=ObservationId("frame_sequence_search_scope"),
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
                *(
                    (MeasurementIdentity.WORKSPACE_TRANSFORM,)
                    if cache.transform_position_uncertainty_px > 0.0
                    else ()
                ),
            ),
            description="count-independent frame-sequence search scope",
            boundary_anchors=tuple(
                item.provenance.observation_id
                for item in measured.holder_boundaries
            ),
        ),
    )


def _separator_measurement_corridor(
    search_scope: FrameSequenceSearchScope,
) -> Box:
    holder = search_scope.holder_safety.box
    by_side = {
        item.side: item for item in search_scope.holder_safety.boundaries
    }
    top = by_side.get(BoundarySide.TOP)
    bottom = by_side.get(BoundarySide.BOTTOM)
    corridor = Box(
        holder.left,
        int(round(top.position.maximum)) if top is not None else holder.top,
        holder.right,
        int(round(bottom.position.minimum)) if bottom is not None else holder.bottom,
    )
    return corridor if corridor.valid() else holder


def frame_sequence_observations(
    cache: MeasurementCache,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    configuration: SeparatorConfiguration,
) -> FrameSequenceObservations:
    corridor = _separator_measurement_corridor(search_scope)
    profile_measurement = cached_separator_profile_measurement(
        cache,
        corridor,
        configuration.profile,
    )
    proposed = propose_separator_bands(
        profile_measurement,
        gray_work=cache.gray_work,
        corridor=corridor,
        statistics=cache.image_statistics,
        parameters=configuration.observation,
        transform_position_uncertainty_px=(
            cache.transform_position_uncertainty_px
        ),
    )
    supports = (
        SeparatorSupportSet((), False)
        if not short_axis_plan.span.supports_safe_crop
        else measure_separator_cross_axis_support(
            proposed,
            gray_work=cache.gray_work,
            corridor=corridor,
            statistics=cache.image_statistics,
            parameters=configuration.observation,
            shared_short_axis=short_axis_plan.span,
        )
    )
    return FrameSequenceObservations(
        proposed,
        prepare_frame_sequence_search_index(search_scope, supports),
    )
