"""Candidate-independent weak sequence transitions joined across height."""

from __future__ import annotations

import numpy as np

from ..robust_statistics import (
    REGISTERED_UINT8_QUANTIZATION_STEP,
    positive_mad_z,
)
from .interval_math import common
from .measurement_model import (
    CrossHeightTransitionRegionObservation,
    PhotoBoundaryMeasurementQuery,
)
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SPATIAL_SUPPORT_REGION_COUNT,
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
    spatial_support_region_index,
)
from .physical_identity import physical_observation_id
from .registered_transition_measurement import (
    TraceMeasurement,
    measured_transition_peaks,
)


CROSS_HEIGHT_AGGREGATION_REVISION = (
    "x5crop_registered_cross_height_signed_mean_v1"
)


def spatial_region_trace_ordinals(
    trace_positions_px: tuple[int, ...],
) -> tuple[tuple[int, ...], ...]:
    """Partition one fixed trace lattice into the canonical three regions."""

    values = tuple(
        tuple(
            ordinal
            for ordinal, trace in enumerate(trace_positions_px)
            if spatial_support_region_index(trace_positions_px, trace)
            == region_index
        )
        for region_index in range(SPATIAL_SUPPORT_REGION_COUNT)
    )
    if any(len(region) < 2 for region in values):
        return ()
    return values


def common_trace_coordinates(
    measurements: tuple[TraceMeasurement, ...],
) -> np.ndarray:
    if any(item.coordinates.size == 0 for item in measurements):
        return np.empty(0, dtype=np.int32)
    lower = max(int(item.coordinates[0]) for item in measurements)
    upper = min(int(item.coordinates[-1]) for item in measurements)
    if upper < lower:
        return np.empty(0, dtype=np.int32)
    return np.arange(lower, upper + 1, dtype=np.int32)


def aligned_trace_slice(
    measurement: TraceMeasurement,
    coordinates: np.ndarray,
) -> slice:
    start = int(measurement.coordinates.searchsorted(coordinates[0]))
    stop = start + int(coordinates.size)
    if (
        stop > measurement.coordinates.size
        or not np.array_equal(
            measurement.coordinates[start:stop],
            coordinates,
        )
    ):
        raise ValueError("cross-height aggregate lost coordinate alignment")
    return slice(start, stop)


def _aggregate_region(
    measurements: tuple[TraceMeasurement, ...],
) -> tuple[TraceMeasurement, tuple[np.ndarray, ...], int]:
    coordinates = common_trace_coordinates(measurements)
    if coordinates.size == 0:
        empty = np.empty(0, dtype=np.float64)
        return (
            TraceMeasurement(
                coordinates,
                empty,
                empty.copy(),
                empty.copy(),
                empty.copy(),
                empty.copy(),
                empty.copy(),
                empty.copy(),
                empty.copy(),
                0,
            ),
            (),
            0,
        )
    slices = tuple(aligned_trace_slice(item, coordinates) for item in measurements)
    signed_values = tuple(
        item.signed_gradient[retained]
        for item, retained in zip(measurements, slices, strict=True)
    )
    signed_gradient = np.zeros(coordinates.size, dtype=np.float64)
    left_tone = np.zeros_like(signed_gradient)
    right_tone = np.zeros_like(signed_gradient)
    left_texture = np.zeros_like(signed_gradient)
    right_texture = np.zeros_like(signed_gradient)
    for item, retained in zip(measurements, slices, strict=True):
        signed_gradient += item.signed_gradient[retained]
        left_tone += item.left_tone[retained]
        right_tone += item.right_tone[retained]
        left_texture += item.left_texture[retained]
        right_texture += item.right_texture[retained]
    divisor = float(len(measurements))
    signed_gradient /= divisor
    left_tone /= divisor
    right_tone /= divisor
    left_texture /= divisor
    right_texture /= divisor
    gradient = np.abs(signed_gradient)
    tone = np.abs(right_tone - left_tone)
    texture = np.abs(right_texture - left_texture)
    gradient_z = positive_mad_z(
        gradient,
        minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
    )
    tone_z = positive_mad_z(
        tone,
        minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
    )
    texture_z = positive_mad_z(
        texture,
        minimum_scale=REGISTERED_UINT8_QUANTIZATION_STEP,
    )
    temporary = sum(
        item.nbytes
        for item in (
            coordinates,
            signed_gradient,
            left_tone,
            right_tone,
            left_texture,
            right_texture,
            gradient,
            tone,
            texture,
            gradient_z,
            tone_z,
            texture_z,
        )
    )
    return (
        TraceMeasurement(
            coordinates=coordinates,
            gradient_z=gradient_z,
            tone_z=tone_z,
            texture_z=texture_z,
            signed_gradient=signed_gradient,
            left_tone=left_tone,
            right_tone=right_tone,
            left_texture=left_texture,
            right_texture=right_texture,
            temporary_bytes=temporary,
        ),
        signed_values,
        temporary,
    )


def measure_cross_height_transition_regions(
    query: PhotoBoundaryMeasurementQuery,
    premeasured: tuple[TraceMeasurement, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[tuple[CrossHeightTransitionRegionObservation, ...], int]:
    """Aggregate the already registered traces without another pixel read.

    Signed means make opposite-polarity structures cancel instead of becoming
    support.  Existing robust-z and peak-localization contracts then operate
    on each fixed height region.  The result remains role- and placement-free.
    """

    if query.purpose != QueryPurpose.SEQUENCE_ANCHOR_WINDOW:
        return (), 0
    if len(premeasured) != len(query.trace_positions_px):
        raise ValueError("cross-height aggregate requires complete trace input")
    regions = spatial_region_trace_ordinals(query.trace_positions_px)
    if not regions:
        return (), 0
    observations: list[CrossHeightTransitionRegionObservation] = []
    peak_temporary_bytes = 0
    for region_index, ordinals in enumerate(regions):
        measurements = tuple(premeasured[index] for index in ordinals)
        aggregate, signed_values, temporary = _aggregate_region(measurements)
        peak_temporary_bytes = max(peak_temporary_bytes, temporary)
        if aggregate.coordinates.size == 0:
            continue
        ownership = common(
            tuple(
                query.transition_ownership_intervals_px[index]
                for index in ordinals
            )
        )
        if ownership is None:
            continue
        representative_ordinal = ordinals[len(ordinals) // 2]
        for peak in measured_transition_peaks(
            aggregate,
            spec,
            split_gradient_reversals=False,
        ):
            coordinate = float(
                aggregate.coordinates[peak.coordinate_index]
            )
            if not ownership.contains(coordinate, epsilon=1.0e-12):
                continue
            polarity_support_count = (
                0
                if peak.polarity == 0
                else sum(
                    int(np.sign(values[peak.coordinate_index]))
                    == peak.polarity
                    for values in signed_values
                )
            )
            if (
                peak.polarity != 0
                and polarity_support_count <= len(ordinals) // 2
            ):
                continue
            identity = physical_observation_id(
                "cross-height-transition-region",
                CROSS_HEIGHT_AGGREGATION_REVISION,
                query.query_id,
                region_index,
                f"{peak.localization_interval.minimum:.6f}",
                f"{peak.localization_interval.maximum:.6f}",
                f"{peak.physical_position_interval.minimum:.6f}",
                f"{peak.physical_position_interval.maximum:.6f}",
            )
            observations.append(
                CrossHeightTransitionRegionObservation(
                    transition_id=identity,
                    query_id=query.query_id,
                    spatial_region_index=region_index,
                    trace_ordinal=representative_ordinal,
                    trace_coordinate_px=query.trace_positions_px[
                        representative_ordinal
                    ],
                    contributing_trace_ordinals=ordinals,
                    contributing_trace_coordinates_px=tuple(
                        query.trace_positions_px[index]
                        for index in ordinals
                    ),
                    canonical_coordinate_px=peak.canonical_coordinate,
                    localization_interval_px=peak.localization_interval,
                    physical_position_interval_px=(
                        peak.physical_position_interval
                    ),
                    gradient_z=peak.gradient_z,
                    tone_z=peak.tone_z,
                    texture_z=peak.texture_z,
                    left_tone_mean=peak.left_tone,
                    right_tone_mean=peak.right_tone,
                    left_texture_mean=peak.left_texture,
                    right_texture_mean=peak.right_texture,
                    polarity=peak.polarity,
                    polarity_support_count=polarity_support_count,
                    peak_width_px=peak.peak_width_px,
                    prominence=peak.prominence,
                    local_noise=peak.local_noise,
                )
            )
    return (
        tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.spatial_region_index,
                    item.canonical_coordinate_px,
                    str(item.transition_id),
                ),
            )
        ),
        peak_temporary_bytes,
    )
