"""Bounded source-pitch calibration from already bound template roles."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from ...domain import FiniteInterval
from .observation_types import BoundaryEdgeObservation
from .template_model import TemplateSpec
from .template_phase_model import PhaseFitResult, PhaseFitStatus


def _intersect(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        return None
    return FiniteInterval(minimum, maximum)


def _advance_interval(
    left: FiniteInterval,
    right: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return FiniteInterval(
            right.minimum - left.maximum,
            right.maximum - left.minimum,
        )
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _unique_supported_interval(
    values: Sequence[FiniteInterval],
) -> FiniteInterval | None:
    """Return the sole interval group supported at two physical adjacencies."""

    groups = {
        tuple(
            index
            for index, interval in enumerate(values)
            if interval.contains(point, epsilon=1.0e-9)
        )
        for interval in values
        for point in (interval.minimum, interval.maximum)
    }
    maximum_support = max(map(len, groups), default=0)
    winners = tuple(group for group in groups if len(group) == maximum_support)
    if maximum_support < 2 or len(winners) != 1:
        return None
    winner = winners[0]
    return FiniteInterval(
        max(values[index].minimum for index in winner),
        min(values[index].maximum for index in winner),
    )


def calibrate_template_source_pitch(
    template: TemplateSpec,
    phase: PhaseFitResult,
    observations: Sequence[BoundaryEdgeObservation],
) -> TemplateSpec:
    """Replace the format pitch prior only after two direct normal advances.

    Format gap remains the bounded search seed used by the provisional fit.
    Once two distinct adjacent slot relations support one source pitch, their
    common interval becomes the lane's measured pitch authority.  Each
    adjacency counts once even when both START and END observations exist.
    Discrete or conflicting groups leave the compiled template unchanged.
    """

    if phase.status != PhaseFitStatus.RESOLVED or phase.best is None:
        return template
    fit = phase.best
    if fit.template.count != template.count or fit.template.direction != template.direction:
        raise ValueError("pitch calibration template identity disagrees")
    by_id = {item.observation_id: item for item in observations}
    adjacency_intervals: list[FiniteInterval] = []
    for ordinal in range(template.count - 1):
        relations: list[FiniteInterval] = []
        for role_offset in (0, 1):
            left_id = fit.role_observation_ids[2 * ordinal + role_offset]
            right_id = fit.role_observation_ids[2 * (ordinal + 1) + role_offset]
            if left_id is None or right_id is None:
                continue
            left = by_id.get(left_id)
            right = by_id.get(right_id)
            if left is None or right is None:
                raise ValueError("bound pitch observation is not registered")
            measured = _advance_interval(
                left.coordinate_interval_px,
                right.coordinate_interval_px,
                template.direction,
            )
            if measured.minimum <= 0.0:
                continue
            relations.append(measured)
        if not relations:
            continue
        relation = relations[0]
        for other in relations[1:]:
            common = _intersect(relation, other)
            if common is None:
                relation = None
                break
            relation = common
        if relation is None:
            continue
        adjacency_intervals.append(relation)
    measured_pitch = _unique_supported_interval(adjacency_intervals)
    if measured_pitch is None:
        return template
    width = FiniteInterval(
        template.frame_width_px.minimum,
        template.frame_width_px.maximum,
    )
    gap = FiniteInterval(
        max(0.0, measured_pitch.minimum - width.maximum),
        max(0.0, measured_pitch.maximum - width.minimum),
    )
    if gap.maximum <= 0.0:
        return template
    return replace(
        template,
        pitch_px=measured_pitch,
        nominal_gap_px=gap,
        phase_lattice_authority=(
            template.phase_lattice_authority.with_period(measured_pitch)
        ),
    )


__all__ = ["calibrate_template_source_pitch"]
