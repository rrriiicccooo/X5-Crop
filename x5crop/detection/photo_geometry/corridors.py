from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import math

from ...domain import Box, FiniteInterval, PositiveInterval
from ...formats import (
    FRAME_DIMENSION_TOLERANCE_SPEC,
    FramePhysicalSpec,
)
from ..source_core import SourceLaneEvidence
from .model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSpec,
    PhotoEdgeSearchCorridor,
    QueryPurpose,
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorTile,
)


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


def _source_axes(layout: str) -> tuple[BoundaryAxis, BoundaryAxis]:
    if layout == "horizontal":
        return BoundaryAxis.X, BoundaryAxis.Y
    if layout == "vertical":
        return BoundaryAxis.Y, BoundaryAxis.X
    raise ValueError(f"unsupported source layout: {layout}")


def _axis_bounds(
    box: Box,
    axis: BoundaryAxis,
) -> tuple[int, int]:
    return (
        (box.left, box.right)
        if axis == BoundaryAxis.X
        else (box.top, box.bottom)
    )


def _lattice_positions(
    minimum: int,
    maximum: int,
    spacing_px: float,
) -> tuple[int, ...]:
    if maximum <= minimum:
        return ()
    step = max(1, int(round(spacing_px)))
    first = min(maximum - 1, minimum + step // 2)
    values = list(range(first, maximum, step))
    if not values:
        values = [(minimum + maximum - 1) // 2]
    if values[-1] < maximum - 1 - step // 2:
        values.append(maximum - 1)
    return tuple(sorted(set(values)))


def _clip_interval(
    interval: FiniteInterval,
    minimum: float,
    maximum: float,
) -> FiniteInterval:
    return FiniteInterval(
        max(minimum, interval.minimum),
        min(maximum, interval.maximum),
    )


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def build_top_bottom_search_corridors(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    aperture_pixels: FramePhysicalPixelIntervals,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoEdgeSearchCorridor, PhotoEdgeSearchCorridor]:
    """Build computation-only short-axis corridors with complete halos."""

    scales = lane.scan_canvas.axis_scales
    long_axis, short_axis = _source_axes(layout)
    lane_box = source_lane_box(lane, layout)
    long_min, long_max = _axis_bounds(lane_box, long_axis)
    short_min, short_max = _axis_bounds(lane_box, short_axis)
    long_scale = scales.width_axis_px_per_mm
    short_scale = scales.height_axis_px_per_mm
    spacing_mm = spec.lattice_spacing_mm(
        aperture_pixels.frame_spec.frame_width_mm
    )
    trace_positions = _lattice_positions(
        long_min,
        long_max,
        spacing_mm * long_scale.maximum,
    )
    center = (short_min + short_max - 1) / 2.0
    center_allowance = (
        spec.center_offset_allowance_mm * short_scale.maximum
    )
    search_deviation = (
        spec.dimension_search_allowance_mm * short_scale.maximum
    )
    halo = (
        int(
            math.ceil(
                (
                    spec.local_window_mm
                    + spec.dimension_search_allowance_mm
                    + spec.transition_gap_mm
                )
                * short_scale.maximum
            )
        )
        + 1
    )
    u0 = (long_min + long_max - 1) / 2.0
    top_core: list[FiniteInterval] = []
    bottom_core: list[FiniteInterval] = []
    top_measurement: list[FiniteInterval] = []
    bottom_measurement: list[FiniteInterval] = []
    for trace in trace_positions:
        rotation_radius = abs(float(trace) - u0) * math.tan(
            math.radians(spec.top_bottom_search_angle_degrees)
        )
        top = _clip_interval(
            FiniteInterval(
                center
                - center_allowance
                - aperture_pixels.frame_height_px.maximum / 2.0
                - search_deviation
                - rotation_radius,
                center
                + center_allowance
                - aperture_pixels.frame_height_px.minimum / 2.0
                + search_deviation
                + rotation_radius,
            ),
            float(short_min),
            float(short_max - 1),
        )
        bottom = _clip_interval(
            FiniteInterval(
                center
                - center_allowance
                + aperture_pixels.frame_height_px.minimum / 2.0
                - search_deviation
                - rotation_radius,
                center
                + center_allowance
                + aperture_pixels.frame_height_px.maximum / 2.0
                + search_deviation
                + rotation_radius,
            ),
            float(short_min),
            float(short_max - 1),
        )
        top_core.append(top)
        bottom_core.append(bottom)
        top_measurement.append(
            _clip_interval(
                FiniteInterval(top.minimum - halo, top.maximum + halo),
                float(short_min),
                float(short_max - 1),
            )
        )
        bottom_measurement.append(
            _clip_interval(
                FiniteInterval(
                    bottom.minimum - halo,
                    bottom.maximum + halo,
                ),
                float(short_min),
                float(short_max - 1),
            )
        )
    return (
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                aperture_pixels.frame_spec,
                BoundaryRole.TOP.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.TOP,
            boundary_axis=short_axis,
            trace_positions_px=trace_positions,
            core_intervals_px=tuple(top_core),
            measurement_intervals_px=tuple(top_measurement),
            measurement_halo_px=halo,
        ),
        PhotoEdgeSearchCorridor(
            corridor_id=_stable_id(
                "photo-edge-corridor",
                lane.domain.lane_id,
                aperture_pixels.frame_spec,
                BoundaryRole.BOTTOM.value,
            ),
            lane_id=lane.domain.lane_id,
            role=BoundaryRole.BOTTOM,
            boundary_axis=short_axis,
            trace_positions_px=trace_positions,
            core_intervals_px=tuple(bottom_core),
            measurement_intervals_px=tuple(bottom_measurement),
            measurement_halo_px=halo,
        ),
    )


def _tile_domain(
    lane_id: str,
    long_extent_px: int,
    tile_width_px: float,
    halo_px: int,
) -> tuple[SequenceAnchorTile, ...]:
    if long_extent_px <= 0:
        raise ValueError("anchor domain requires positive long extent")
    width = max(1, int(math.ceil(tile_width_px)))
    tiles: list[SequenceAnchorTile] = []
    start = 0
    ordinal = 0
    while start < long_extent_px:
        stop = min(long_extent_px, start + width)
        tiles.append(
            SequenceAnchorTile(
                tile_id=f"anchor-tile:{lane_id}:{ordinal:04d}",
                core_px=FiniteInterval(float(start), float(stop)),
                measurement_px=FiniteInterval(
                    float(max(0, start - halo_px)),
                    float(min(long_extent_px - 1, stop + halo_px)),
                ),
            )
        )
        start = stop
        ordinal += 1
    return tuple(tiles)


def build_sequence_anchor_discovery_domain(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    authoritative_sequence_length: int,
    aperture_pixels: FramePhysicalPixelIntervals,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> SequenceAnchorDiscoveryDomain:
    if authoritative_sequence_length <= 0:
        raise ValueError("anchor domain requires authoritative sequence length")
    lane_box = source_lane_box(lane, layout)
    long_axis, short_axis = _source_axes(layout)
    long_min, long_max = _axis_bounds(lane_box, long_axis)
    short_min, short_max = _axis_bounds(lane_box, short_axis)
    if long_min != 0:
        raise ValueError("current lane authority must begin at source long zero")
    scales = lane.scan_canvas.axis_scales
    measurement_halo = (
        int(
            math.ceil(
                0.5
                * (short_max - short_min)
                * math.tan(
                    math.radians(spec.top_bottom_search_angle_degrees)
                )
                + (
                    spec.local_window_mm
                    + spec.transition_gap_mm
                )
                * scales.width_axis_px_per_mm.maximum
            )
        )
        + 1
    )
    tiles = _tile_domain(
        lane.domain.lane_id,
        long_max - long_min,
        spec.anchor_tile_width_mm
        * scales.width_axis_px_per_mm.maximum,
        measurement_halo,
    )
    query_order = tuple(tile.tile_id for tile in tiles)
    return SequenceAnchorDiscoveryDomain(
        domain_id=_stable_id(
            "sequence-anchor-domain",
            lane.domain.lane_id,
            authoritative_sequence_length,
            aperture_pixels.frame_spec,
        ),
        lane_id=lane.domain.lane_id,
        long_axis_extent_px=long_max - long_min,
        authoritative_sequence_length=authoritative_sequence_length,
        tiles=tiles,
        query_execution_order=query_order,
    )


def _coarse_short_trace_positions(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    aperture_pixels: FramePhysicalPixelIntervals,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[int, ...]:
    lane_box = source_lane_box(lane, layout)
    _long_axis, short_axis = _source_axes(layout)
    short_min, short_max = _axis_bounds(lane_box, short_axis)
    scales = lane.scan_canvas.axis_scales
    center = (short_min + short_max - 1) / 2.0
    half_height = min(
        (short_max - short_min - 2) / 2.0,
        aperture_pixels.frame_height_px.minimum / 2.0
        - spec.local_window_mm
        * scales.height_axis_px_per_mm.maximum,
    )
    inner_min = max(short_min, int(math.ceil(center - half_height)))
    inner_max = min(short_max, int(math.floor(center + half_height)) + 1)
    spacing_mm = spec.lattice_spacing_mm(
        aperture_pixels.frame_spec.frame_height_mm
    )
    return _lattice_positions(
        inner_min,
        inner_max,
        spacing_mm * scales.height_axis_px_per_mm.maximum,
    )


def registered_lane_measurement_queries(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    aperture_pixels: FramePhysicalPixelIntervals,
    top_corridor: PhotoEdgeSearchCorridor,
    bottom_corridor: PhotoEdgeSearchCorridor,
    anchor_domain: SequenceAnchorDiscoveryDomain,
    registration_start: int = 0,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoBoundaryMeasurementQuery, ...]:
    """Pre-register complete top/bottom and seamless anchor coverage."""

    scales = lane.scan_canvas.axis_scales
    source_long_axis, source_short_axis = _source_axes(layout)
    queries: list[PhotoBoundaryMeasurementQuery] = []
    for corridor, purpose in (
        (top_corridor, QueryPurpose.TOP_CORRIDOR),
        (bottom_corridor, QueryPurpose.BOTTOM_CORRIDOR),
    ):
        queries.append(
            PhotoBoundaryMeasurementQuery(
                query_id=f"query:{corridor.corridor_id}",
                registration_index=0,
                lane_id=lane.domain.lane_id,
                purpose=purpose,
                boundary_axis=source_short_axis,
                trace_positions_px=corridor.trace_positions_px,
                search_intervals_px=corridor.measurement_intervals_px,
                transition_ownership_intervals_px=(
                    corridor.measurement_intervals_px
                ),
                expected_support_px=aperture_pixels.frame_width_px.maximum,
                boundary_axis_scale_px_per_mm=(
                    scales.height_axis_px_per_mm
                ),
                trace_axis_scale_px_per_mm=(
                    scales.width_axis_px_per_mm
                ),
                measurement_halo_px=corridor.measurement_halo_px,
                search_proposal_ids=(corridor.corridor_id,),
            )
        )
    short_traces = _coarse_short_trace_positions(
        lane,
        layout=layout,
        aperture_pixels=aperture_pixels,
        spec=spec,
    )
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
                query_id=f"query:{anchor_domain.domain_id}:{tile.tile_id}",
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
                expected_support_px=aperture_pixels.frame_height_px.maximum,
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
