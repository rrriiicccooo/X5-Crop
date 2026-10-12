from __future__ import annotations

from x5crop.domain import FiniteInterval, ObservationId, Box
from x5crop.detection.photo_geometry.measurement_model import (
    BroadMaterialTraceObservation,
    MaterialBackgroundSide,
)
from x5crop.detection.photo_geometry.measurement_points import TransitionPoint
from x5crop.detection.photo_geometry.model import spatial_support_region_index
from x5crop.detection.evidence.content_occupancy_model import (
    ContentOccupancyObservation,
    ContentOccupancyObservationSet,
)


def _broad_point(
    queried_traces: tuple[int, ...],
    ordinal: int,
    coordinate: float,
    *,
    identity: str | None = None,
    physical: tuple[float, float] | None = None,
    polarity: int = 1,
    background: MaterialBackgroundSide = MaterialBackgroundSide.LEFT,
    query_id: str = "query:association-contract",
) -> TransitionPoint:
    """Build an actual production broad observation at one lattice trace."""

    trace = queried_traces[ordinal]
    coordinate = float(coordinate)
    if physical is None:
        physical = (coordinate - 0.05, coordinate + 0.05)
    physical_interval = FiniteInterval(*map(float, physical))
    localization = FiniteInterval(coordinate - 0.02, coordinate + 0.02)
    if not physical_interval.contains(localization.minimum) or not physical_interval.contains(
        localization.maximum
    ):
        raise ValueError("test physical interval must contain localization interval")
    transition = BroadMaterialTraceObservation(
        transition_id=ObservationId(identity or f"assoc:{ordinal:03d}"),
        query_id=query_id,
        spatial_region_index=spatial_support_region_index(queried_traces, trace),
        trace_ordinal=ordinal,
        trace_coordinate_px=trace,
        canonical_coordinate_px=coordinate,
        localization_interval_px=localization,
        physical_position_interval_px=physical_interval,
        window_scales_mm=(1.0, 2.0),
        scale_tone_contrasts=(5.0, 4.0),
        material_contrast_z=5.0,
        material_contrast_lower_bound=4.0,
        background_uniformity_upper_bound=1.0,
        left_tone_mean=10.0,
        right_tone_mean=30.0,
        left_texture_mean=1.0,
        right_texture_mean=4.0,
        polarity=polarity,
        background_side=background,
        peak_width_px=1.0,
        prominence=5.0,
        local_noise=0.1,
    )
    return TransitionPoint(transition, float(trace), coordinate)


def make_observation(box: Box) -> ContentOccupancyObservationSet:
    identity = ObservationId(
        f"content:{box.left}:{box.top}:{box.right}:{box.bottom}"
    )
    observation = ContentOccupancyObservation(
        observation_id=identity,
        lane_id="lane:0",
        source_box=box,
        source_cells=tuple(
            Box(left, top, left + 1, top + 1)
            for left in range(box.left, box.right)
            for top in range(box.top, box.bottom)
        ),
        reliability=0.95,
    )
    return ContentOccupancyObservationSet(
        lane_id="lane:0",
        observations=(observation,),
        long_step_px=1,
        cross_step_px=1,
        long_sample_count=16,
        cross_sample_count=16,
        occupied_cell_count=box.width * box.height,
        long_support_depth_px=1,
        cross_support_depth_px=1,
    )
