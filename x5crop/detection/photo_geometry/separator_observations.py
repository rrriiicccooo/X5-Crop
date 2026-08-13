"""Direct separator-band observations from paired physical edge families."""

from __future__ import annotations

import math

import numpy as np

from ...domain import FiniteInterval, ObservationId
from ...run_local_identity import run_local_id
from .model import (
    BoundaryAxis,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    independent_spatial_support_count,
    spatial_support_region_index,
)
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryTransition,
)
from .observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    ProfileRun,
    SeparatorBandObservation,
    SeparatorMaterialRegionObservation,
)
from .separator_material import repeated_dark_material_supported


def _separator_core_material(
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
    *,
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
    transitions: dict[str, PhotoBoundaryTransition],
    trace_coordinates_px: tuple[int, ...],
) -> tuple[tuple[int, float, float], ...] | None:
    """Measure the whole directly visible band, not only its two edges."""

    left_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in left.transition_ids
    }
    right_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in right.transition_ids
    }
    samples: list[tuple[int, float, float]] = []
    for trace in trace_coordinates_px:
        start = int(math.ceil(left_by_trace[trace].canonical_coordinate_px))
        stop = int(math.floor(right_by_trace[trace].canonical_coordinate_px)) + 1
        if stop - start < 2:
            continue
        if boundary_axis == BoundaryAxis.X:
            if not 0 <= trace < field.source_gray.shape[0]:
                continue
            values = field.source_gray[trace, start:stop]
        else:
            if not 0 <= trace < field.source_gray.shape[1]:
                continue
            values = field.source_gray[start:stop, trace]
        if values.size < 2:
            continue
        numeric = values.astype(np.float64, copy=False)
        samples.append(
            (
                trace,
                float(np.mean(numeric)),
                float(np.mean(np.abs(np.diff(numeric)))),
            )
        )
    return None if not samples else tuple(samples)


def _separator_band_from_edges(
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
    *,
    profile: BasicAxisProfile,
    runs_by_id: dict[str, ProfileRun],
    transitions: dict[str, PhotoBoundaryTransition],
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
) -> SeparatorBandObservation | None:
    """Build one directly observed band from two physical edge families."""

    if (
        left.coordinate_interval_px.center
        >= right.coordinate_interval_px.center
        or left.polarity != -1
        or right.polarity != 1
    ):
        return None
    shared_traces = tuple(
        sorted(set(left.trace_coordinates_px) & set(right.trace_coordinates_px))
    )
    support_region_count = independent_spatial_support_count(
        profile.trace_coordinates_px,
        shared_traces,
    )
    if support_region_count < MINIMUM_INDEPENDENT_SUPPORT_REGIONS:
        return None
    gap = FiniteInterval(
        max(
            0.0,
            right.coordinate_interval_px.minimum
            - left.coordinate_interval_px.maximum,
        ),
        max(
            0.0,
            right.coordinate_interval_px.maximum
            - left.coordinate_interval_px.minimum,
        ),
    )
    left_run = runs_by_id[left.run_id]
    right_run = runs_by_id[right.run_id]
    material = _separator_core_material(
        left,
        right,
        field=field,
        boundary_axis=boundary_axis,
        transitions=transitions,
        trace_coordinates_px=shared_traces,
    )
    if material is None:
        return None
    material_support_region_count = independent_spatial_support_count(
        profile.trace_coordinates_px,
        tuple(item[0] for item in material),
    )
    if material_support_region_count < MINIMUM_INDEPENDENT_SUPPORT_REGIONS:
        return None
    left_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in left_run.transition_ids
    }
    right_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in right_run.transition_ids
    }
    darkness_samples = tuple(
        max(
            0.0,
            min(
                left_by_trace[trace].left_tone_mean,
                right_by_trace[trace].right_tone_mean,
            )
            - core_tone,
        )
        for trace, core_tone, _core_texture in material
    )
    texture_samples = tuple(
        max(
            0.0,
            min(
                left_by_trace[trace].left_texture_mean,
                right_by_trace[trace].right_texture_mean,
            )
            - core_texture,
        )
        for trace, _core_tone, core_texture in material
    )
    samples_by_region: dict[int, list[tuple[float, float]]] = {}
    for (trace, _core_tone, _core_texture), darkness, texture in zip(
        material,
        darkness_samples,
        texture_samples,
        strict=True,
    ):
        region_index = spatial_support_region_index(
            profile.trace_coordinates_px,
            trace,
        )
        samples_by_region.setdefault(region_index, []).append(
            (darkness, texture)
        )
    material_regions = tuple(
        SeparatorMaterialRegionObservation(
            region_index=region_index,
            sample_count=len(values),
            darkness_contrast_interval=FiniteInterval(
                min(item[0] for item in values),
                max(item[0] for item in values),
            ),
            texture_contrast_interval=FiniteInterval(
                min(item[1] for item in values),
                max(item[1] for item in values),
            ),
        )
        for region_index, values in sorted(samples_by_region.items())
    )
    if not repeated_dark_material_supported(material_regions):
        return None
    darkness = float(np.median(np.asarray(darkness_samples, dtype=np.float64)))
    texture = float(np.median(np.asarray(texture_samples, dtype=np.float64)))
    if darkness == 0.0 and texture == 0.0:
        return None
    transition_ids = tuple(
        sorted(
            {
                identity
                for identity in (*left.transition_ids, *right.transition_ids)
                if transitions[str(identity)].trace_coordinate_px
                in shared_traces
            },
            key=str,
        )
    )
    identity = ObservationId(
        run_local_id(
            "separator-band",
            left.observation_id,
            right.observation_id,
            gap.minimum.hex(),
            gap.maximum.hex(),
        )
    )
    return SeparatorBandObservation(
        observation_id=identity,
        left_edge_observation_id=left.observation_id,
        right_edge_observation_id=right.observation_id,
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        gap_interval_px=gap,
        transition_ids=transition_ids,
        independent_support_region_count=material_support_region_count,
        continuous_support_fraction=min(
            left.continuous_support_fraction,
            right.continuous_support_fraction,
        ),
        darkness_contrast=darkness,
        darkness_contrast_interval=FiniteInterval(
            min(darkness_samples),
            max(darkness_samples),
        ),
        texture_contrast=texture,
        texture_contrast_interval=FiniteInterval(
            min(texture_samples),
            max(texture_samples),
        ),
        material_regions=material_regions,
    )


def build_format_separator_bands(
    profile: BasicAxisProfile,
    edges: tuple[BoundaryEdgeObservation, ...],
    transitions: dict[str, PhotoBoundaryTransition],
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
) -> tuple[SeparatorBandObservation, ...]:
    """Pair every physical dark-valley edge family and verify its material.

    Format gap priors never filter observations.  A normal, very wide or
    otherwise abnormal directly visible black band enters the same material
    measurement; placement authority is assigned only after role binding.
    """

    ordered = tuple(
        sorted(
            edges,
            key=lambda item: (
                item.coordinate_interval_px.center,
                str(item.observation_id),
            ),
        )
    )
    if len(ordered) < 2:
        return ()
    runs_by_id = {run.run_id: run for run in profile.runs}
    edges_by_run_id = {edge.run_id: edge for edge in ordered}
    candidate_pairs: set[tuple[str, str]] = set()
    for trace in profile.trace_coordinates_px:
        trace_runs = tuple(
            run
            for run in profile.runs_at_trace(trace)
            if run.run_id in edges_by_run_id
        )
        for left_index, left_run in enumerate(trace_runs[:-1]):
            left = edges_by_run_id[left_run.run_id]
            if left.polarity != -1:
                continue
            for right_index, right_run in enumerate(
                trace_runs[left_index + 1 :],
                start=left_index + 1,
            ):
                right = edges_by_run_id[right_run.run_id]
                if right.polarity != 1:
                    continue
                candidate_pairs.add((left.run_id, right.run_id))

    values: dict[str, SeparatorBandObservation] = {}
    for left_run_id, right_run_id in sorted(candidate_pairs):
        candidate = _separator_band_from_edges(
            edges_by_run_id[left_run_id],
            edges_by_run_id[right_run_id],
            profile=profile,
            runs_by_id=runs_by_id,
            transitions=transitions,
            field=field,
            boundary_axis=boundary_axis,
        )
        if candidate is not None:
            values[str(candidate.observation_id)] = candidate
    return tuple(values[key] for key in sorted(values))
