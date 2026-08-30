"""Canonical physical identity for long-axis boundary edge segments."""

from __future__ import annotations

import math

import numpy as np

from ...domain import FiniteInterval, ObservationId, PositiveInterval
from ...run_local_identity import run_local_id
from .edge_family_identity import (
    disjoint_family_pairs,
)
from .interval_math import common, intersect
from .measurement_points import TransitionPoint
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
)
from .measurement_model import SequenceTransitionObservation
from .observation_types import BasicAxisProfile, ProfileRun
from .robust_line_fit import fit_transition_line, physical_slope_interval
from .sequence_direction_measurement import sequence_run_direction_measurement
from .trace_support import (
    continuous_trace_support_fraction,
    trace_support_is_one_connected_run,
)


def _dominant_polarity(
    run: ProfileRun,
    transitions: dict[str, SequenceTransitionObservation],
) -> int:
    value = sum(
        transitions[str(identity)].polarity for identity in run.transition_ids
    )
    return 1 if value > 0 else -1 if value < 0 else 0


def _reference_position_interval(
    runs: tuple[ProfileRun, ...],
    transitions: dict[str, SequenceTransitionObservation],
    *,
    slope: float,
    reference_trace_px: float,
) -> FiniteInterval | None:
    constraints = tuple(
        FiniteInterval(
            transition.physical_position_interval_px.minimum
            - slope * (transition.trace_coordinate_px - reference_trace_px),
            transition.physical_position_interval_px.maximum
            - slope * (transition.trace_coordinate_px - reference_trace_px),
        )
        for run in runs
        for identity in run.transition_ids
        for transition in (transitions[str(identity)],)
    )
    return common(constraints)


def merge_sequence_edge_families(
    profile: BasicAxisProfile,
    transitions: dict[str, SequenceTransitionObservation],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> BasicAxisProfile:
    """Merge only disjoint segments proved to be one complete physical line."""

    if profile.axis_name != "sequence" or len(profile.runs) < 2:
        return profile
    runs = profile.runs
    fit_cache: dict[tuple[int, ...], tuple[ProfileRun, float] | None] = {}

    def fit_members(indices: tuple[int, ...]) -> tuple[ProfileRun, float] | None:
        key = tuple(sorted(indices))
        if key in fit_cache:
            return fit_cache[key]
        members = tuple(runs[index] for index in key)
        polarities = {_dominant_polarity(run, transitions) for run in members}
        identities = tuple(
            ObservationId(value)
            for value in sorted(
                {
                    str(identity)
                    for run in members
                    for identity in run.transition_ids
                }
            )
        )
        if polarities in ({0}, {-1, 0}, {0, 1}) or len(polarities) != 1:
            fit_cache[key] = None
            return None
        points = tuple(
            TransitionPoint(
                transition=transitions[str(identity)],
                trace=float(transitions[str(identity)].trace_coordinate_px),
                coordinate=transitions[str(identity)].coordinate_px,
            )
            for identity in identities
        )
        maximum_slope = math.tan(
            math.radians(spec.maximum_measurable_line_angle_degrees)
        )
        if physical_slope_interval(points, maximum_slope) is None:
            fit_cache[key] = None
            return None
        fitted = fit_transition_line(
            points, boundary_axis_scale_px_per_mm.maximum, spec
        )
        retained_ids = tuple(
            sorted(
                (point.transition.transition_id for point in fitted.selected_points),
                key=str,
            )
        )
        if set(retained_ids) != set(identities):
            fit_cache[key] = None
            return None
        position = _reference_position_interval(
            members,
            transitions,
            slope=fitted.slope,
            reference_trace_px=reference_trace_px,
        )
        if position is None:
            fit_cache[key] = None
            return None
        traces = tuple(
            sorted(
                {
                    transitions[str(identity)].trace_coordinate_px
                    for identity in identities
                }
            )
        )
        residual = float(np.median(np.abs(fitted.residuals)))
        merged = ProfileRun(
            run_id=run_local_id(
                "sequence-edge-family", *(run.run_id for run in members)
            ),
            coordinate_interval_px=position,
            transition_ids=identities,
            trace_coordinates_px=traces,
            role_hint=None,
            qualified_anchor_roles=tuple(
                role
                for role in members[0].qualified_anchor_roles
                if all(
                    role in member.qualified_anchor_roles for member in members
                )
            ),
            support_fraction=len(traces) / len(profile.trace_coordinates_px),
            continuous_support_fraction=continuous_trace_support_fraction(
                profile.trace_coordinates_px, traces, spec=spec
            ),
            fit_residual_px=residual,
            evidence_strength=sum(
                transitions[str(identity)].gradient_z
                + max(
                    transitions[str(identity)].tone_z,
                    transitions[str(identity)].texture_z,
                )
                for identity in identities
            )
            / len(identities),
            pair_qualified=all(member.pair_qualified for member in members),
        )
        fit_cache[key] = (merged, math.degrees(math.atan(-fitted.slope)))
        return fit_cache[key]

    def merge_components(
        mergeable: set[tuple[int, int]],
    ) -> tuple[ProfileRun, ...]:
        """Merge only an entire uniquely connected physical family.

        If a connected graph cannot be fitted as one common line, keeping all
        original observations is the only non-arbitrary result.  Greedily
        choosing one compatible neighbour would suppress a real competitor by
        lexical order before role binding.
        """

        components: list[tuple[int, ...]] = []
        remaining = set(range(len(runs)))
        while remaining:
            frontier = [min(remaining)]
            component: set[int] = set()
            while frontier:
                member = frontier.pop()
                if member in component:
                    continue
                component.add(member)
                frontier.extend(
                    candidate
                    for candidate in remaining
                    if tuple(sorted((member, candidate))) in mergeable
                )
            remaining.difference_update(component)
            components.append(tuple(sorted(component)))
        merged: list[ProfileRun] = []
        for component in components:
            fitted = fit_members(component) if len(component) > 1 else None
            if fitted is None:
                merged.extend(runs[index] for index in component)
            else:
                merged.append(fitted[0])
        return tuple(merged)

    # Multiple trace/window fits may express the same physical edge.  Merge
    # them before any role is generated, but only when pixel identity,
    # position, direction and continuous support all agree.  No coordinate
    # distance threshold participates.
    directions = tuple(
        sequence_run_direction_measurement(
            run,
            transitions,
            queried_trace_coordinates_px=profile.trace_coordinates_px,
            boundary_axis_scale_px_per_mm=(
                boundary_axis_scale_px_per_mm.maximum
            ),
            spec=spec,
        )
        for run in runs
    )
    duplicate_pairs = {
        (left_index, right_index)
        for left_index, left in enumerate(runs)
        for right_index, right in enumerate(runs[left_index + 1 :], start=left_index + 1)
        if set(left.transition_ids) & set(right.transition_ids)
        and intersect(
            left.coordinate_interval_px,
            right.coordinate_interval_px,
        )
        is not None
        and directions[left_index] is not None
        and directions[right_index] is not None
        and intersect(
            directions[left_index][1],  # type: ignore[index]
            directions[right_index][1],  # type: ignore[index]
        )
        is not None
        and trace_support_is_one_connected_run(
            profile.trace_coordinates_px,
            tuple(
                sorted(
                    set(left.trace_coordinates_px)
                    | set(right.trace_coordinates_px)
                )
            ),
            spec=spec,
        )
        and fit_members((left_index, right_index)) is not None
    }
    if duplicate_pairs:
        runs = merge_components(duplicate_pairs)
        fit_cache.clear()

    pairs = disjoint_family_pairs(
        tuple(
            FiniteInterval(
                float(run.trace_coordinates_px[0]),
                float(run.trace_coordinates_px[-1]),
            )
            for run in runs
        )
    )

    mergeable = {pair for pair in pairs if fit_members(pair) is not None}
    merged_runs = merge_components(mergeable)
    return BasicAxisProfile(
        profile.axis_name,
        profile.coordinate_count,
        profile.trace_coordinates_px,
        tuple(
            sorted(
                merged_runs,
                key=lambda item: (
                    item.coordinate_interval_px.center,
                    item.run_id,
                ),
            )
        ),
    )
