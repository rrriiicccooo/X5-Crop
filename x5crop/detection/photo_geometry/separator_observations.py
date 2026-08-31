"""Direct separator-band observations from paired physical edge families."""

from __future__ import annotations

import math

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...run_local_identity import run_local_id
from .model import (
    BoundaryAxis,
    BoundaryEvidenceState,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
    spatial_support_region_index,
)
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    SequenceTransitionObservation,
)
from .observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    ProfileRun,
    SeparatorBandObservation,
    SeparatorBandMeasurementBasis,
    SeparatorMaterialPolarity,
    SeparatorMaterialRegionObservation,
    SeparatorMaterialRegionState,
)
from .separator_material import (
    classify_separator_material_region,
    repeated_separator_material_supported,
)


def _separator_core_material(
    left: BoundaryEdgeObservation,
    right: BoundaryEdgeObservation,
    *,
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
    transitions: dict[str, SequenceTransitionObservation],
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
    transitions: dict[str, SequenceTransitionObservation],
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
    frame_width_px: PositiveInterval,
    measurement_basis: SeparatorBandMeasurementBasis,
) -> SeparatorBandObservation | None:
    """Build one directly observed band from two physical edge families."""

    if (
        left.fit_position_interval_px.center
        >= right.fit_position_interval_px.center
    ):
        return None
    polarity = {
        (-1, 1): SeparatorMaterialPolarity.DARK,
        (1, -1): SeparatorMaterialPolarity.LIGHT,
    }.get((left.polarity, right.polarity))
    if polarity is None:
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
            right.fit_position_interval_px.minimum
            - left.fit_position_interval_px.maximum,
        ),
        max(
            0.0,
            right.fit_position_interval_px.maximum
            - left.fit_position_interval_px.minimum,
        ),
    )
    if gap.maximum >= frame_width_px.minimum:
        # A region that can contain a complete format frame is not one
        # adjacency's separator material.  It may be coarse support or an
        # unresolved missing-frame region, but it cannot bind END -> START.
        return None
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
    observed_material_region_count = independent_spatial_support_count(
        profile.trace_coordinates_px,
        tuple(item[0] for item in material),
    )
    if observed_material_region_count < MINIMUM_INDEPENDENT_SUPPORT_REGIONS:
        return None
    left_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in left_run.transition_ids
    }
    right_by_trace = {
        transitions[str(identity)].trace_coordinate_px: transitions[str(identity)]
        for identity in right_run.transition_ids
    }
    material_contrast_samples = tuple(
        (
            min(
                left_by_trace[trace].left_tone_mean,
                right_by_trace[trace].right_tone_mean,
            )
            - core_tone
            if polarity == SeparatorMaterialPolarity.DARK
            else core_tone
            - max(
                left_by_trace[trace].left_tone_mean,
                right_by_trace[trace].right_tone_mean,
            )
        )
        for trace, core_tone, _core_texture in material
    )
    samples_by_region: dict[int, list[tuple[float, float]]] = {}
    for (trace, _core_tone, core_texture), contrast in zip(
        material,
        material_contrast_samples,
        strict=True,
    ):
        region_index = spatial_support_region_index(
            profile.trace_coordinates_px,
            trace,
        )
        samples_by_region.setdefault(region_index, []).append(
            (contrast, core_texture)
        )
    material_regions_list: list[SeparatorMaterialRegionObservation] = []
    for region_index, values in sorted(samples_by_region.items()):
        contrast_interval = FiniteInterval(
            min(item[0] for item in values),
            max(item[0] for item in values),
        )
        core_texture_interval = FiniteInterval(
            min(item[1] for item in values),
            max(item[1] for item in values),
        )
        material_regions_list.append(
            SeparatorMaterialRegionObservation(
                region_index=region_index,
                sample_count=len(values),
                material_contrast_interval=contrast_interval,
                core_texture_interval=core_texture_interval,
                state=classify_separator_material_region(
                    contrast_interval,
                    core_texture_interval,
                ),
            ),
        )
    material_regions = tuple(material_regions_list)
    material_support_region_count = sum(
        item.state == SeparatorMaterialRegionState.SUPPORTED
        for item in material_regions
    )
    repeated_material = repeated_separator_material_supported(
        material_regions
    )
    source_wide_conflict = (
        len(material_regions) == SPATIAL_SUPPORT_REGION_COUNT
        and not repeated_material
    )
    if (
        not repeated_material
        and not source_wide_conflict
    ):
        return None
    material_contrast = float(
        np.median(np.asarray(material_contrast_samples, dtype=np.float64))
    )
    core_texture_samples = tuple(item[2] for item in material)
    core_texture = float(
        np.median(np.asarray(core_texture_samples, dtype=np.float64))
    )
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
            polarity.value,
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
        measurement_basis=measurement_basis,
        material_polarity=polarity,
        gap_interval_px=gap,
        transition_ids=transition_ids,
        material_support_region_count=material_support_region_count,
        continuous_support_fraction=min(
            left.continuous_support_fraction,
            right.continuous_support_fraction,
        ),
        material_contrast=material_contrast,
        material_contrast_interval=FiniteInterval(
            min(material_contrast_samples),
            max(material_contrast_samples),
        ),
        core_texture=core_texture,
        core_texture_interval=FiniteInterval(
            min(core_texture_samples),
            max(core_texture_samples),
        ),
        material_regions=material_regions,
        evidence_state=(
            BoundaryEvidenceState.CONTRADICTION
            if source_wide_conflict
            else BoundaryEvidenceState.SUPPORT
        ),
    )


def build_format_separator_bands(
    profile: BasicAxisProfile,
    edges: tuple[BoundaryEdgeObservation, ...],
    transitions: dict[str, SequenceTransitionObservation],
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
    frame_width_px: PositiveInterval,
    *,
    measurement_basis: SeparatorBandMeasurementBasis,
) -> tuple[SeparatorBandObservation, ...]:
    """Verify adjacent dark-valley or light-peak edges as material.

    Format gap priors never filter observations.  A normal, very wide or
    otherwise abnormal directly visible band enters the same material
    measurement while it remains narrower than one complete format frame.
    A region wide enough to contain a frame cannot prove one adjacency.
    Placement authority is assigned only after role binding.
    The two edges must be neighbours on a trace. Skipping over another
    transition would turn photo content or several structures into one false
    separator and creates quadratic work.
    """

    ordered = tuple(
        sorted(
            edges,
            key=lambda item: (
                item.fit_position_interval_px.center,
                str(item.observation_id),
            ),
        )
    )
    if len(ordered) < 2:
        return ()
    if not isinstance(frame_width_px, PositiveInterval):
        raise TypeError("separator frame-width authority must be positive")
    runs_by_id = {run.run_id: run for run in profile.runs}
    edges_by_run_id = {edge.run_id: edge for edge in ordered}
    candidate_pairs: set[tuple[str, str]] = set()
    for trace in profile.trace_coordinates_px:
        trace_runs = tuple(
            run
            for run in profile.runs_at_trace(trace)
            if run.run_id in edges_by_run_id
        )
        for left_run, right_run in zip(trace_runs, trace_runs[1:]):
            left = edges_by_run_id[left_run.run_id]
            right = edges_by_run_id[right_run.run_id]
            if (left.polarity, right.polarity) in {(-1, 1), (1, -1)}:
                candidate_pairs.add((left.run_id, right.run_id))

    values: dict[str, SeparatorBandObservation] = {}
    for left_run_id, right_run_id in sorted(candidate_pairs):
        left_edge = edges_by_run_id[left_run_id]
        right_edge = edges_by_run_id[right_run_id]
        maximum_gap = max(
            0.0,
            right_edge.fit_position_interval_px.maximum
            - left_edge.fit_position_interval_px.minimum,
        )
        if maximum_gap >= frame_width_px.minimum:
            continue
        candidate = _separator_band_from_edges(
            left_edge,
            right_edge,
            profile=profile,
            runs_by_id=runs_by_id,
            transitions=transitions,
            field=field,
            boundary_axis=boundary_axis,
            frame_width_px=frame_width_px,
            measurement_basis=measurement_basis,
        )
        if candidate is not None:
            values[str(candidate.observation_id)] = candidate
    return tuple(values[key] for key in sorted(values))
