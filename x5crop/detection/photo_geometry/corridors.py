from __future__ import annotations

from dataclasses import dataclass, replace
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
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
)
from .measurement_model import PhotoBoundaryMeasurementQuery
from .search_model import (
    PhotoEdgeSearchCorridor,
    SequenceAnchorDiscoveryDomain,
    SequenceAnchorTile,
)
from .axis_layout import source_axes
from .source_geometry import centered_short_axis_authority_px
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
    return run_local_id(prefix, *parts)


def build_top_bottom_search_corridors(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    aperture_pixels: FramePhysicalPixelIntervals,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoEdgeSearchCorridor, PhotoEdgeSearchCorridor]:
    """Build computation-only short-axis corridors with complete halos."""

    scales = lane.scan_canvas.axis_scales
    long_axis, short_axis = source_axes(layout)
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
    # Film is centred on the holder lane's short axis.  The shared H interval,
    # source direction and measurement halo therefore define the complete
    # search corridor; per-frame transverse translation has no authority.
    short_authority = FiniteInterval(
        float(short_min),
        float(short_max - 1),
    )
    center = centered_short_axis_authority_px(
        short_authority,
        short_scale,
    )
    height = aperture_pixels.frame_height_px
    halo = spec.measurement_halo_px(short_scale.maximum)
    top_core: list[FiniteInterval] = []
    bottom_core: list[FiniteInterval] = []
    top_measurement: list[FiniteInterval] = []
    bottom_measurement: list[FiniteInterval] = []
    for _trace in trace_positions:
        top = _clip_interval(
            FiniteInterval(
                center.minimum - height.maximum / 2.0,
                center.maximum - height.minimum / 2.0,
            ),
            float(short_min),
            float(short_max - 1),
        )
        bottom = _clip_interval(
            FiniteInterval(
                center.minimum + height.minimum / 2.0,
                center.maximum + height.maximum / 2.0,
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
    authoritative_sequence_length: int,
    aperture_pixels: FramePhysicalPixelIntervals,
) -> SequenceAnchorDiscoveryDomain:
    if authoritative_sequence_length <= 0:
        raise ValueError("anchor domain requires authoritative sequence length")
    lane_box = source_lane_box(lane, layout)
    long_axis, _short_axis = source_axes(layout)
    long_min, long_max = _axis_bounds(lane_box, long_axis)
    if long_min != 0:
        raise ValueError("current lane authority must begin at source long zero")
    tiles = _tile_domain(
        lane.domain.lane_id,
        long_max - long_min,
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
    _long_axis, short_axis = source_axes(layout)
    short_min, short_max = _axis_bounds(lane_box, short_axis)
    scales = lane.scan_canvas.axis_scales
    center = (short_min + short_max - 1) / 2.0
    half_height = min(
        (short_max - short_min - 2) / 2.0,
        aperture_pixels.frame_height_px.minimum / 2.0
        - spec.measurement_halo_px(
            scales.height_axis_px_per_mm.maximum
        ),
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
    source_long_axis, source_short_axis = source_axes(layout)
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
