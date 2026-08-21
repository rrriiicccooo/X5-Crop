"""Bound one placement's source-space frame axis without owning deskew."""

from __future__ import annotations

from statistics import median

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .interval_math import hull, intersect
from .model import SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation
from .output_model import OutputBoundaryUse, SharedStripDirection
from .template_cross_model import CrossEvidence, CrossFit
from .template_model import SequenceFit


def _sequence_role_groups(role_count: int) -> tuple[tuple[int, ...], ...]:
    groups: list[tuple[int, ...]] = [(0,)]
    groups.extend(
        (end_index, end_index + 1)
        for end_index in range(1, role_count - 1, 2)
    )
    if role_count > 1:
        groups.append((role_count - 1,))
    return tuple(groups)


def _sequence_axis_facts(
    sequence_fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
) -> tuple[tuple[float, FiniteInterval, tuple], ...]:
    by_id = {item.observation_id: item for item in observations}
    facts = []
    for indices in _sequence_role_groups(len(sequence_fit.role_observation_ids)):
        values = tuple(
            by_id[sequence_fit.role_observation_ids[index]]
            for index in indices
            if sequence_fit.role_observation_ids[index] is not None
            and sequence_fit.role_observation_ids[index] in by_id
            and by_id[
                sequence_fit.role_observation_ids[index]
            ].canonical_direction_degrees
            is not None
            and by_id[
                sequence_fit.role_observation_ids[index]
            ].fit_direction_interval_degrees
            is not None
        )
        if not values:
            continue
        facts.append(
            (
                float(
                    median(
                        float(item.canonical_direction_degrees)
                        for item in values
                    )
                ),
                FiniteInterval(
                    min(
                        item.fit_direction_interval_degrees.minimum
                        for item in values
                    ),
                    max(
                        item.fit_direction_interval_degrees.maximum
                        for item in values
                    ),
                ),
                tuple(item.observation_id for item in values),
            )
        )
    return tuple(facts)


def _frame_axis(
    cross_fit: CrossFit,
    interval: FiniteInterval,
    identities: tuple,
    *,
    canonical: float | None = None,
) -> SharedStripDirection:
    cross = cross_fit.selected_direction
    if cross is None:
        raise ValueError("frame axis requires direct cross geometry")
    selected = tuple(
        dict.fromkeys((*cross.selected_observation_ids, *identities))
    )
    value = cross.canonical_angle_degrees if canonical is None else canonical
    value = min(interval.maximum, max(interval.minimum, value))
    return SharedStripDirection(
        direction_id=run_local_id(
            "template-frame-axis",
            cross.direction_id,
            *(str(identity) for identity in selected),
        ),
        selected_observation_ids=selected,
        full_angle_interval_degrees=interval,
        observed_angle_interval_degrees=hull(
            (cross.observed_angle_interval_degrees, interval)
        ),
        canonical_angle_degrees=value,
    )


def placement_frame_axis(
    sequence_fit: SequenceFit,
    sequence_observations: tuple[BoundaryEdgeObservation, ...],
    cross_fit: CrossFit,
) -> SharedStripDirection:
    """Resolve only the local axis needed to bound a source-space frame.

    This value never selects a placement, joins lanes, or rotates output. If
    direct facts cannot safely narrow the cross interval, the original cross
    interval remains as conservative polygon uncertainty instead of becoming
    a new detection failure.
    """

    cross = cross_fit.selected_direction
    if cross is None:
        raise ValueError("frame axis requires direct cross geometry")
    local_refinements = tuple(
        item
        for item in cross_fit.direct_bindings
        if item.evidence == CrossEvidence.TEMPLATE_LOCAL_REFINEMENT
    )
    direct_anchors = tuple(
        item
        for item in cross_fit.direct_bindings
        if item.evidence != CrossEvidence.TEMPLATE_LOCAL_REFINEMENT
        and item.canonical_direction_degrees is not None
        and item.full_direction_interval_degrees is not None
    )
    if len(local_refinements) == 1 and len(direct_anchors) == 1:
        anchor = direct_anchors[0]
        return _frame_axis(
            cross_fit,
            anchor.full_direction_interval_degrees,
            (),
            canonical=float(anchor.canonical_direction_degrees),
        )
    if (
        cross_fit.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        or any(
            item.source_spanning_continuous and item.role_authorized
            for item in cross_fit.direct_bindings
        )
    ):
        return cross
    fit_intervals = tuple(
        item.fit_direction_interval_degrees
        for item in cross_fit.direct_bindings
        if item.fit_direction_interval_degrees is not None
    )
    if (
        cross_fit.direct_pair
        and cross_fit.independent_support_region_count
        == SPATIAL_SUPPORT_REGION_COUNT
        and len(fit_intervals) == 2
    ):
        return _frame_axis(
            cross_fit,
            FiniteInterval(
                min(item.minimum for item in fit_intervals),
                max(item.maximum for item in fit_intervals),
            ),
            (),
        )
    if len(cross_fit.direct_bindings) != 2 or len(fit_intervals) != 2:
        return cross
    sequence_facts = _sequence_axis_facts(
        sequence_fit,
        sequence_observations,
    )
    if len(sequence_facts) < 2:
        return cross
    sequence_interval = FiniteInterval(
        float(median(item[1].minimum for item in sequence_facts)),
        float(median(item[1].maximum for item in sequence_facts)),
    )
    sequence_ids = tuple(
        identity for fact in sequence_facts for identity in fact[2]
    )
    fit_common = intersect(fit_intervals[0], fit_intervals[1])
    if fit_common is not None:
        if intersect(sequence_interval, fit_common) is None:
            return cross
        return _frame_axis(
            cross_fit,
            FiniteInterval(
                min(item.minimum for item in fit_intervals),
                max(item.maximum for item in fit_intervals),
            ),
            sequence_ids,
        )
    local_direct_pair = (
        cross_fit.boundary_use == OutputBoundaryUse.APERTURE_PAIR
        and cross_fit.independent_support_region_count
        < SPATIAL_SUPPORT_REGION_COUNT
        and all(
            item.evidence == CrossEvidence.DIRECT
            and item.role_authorized
            and not item.source_spanning_continuous
            for item in cross_fit.direct_bindings
        )
    )
    if not local_direct_pair:
        return cross
    return _frame_axis(
        cross_fit,
        sequence_interval,
        sequence_ids,
        canonical=float(median(item[0] for item in sequence_facts)),
    )


__all__ = ["placement_frame_axis"]
