"""Resolve one source direction from independent template-bound evidence."""

from __future__ import annotations

from statistics import median

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .observation_types import BoundaryEdgeObservation
from .output_model import SharedStripDirection
from .template_cross import CrossFit
from .template_model import SequenceFit


def _intersect(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return None if minimum > maximum else FiniteInterval(minimum, maximum)


def _sequence_direction_groups(
    sequence_fit: SequenceFit,
    observations: tuple[BoundaryEdgeObservation, ...],
) -> tuple[
    tuple[float, FiniteInterval, tuple],
    ...,
]:
    """Return one direction fact per independent physical sequence position.

    The two sides of one separator are one physical structure.  They improve
    that separator's direction interval but never become two independent
    votes.  The outer start/end boundaries each remain their own position.
    """

    by_id = {item.observation_id: item for item in observations}
    role_ids = sequence_fit.role_observation_ids
    role_groups = [(0,)]
    role_groups.extend(
        (end_index, end_index + 1)
        for end_index in range(1, len(role_ids) - 1, 2)
    )
    if len(role_ids) > 1:
        role_groups.append((len(role_ids) - 1,))
    result = []
    for indices in role_groups:
        values = tuple(
            by_id[role_ids[index]]
            for index in indices
            if role_ids[index] is not None
            and role_ids[index] in by_id
            and by_id[role_ids[index]].canonical_direction_degrees is not None
            and by_id[role_ids[index]].fit_direction_interval_degrees is not None
        )
        if not values:
            continue
        canonical = float(median(
            float(item.canonical_direction_degrees) for item in values
        ))
        fit_interval = FiniteInterval(
            min(item.fit_direction_interval_degrees.minimum for item in values),
            max(item.fit_direction_interval_degrees.maximum for item in values),
        )
        result.append(
            (
                canonical,
                fit_interval,
                tuple(item.observation_id for item in values),
            )
        )
    return tuple(result)


def lane_template_direction(
    sequence_fit: SequenceFit,
    sequence_observations: tuple[BoundaryEdgeObservation, ...],
    cross_fit: CrossFit,
) -> SharedStripDirection:
    """Close shared direction from cross compatibility and sequence positions.

    Cross evidence still owns top/bottom placement.  At least two independent
    template-bound sequence positions may additionally estimate the one shared
    strip direction.  This is a continuous fit, never a placement vote.
    """

    cross_direction = cross_fit.selected_direction
    if cross_direction is None:
        raise ValueError("lane direction requires direct cross evidence")
    direct_fit_intervals = tuple(
        item.fit_direction_interval_degrees
        for item in cross_fit.direct_bindings
        if item.fit_direction_interval_degrees is not None
    )
    direct_fit_common = None
    if direct_fit_intervals:
        direct_fit_common = direct_fit_intervals[0]
        for interval in direct_fit_intervals[1:]:
            direct_fit_common = _intersect(direct_fit_common, interval)
            if direct_fit_common is None:
                break
    if any(
        item.source_spanning_continuous
        for item in cross_fit.direct_bindings
    ):
        return cross_direction
    if len(cross_fit.direct_bindings) != 2:
        return cross_direction
    groups = _sequence_direction_groups(sequence_fit, sequence_observations)
    if len(groups) < 2:
        return cross_direction
    sequence_interval = FiniteInterval(
        float(median(item[1].minimum for item in groups)),
        float(median(item[1].maximum for item in groups)),
    )
    sequence_identities = tuple(
        identity for item in groups for identity in item[2]
    )
    compatibility = (
        cross_fit.parallel_direction_interval_degrees
        or cross_direction.full_angle_interval_degrees
    )
    if direct_fit_common is not None:
        # Two role-authorized local sides establish one common direction, and
        # independent sequence positions prove that this local closure belongs
        # to the source-wide strip.  Retain each side's statistical fit hull;
        # the much broader fragment extrapolation intervals no longer become
        # source-wide selected-output uncertainty.
        if _intersect(sequence_interval, direct_fit_common) is None:
            return cross_direction
        fit_hull = FiniteInterval(
            min(item.minimum for item in direct_fit_intervals),
            max(item.maximum for item in direct_fit_intervals),
        )
        common = _intersect(fit_hull, compatibility)
        if common is None:
            return cross_direction
        canonical = min(
            common.maximum,
            max(common.minimum, cross_direction.canonical_angle_degrees),
        )
        identities = tuple(
            dict.fromkeys(
                (
                    *cross_direction.selected_observation_ids,
                    *sequence_identities,
                )
            )
        )
        return SharedStripDirection(
            direction_id=run_local_id(
                "template-lane-direction",
                cross_direction.direction_id,
                *(str(identity) for identity in identities),
            ),
            selected_observation_ids=identities,
            full_angle_interval_degrees=common,
            canonical_angle_degrees=canonical,
        )
    if _intersect(
        sequence_interval,
        cross_direction.full_angle_interval_degrees,
    ) is None:
        return cross_direction
    common = _intersect(sequence_interval, compatibility)
    if common is None:
        raise ValueError("sequence and cross direction evidence are incompatible")
    canonical = min(
        common.maximum,
        max(common.minimum, float(median(item[0] for item in groups))),
    )
    identities = tuple(
        dict.fromkeys(
            (
                *cross_direction.selected_observation_ids,
                *sequence_identities,
            )
        )
    )
    return SharedStripDirection(
        direction_id=run_local_id(
            "template-lane-direction",
            cross_direction.direction_id,
            *(str(identity) for identity in identities),
        ),
        selected_observation_ids=identities,
        full_angle_interval_degrees=common,
        canonical_angle_degrees=canonical,
    )


def shared_template_direction(
    directions: tuple[SharedStripDirection, ...],
) -> SharedStripDirection:
    if not directions:
        raise ValueError("shared template direction requires direct lane evidence")
    minimum = max(item.full_angle_interval_degrees.minimum for item in directions)
    maximum = min(item.full_angle_interval_degrees.maximum for item in directions)
    if minimum > maximum:
        raise ValueError("lane direction observations have no common interval")
    identities = tuple(
        sorted(
            {
                identity
                for direction in directions
                for identity in direction.selected_observation_ids
            },
            key=str,
        )
    )
    canonical = min(
        maximum,
        max(
            minimum,
            sum(item.canonical_angle_degrees for item in directions)
            / len(directions),
        ),
    )
    return SharedStripDirection(
        direction_id=run_local_id(
            "template-source-direction",
            *(item.direction_id for item in directions),
            *(str(identity) for identity in identities),
        ),
        selected_observation_ids=identities,
        full_angle_interval_degrees=FiniteInterval(minimum, maximum),
        canonical_angle_degrees=canonical,
    )


__all__ = ["lane_template_direction", "shared_template_direction"]
