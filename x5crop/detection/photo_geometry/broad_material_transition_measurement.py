"""Candidate-independent broad material changes in registered spatial regions."""

from __future__ import annotations

import numpy as np

from .cross_height_transition_measurement import (
    aligned_trace_slice,
    common_trace_coordinates,
    spatial_region_trace_ordinals,
)
from .interval_math import common
from .measurement_model import (
    BroadMaterialTransitionRegionObservation,
    MaterialBackgroundSide,
    PhotoBoundaryMeasurementQuery,
)
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
)
from .physical_identity import physical_observation_id
from .registered_transition_measurement import (
    TraceMeasurement,
    broad_material_from_scale_measurements,
    measured_broad_material_peaks,
)


BROAD_MATERIAL_AGGREGATION_REVISION = (
    "x5crop_registered_broad_material_two_scale_mean_v1"
)


def _aggregate_region(
    measurements: tuple[TraceMeasurement, ...],
) -> tuple[
    TraceMeasurement,
    tuple[np.ndarray, ...],
    tuple[np.ndarray, ...],
    int,
]:
    coordinates = common_trace_coordinates(measurements)
    if coordinates.size == 0 or any(
        item.broad_material is None for item in measurements
    ):
        empty = np.empty(0, dtype=np.float64)
        return (
            TraceMeasurement(
                empty.astype(np.int32),
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
            (),
            0,
        )
    slices = tuple(
        aligned_trace_slice(item, coordinates) for item in measurements
    )
    materials = tuple(item.broad_material for item in measurements)
    assert all(item is not None for item in materials)
    typed_materials = tuple(item for item in materials if item is not None)
    scales = typed_materials[0].window_scales_mm
    if any(item.window_scales_mm != scales for item in typed_materials[1:]):
        raise ValueError("broad material aggregates changed physical scales")

    def averaged(attribute: str) -> tuple[np.ndarray, ...]:
        values: list[np.ndarray] = []
        for scale_index in range(len(scales)):
            aggregate = np.zeros(coordinates.size, dtype=np.float64)
            for material, retained in zip(
                typed_materials,
                slices,
                strict=True,
            ):
                aggregate += getattr(material, attribute)[scale_index][retained]
            aggregate /= float(len(typed_materials))
            values.append(aggregate)
        return tuple(values)

    signed_tone = averaged("signed_tone_by_scale")
    left_tone = averaged("left_tone_by_scale")
    right_tone = averaged("right_tone_by_scale")
    left_texture = averaged("left_texture_by_scale")
    right_texture = averaged("right_texture_by_scale")
    observable = tuple(
        np.logical_and.reduce(
            tuple(
                material.observable[retained]
                for material, retained in zip(
                    typed_materials,
                    slices,
                    strict=True,
                )
            )
        )
        for _scale in scales
    )
    material = broad_material_from_scale_measurements(
        scales,
        signed_tone,
        left_tone,
        right_tone,
        left_texture,
        right_texture,
        observable,
    )
    zeros = np.zeros(coordinates.size, dtype=np.float64)
    trace = TraceMeasurement(
        coordinates=coordinates,
        gradient_z=zeros,
        tone_z=zeros.copy(),
        texture_z=zeros.copy(),
        signed_gradient=zeros.copy(),
        left_tone=zeros.copy(),
        right_tone=zeros.copy(),
        left_texture=zeros.copy(),
        right_texture=zeros.copy(),
        temporary_bytes=(
            material.temporary_bytes
            + sum(item.nbytes for item in (*signed_tone, *observable))
        ),
        broad_material=material,
    )
    polarity_by_trace = tuple(
        item.polarity[retained]
        for item, retained in zip(typed_materials, slices, strict=True)
    )
    background_by_trace = tuple(
        item.background_side[retained]
        for item, retained in zip(typed_materials, slices, strict=True)
    )
    return (
        trace,
        polarity_by_trace,
        background_by_trace,
        trace.temporary_bytes,
    )


def measure_broad_material_transition_regions(
    query: PhotoBoundaryMeasurementQuery,
    premeasured: tuple[TraceMeasurement, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    *,
    trace_ordinals: tuple[int, ...] | None = None,
) -> tuple[tuple[BroadMaterialTransitionRegionObservation, ...], int]:
    """Measure two-scale material state in three registered spatial regions."""

    if query.purpose not in {
        QueryPurpose.COARSE_STRIP_SHORT,
        QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
    }:
        return (), 0
    if len(premeasured) != len(query.trace_positions_px):
        raise ValueError("broad material aggregate requires complete traces")
    active_ordinals = (
        tuple(range(len(query.trace_positions_px)))
        if trace_ordinals is None
        else trace_ordinals
    )
    if (
        not active_ordinals
        or tuple(sorted(set(active_ordinals))) != active_ordinals
        or active_ordinals[0] < 0
        or active_ordinals[-1] >= len(query.trace_positions_px)
    ):
        raise ValueError("broad material trace view is invalid")
    regions = spatial_region_trace_ordinals(
        tuple(query.trace_positions_px[index] for index in active_ordinals)
    )
    if not regions:
        return (), 0
    observations: list[BroadMaterialTransitionRegionObservation] = []
    peak_temporary_bytes = 0
    for region_index, local_ordinals in enumerate(regions):
        ordinals = tuple(
            active_ordinals[index] for index in local_ordinals
        )
        aggregate, polarities, backgrounds, temporary = _aggregate_region(
            tuple(premeasured[index] for index in ordinals)
        )
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
        for peak in measured_broad_material_peaks(aggregate, spec):
            coordinate = float(
                aggregate.coordinates[peak.coordinate_index]
            )
            if not ownership.contains(coordinate, epsilon=1.0e-12):
                continue
            polarity_support_count = sum(
                int(values[peak.coordinate_index]) == peak.polarity
                for values in polarities
            )
            background_support_count = sum(
                int(values[peak.coordinate_index]) == peak.background_side
                for values in backgrounds
            )
            if (
                polarity_support_count <= len(ordinals) // 2
                or background_support_count <= len(ordinals) // 2
            ):
                continue
            identity = physical_observation_id(
                "broad-material-transition-region",
                BROAD_MATERIAL_AGGREGATION_REVISION,
                query.query_id,
                region_index,
                f"{peak.localization_interval.minimum:.6f}",
                f"{peak.localization_interval.maximum:.6f}",
                f"{peak.physical_position_interval.minimum:.6f}",
                f"{peak.physical_position_interval.maximum:.6f}",
            )
            observations.append(
                BroadMaterialTransitionRegionObservation(
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
                    window_scales_mm=peak.window_scales_mm,
                    scale_tone_contrasts=peak.scale_tone_contrasts,
                    material_contrast_z=peak.material_contrast_z,
                    material_contrast_lower_bound=(
                        peak.material_contrast_lower_bound
                    ),
                    background_uniformity_upper_bound=(
                        peak.background_uniformity_upper_bound
                    ),
                    left_tone_mean=peak.left_tone,
                    right_tone_mean=peak.right_tone,
                    left_texture_mean=peak.left_texture,
                    right_texture_mean=peak.right_texture,
                    polarity=peak.polarity,
                    polarity_support_count=polarity_support_count,
                    background_side=MaterialBackgroundSide(
                        "left" if peak.background_side < 0 else "right"
                    ),
                    background_side_support_count=background_support_count,
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
