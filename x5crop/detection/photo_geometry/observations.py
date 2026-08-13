"""Candidate-independent sequence-edge observations."""

from __future__ import annotations

from ...domain import ObservationId, PositiveInterval
from ...run_local_identity import run_local_id
from .model import BoundaryAxis
from .measurement_model import (
    PhotoBoundaryMeasurementField,
    PhotoBoundaryTransition,
)
from .observation_types import (
    BasicAxisProfile,
    BoundaryEdgeObservation,
    ProfileRun,
    SeparatorBandObservation,
)
from .separator_observations import build_format_separator_bands
from .sequence_direction_measurement import sequence_run_direction_measurement


def _dominant_polarity(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
) -> int:
    value = sum(
        transitions[str(identity)].polarity for identity in run.transition_ids
    )
    return 1 if value > 0 else -1 if value < 0 else 0


def build_sequence_observations(
    profile: BasicAxisProfile,
    transitions: dict[str, PhotoBoundaryTransition],
    field: PhotoBoundaryMeasurementField,
    boundary_axis: BoundaryAxis,
    boundary_axis_scale_px_per_mm: PositiveInterval,
) -> tuple[
    tuple[BoundaryEdgeObservation, ...],
    tuple[SeparatorBandObservation, ...],
]:
    edges: list[BoundaryEdgeObservation] = []
    for run in profile.runs:
        polarity = _dominant_polarity(run, transitions)
        if polarity == 0 and not run.qualified_anchor_roles:
            continue
        identity = ObservationId(
            run_local_id(
                "boundary-edge",
                run.run_id,
                run.coordinate_interval_px.minimum.hex(),
                run.coordinate_interval_px.maximum.hex(),
                polarity,
            )
        )
        direction = sequence_run_direction_measurement(
            run,
            transitions,
            boundary_axis_scale_px_per_mm=(
                boundary_axis_scale_px_per_mm.maximum
            ),
        )
        edges.append(
            BoundaryEdgeObservation(
                observation_id=identity,
                run_id=run.run_id,
                coordinate_interval_px=run.coordinate_interval_px,
                transition_ids=run.transition_ids,
                trace_coordinates_px=run.trace_coordinates_px,
                polarity=polarity,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
                canonical_direction_degrees=(
                    None if direction is None else direction[0]
                ),
                fit_direction_interval_degrees=(
                    None if direction is None else direction[1]
                ),
                full_direction_interval_degrees=(
                    None if direction is None else direction[2]
                ),
            )
        )
    ordered = tuple(
        sorted(
            edges,
            key=lambda item: (
                item.coordinate_interval_px.center,
                str(item.observation_id),
            ),
        )
    )
    bands = build_format_separator_bands(
        profile,
        ordered,
        transitions,
        field,
        boundary_axis,
    )
    return ordered, bands
