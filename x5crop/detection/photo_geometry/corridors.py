from __future__ import annotations

from dataclasses import dataclass, replace
import math

from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import (
    FRAME_DIMENSION_TOLERANCE_SPEC,
    FramePhysicalSpec,
)
from ..source_core import SourceLaneEvidence
from .model import BoundaryAxis, BoundaryRole, QueryPurpose
from .measurement_model import PhotoBoundaryMeasurementQuery
from .search_model import (
    PhotoEdgeSearchCorridor,
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorTile,
)
from .template_measurement_plan_model import (
    MeasurementIntentKind,
    TemplateMeasurementPlan,
)
from .axis_layout import source_axes
from ...run_local_identity import run_local_id


@dataclass(frozen=True)
class FramePhysicalPixelIntervals:
    frame_spec: FramePhysicalSpec
    frame_width_px: PositiveInterval
    frame_height_px: PositiveInterval


def frame_physical_pixel_intervals(
    frame_spec: FramePhysicalSpec,
    width_axis_scale_px_per_mm: PositiveInterval,
    height_axis_scale_px_per_mm: PositiveInterval,
) -> FramePhysicalPixelIntervals:
    tolerance = FRAME_DIMENSION_TOLERANCE_SPEC
    return FramePhysicalPixelIntervals(
        frame_spec=frame_spec,
        frame_width_px=PositiveInterval(
            frame_spec.frame_width_mm
            * (1.0 - tolerance.frame_width_tolerance_ratio)
            * width_axis_scale_px_per_mm.minimum,
            frame_spec.frame_width_mm
            * (1.0 + tolerance.frame_width_tolerance_ratio)
            * width_axis_scale_px_per_mm.maximum,
        ),
        frame_height_px=PositiveInterval(
            frame_spec.frame_height_mm
            * (1.0 - tolerance.frame_height_tolerance_ratio)
            * height_axis_scale_px_per_mm.minimum,
            frame_spec.frame_height_mm
            * (1.0 + tolerance.frame_height_tolerance_ratio)
            * height_axis_scale_px_per_mm.maximum,
        ),
    )


def source_lane_box(
    lane: SourceLaneEvidence,
    layout: str,
) -> Box:
    work = lane.domain.work_box
    if layout == "horizontal":
        return work
    if layout == "vertical":
        return Box(
            left=work.top,
            top=work.left,
            right=work.bottom,
            bottom=work.right,
        )
    raise ValueError(f"unsupported source layout: {layout}")


def _stable_id(prefix: str, *parts: object) -> str:
    return run_local_id(prefix, *parts)


def build_top_bottom_search_corridors(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
) -> tuple[PhotoEdgeSearchCorridor, PhotoEdgeSearchCorridor]:
    """Materialize the compiler-owned short-axis query projection."""

    if (
        measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
    ):
        raise ValueError("corridors require the compiled lane plan")
    _long_axis, short_axis = source_axes(layout)
    projected = measurement_plan.projected_queries
    return (
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                measurement_plan.plan_identity,
                BoundaryRole.TOP.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.TOP,
            boundary_axis=short_axis,
            trace_positions_px=projected.cross_trace_positions_px,
            core_intervals_px=projected.top_core_intervals_px,
            measurement_intervals_px=projected.top_measurement_intervals_px,
            measurement_halo_px=projected.measurement_halo_px,
        ),
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                measurement_plan.plan_identity,
                BoundaryRole.BOTTOM.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.BOTTOM,
            boundary_axis=short_axis,
            trace_positions_px=projected.cross_trace_positions_px,
            core_intervals_px=projected.bottom_core_intervals_px,
            measurement_intervals_px=projected.bottom_measurement_intervals_px,
            measurement_halo_px=projected.measurement_halo_px,
        ),
    )


def _tile_domain(
    lane_id: str,
    long_extent_px: int,
) -> tuple[SequenceAnchorTile, ...]:
    if long_extent_px <= 0:
        raise ValueError("anchor domain requires positive long extent")
    # The whole lane is one seamless registered discovery domain.  Local pixel
    # measurement already processes traces independently and reports actual
    # peak temporary memory; artificial millimetre tiles only duplicated seam
    # work and made an engineering partition affect physical observations.
    return (
        SequenceAnchorTile(
            tile_id=f"anchor-domain:{lane_id}",
            core_px=FiniteInterval(0.0, float(long_extent_px)),
            measurement_px=FiniteInterval(0.0, float(long_extent_px - 1)),
        ),
    )


def build_sequence_anchor_discovery_domain(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
) -> SequenceAnchorDiscoveryDomain:
    if (
        measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
    ):
        raise ValueError("anchor domain requires the compiled lane plan")
    projected = measurement_plan.projected_queries
    tiles = _tile_domain(
        lane.domain.lane_id,
        projected.long_extent_px,
    )
    query_order = tuple(tile.tile_id for tile in tiles)
    return SequenceAnchorDiscoveryDomain(
        domain_id=_stable_id(
            "sequence-anchor-domain",
            lane.domain.lane_id,
            measurement_plan.plan_identity,
        ),
        lane_id=lane.domain.lane_id,
        long_axis_extent_px=projected.long_extent_px,
        authoritative_sequence_length=measurement_plan.full_count,
        tiles=tiles,
        query_execution_order=query_order,
    )


def registered_lane_measurement_queries(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    top_corridor: PhotoEdgeSearchCorridor,
    bottom_corridor: PhotoEdgeSearchCorridor,
    anchor_domain: SequenceAnchorDiscoveryDomain,
    measurement_plan: TemplateMeasurementPlan,
    registration_start: int = 0,
) -> tuple[PhotoBoundaryMeasurementQuery, ...]:
    """Pre-register complete top/bottom and seamless anchor coverage."""

    if (
        not isinstance(measurement_plan, TemplateMeasurementPlan)
        or measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
    ):
        raise ValueError("measurement queries require the compiled lane plan")
    intent_ids = {item.kind: item.intent_id for item in measurement_plan.query_intents}

    scales = lane.scan_canvas.axis_scales
    source_long_axis, source_short_axis = source_axes(layout)
    queries: list[PhotoBoundaryMeasurementQuery] = []
    for corridor, purpose in (
        (top_corridor, QueryPurpose.TOP_CORRIDOR),
        (bottom_corridor, QueryPurpose.BOTTOM_CORRIDOR),
    ):
        queries.append(
            PhotoBoundaryMeasurementQuery(
                query_id=f"query:{measurement_plan.plan_identity}:{corridor.corridor_id}",
                registration_index=0,
                lane_id=lane.domain.lane_id,
                purpose=purpose,
                boundary_axis=source_short_axis,
                trace_positions_px=corridor.trace_positions_px,
                search_intervals_px=corridor.measurement_intervals_px,
                transition_ownership_intervals_px=(
                    corridor.measurement_intervals_px
                ),
                expected_support_px=measurement_plan.template_spec.frame_width_px.maximum,
                boundary_axis_scale_px_per_mm=(
                    scales.height_axis_px_per_mm
                ),
                trace_axis_scale_px_per_mm=(
                    scales.width_axis_px_per_mm
                ),
                measurement_halo_px=corridor.measurement_halo_px,
                search_proposal_ids=(
                    corridor.corridor_id,
                    intent_ids[
                        MeasurementIntentKind.TOP
                        if purpose == QueryPurpose.TOP_CORRIDOR
                        else MeasurementIntentKind.BOTTOM
                    ],
                ),
            )
        )
    short_traces = measurement_plan.projected_queries.sequence_trace_positions_px
    tiles_by_id = {tile.tile_id: tile for tile in anchor_domain.tiles}
    # Every tile is pre-registered before template placement begins.
    for tile_id in anchor_domain.query_execution_order:
        tile = tiles_by_id[tile_id]
        source_long_extent = (
            source_lane_box(lane, layout).right
            if source_long_axis == BoundaryAxis.X
            else source_lane_box(lane, layout).bottom
        )
        measured_interval = FiniteInterval(
            tile.measurement_px.minimum,
            min(
                float(source_long_extent - 1),
                tile.measurement_px.maximum,
            ),
        )
        owned_interval = FiniteInterval(
            tile.core_px.minimum,
            min(
                float(source_long_extent - 1),
                max(tile.core_px.minimum, tile.core_px.maximum - 1.0),
            ),
        )
        queries.append(
            PhotoBoundaryMeasurementQuery(
                query_id=f"query:{measurement_plan.plan_identity}:{anchor_domain.domain_id}:{tile.tile_id}",
                registration_index=0,
                lane_id=lane.domain.lane_id,
                purpose=QueryPurpose.SEQUENCE_ANCHOR_TILE,
                boundary_axis=source_long_axis,
                trace_positions_px=short_traces,
                search_intervals_px=tuple(
                    measured_interval for _trace in short_traces
                ),
                transition_ownership_intervals_px=tuple(
                    owned_interval for _trace in short_traces
                ),
                expected_support_px=measurement_plan.template_spec.frame_height_px.maximum,
                boundary_axis_scale_px_per_mm=(
                    scales.width_axis_px_per_mm
                ),
                trace_axis_scale_px_per_mm=(
                    scales.height_axis_px_per_mm
                ),
                measurement_halo_px=int(
                    max(
                        1.0,
                        math.ceil(
                            tile.measurement_px.width
                            - tile.core_px.width
                        ),
                    )
                ),
                search_proposal_ids=(
                    anchor_domain.domain_id,
                    tile.tile_id,
                    intent_ids[MeasurementIntentKind.OUTER_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.EARLY_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.MIDDLE_SEQUENCE_ANCHOR],
                    intent_ids[MeasurementIntentKind.LATE_SEQUENCE_ANCHOR],
                ),
            )
        )
    return tuple(
        replace(
            query,
            registration_index=registration_start + index,
        )
        for index, query in enumerate(queries)
    )
