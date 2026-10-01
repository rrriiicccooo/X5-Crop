"""Two-scale broad material peaks on the existing registered trace lattice."""

from __future__ import annotations

from .cross_height_transition_measurement import spatial_region_trace_ordinals
from .measurement_model import (
    BroadMaterialTraceObservation,
    MaterialBackgroundSide,
    PhotoBoundaryMeasurementQuery,
)
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
)
from .physical_identity import physical_observation_id
from .registered_transition_measurement import TraceMeasurement, measured_broad_material_peaks


BROAD_MATERIAL_MEASUREMENT_REVISION = "x5crop_registered_broad_material_trace_v2"


def broad_material_trace_support_qualified(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
) -> bool:
    """Require actual members on a majority of each fixed region's traces."""

    regions = spatial_region_trace_ordinals(queried_traces)
    supported = set(supporting_traces)
    return bool(regions) and all(
        sum(queried_traces[index] in supported for index in region) > len(region) // 2
        for region in regions
    )


def measure_broad_material_transitions(
    query: PhotoBoundaryMeasurementQuery,
    premeasured: tuple[TraceMeasurement, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[tuple[BroadMaterialTraceObservation, ...], int]:
    """Retain actual point geometry; spatial repetition belongs to tracking.

    Averaging shifted, unequal-contrast signals cannot measure the boundary
    at a representative trace. Every interval here comes from its own trace.
    Missing traces remain in the registered lattice used for qualification.
    """

    if query.purpose not in {
        QueryPurpose.COARSE_STRIP_SHORT,
        QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
    }:
        return (), 0
    if len(premeasured) != len(query.trace_positions_px):
        raise ValueError("broad material measurement requires complete traces")
    regions = spatial_region_trace_ordinals(query.trace_positions_px)
    if not regions:
        return (), 0
    observations: list[BroadMaterialTraceObservation] = []
    peak_temporary_bytes = 0
    for region_index, ordinals in enumerate(regions):
        for ordinal in ordinals:
            measurement = premeasured[ordinal]
            # Bound masks, indices, gathered signal and median workspace by
            # eight float64-sized arrays. Retained trace arrays are owned by
            # the caller; this bound does not describe process RSS.
            peak_temporary_bytes = max(
                peak_temporary_bytes, 64 * int(measurement.coordinates.size),
            )
            ownership = query.transition_ownership_intervals_px[ordinal]
            for peak in measured_broad_material_peaks(measurement, spec):
                coordinate = float(measurement.coordinates[peak.coordinate_index])
                if not ownership.contains(coordinate, epsilon=1.0e-12):
                    continue
                identity = physical_observation_id(
                    "broad-material-trace", BROAD_MATERIAL_MEASUREMENT_REVISION,
                    query.query_id, ordinal,
                    f"{peak.localization_interval.minimum:.6f}",
                    f"{peak.localization_interval.maximum:.6f}",
                    f"{peak.physical_position_interval.minimum:.6f}",
                    f"{peak.physical_position_interval.maximum:.6f}",
                )
                observations.append(BroadMaterialTraceObservation(
                    transition_id=identity, query_id=query.query_id,
                    spatial_region_index=region_index, trace_ordinal=ordinal,
                    trace_coordinate_px=query.trace_positions_px[ordinal],
                    canonical_coordinate_px=peak.canonical_coordinate,
                    localization_interval_px=peak.localization_interval,
                    physical_position_interval_px=peak.physical_position_interval,
                    window_scales_mm=peak.window_scales_mm,
                    scale_tone_contrasts=peak.scale_tone_contrasts,
                    material_contrast_z=peak.material_contrast_z,
                    material_contrast_lower_bound=peak.material_contrast_lower_bound,
                    background_uniformity_upper_bound=peak.background_uniformity_upper_bound,
                    left_tone_mean=peak.left_tone, right_tone_mean=peak.right_tone,
                    left_texture_mean=peak.left_texture, right_texture_mean=peak.right_texture,
                    polarity=peak.polarity,
                    background_side=MaterialBackgroundSide(
                        "left" if peak.background_side < 0 else "right"
                    ),
                    peak_width_px=peak.peak_width_px,
                    prominence=peak.prominence, local_noise=peak.local_noise,
                ))
    return tuple(observations), peak_temporary_bytes
