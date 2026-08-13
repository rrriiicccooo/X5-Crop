"""Lane direction compatibility facts for one complete chain."""

from __future__ import annotations

from statistics import median

from ...domain import FiniteInterval, ObservationId
from .chains import CompleteFormatChain
from .interval_math import intersect


def lane_direction_evidence(
    placement: CompleteFormatChain,
) -> tuple[float, tuple[ObservationId, ...]]:
    cross_observations = {
        item.observation.observation_id: item.observation
        for item in placement.cross.evidence
    }
    sequence_observations = {
        item.observation_id: item
        for item in placement.sequence.observations
        if item.observation_id is not None
    }
    direction_ids = set(
        placement.lane_geometry.direction.selected_observation_ids
    )
    cross_intervals = tuple(
        observation.fit_angle_interval_degrees
        for identity, observation in cross_observations.items()
        if identity in direction_ids
    )
    identities = tuple(
        sorted((*cross_observations, *sequence_observations), key=str)
    )
    if not cross_intervals:
        return 0.0, identities

    def interval_gap(left: FiniteInterval, right: FiniteInterval) -> float:
        return max(
            0.0,
            left.minimum - right.maximum,
            right.minimum - left.maximum,
        )

    comparisons = [
        interval_gap(left, right)
        for index, left in enumerate(cross_intervals)
        for right in cross_intervals[index + 1 :]
    ]
    sequence_consensus = _sequence_direction_consensus(placement)
    if sequence_consensus is not None:
        comparisons.extend(
            interval_gap(interval, sequence_consensus)
            for interval in cross_intervals
        )
    return max(comparisons, default=0.0), identities


def _sequence_direction_consensus(
    placement: CompleteFormatChain,
) -> FiniteInterval | None:
    """Return repeated compatible sequence-edge direction evidence."""

    observations = {
        item.observation_id: item
        for item in placement.sequence.observations
        if item.observation_id is not None
    }
    values = tuple(observations.values())
    if len(values) < 2:
        return None
    full_common = values[0].full_direction_interval_degrees
    for item in values[1:]:
        full_common = intersect(
            full_common,
            item.full_direction_interval_degrees,
        )
        if full_common is None:
            break
    if full_common is not None:
        return full_common
    if len(values) == 2:
        return None
    return FiniteInterval(
        median(item.fit_direction_interval_degrees.minimum for item in values),
        median(item.fit_direction_interval_degrees.maximum for item in values),
    )
