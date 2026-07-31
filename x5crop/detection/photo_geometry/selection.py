from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...domain import FiniteInterval, PositiveInterval
from ..source_core import SourceLaneEvidence
from .model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    PhotoBoundaryObservation,
)


def line_coordinate_at_trace(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> float:
    line = observation.line
    if boundary_axis == BoundaryAxis.X:
        if abs(line.normal_x) <= 1.0e-12:
            raise ValueError("x-boundary line has no x authority")
        return (
            line.offset_px - line.normal_y * trace_coordinate_px
        ) / line.normal_x
    if abs(line.normal_y) <= 1.0e-12:
        raise ValueError("y-boundary line has no y authority")
    return (
        line.offset_px - line.normal_x * trace_coordinate_px
    ) / line.normal_y


def line_coordinate_interval_at_trace(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> FiniteInterval:
    line = observation.line
    component = (
        line.normal_x
        if boundary_axis == BoundaryAxis.X
        else line.normal_y
    )
    if abs(component) <= 1.0e-12:
        raise ValueError("boundary line has no dependent-axis authority")
    values = tuple(
        (
            offset
            - (
                line.normal_y
                if boundary_axis == BoundaryAxis.X
                else line.normal_x
            )
            * trace_coordinate_px
        )
        / component
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def _angles_overlap(
    left: FiniteInterval,
    right: FiniteInterval,
) -> bool:
    return (
        left.minimum <= right.maximum
        and right.minimum <= left.maximum
    )


def eliminate_transition_zone_dominated_lines(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoBoundaryObservation, ...]:
    """Retain one evidence-dominant fit per equivalent physical line.

    The maximum raw transition width belongs to one observed transition
    interval; it is not permission to merge separately fitted parallel lines
    across a 1 mm band.  Only the frozen source-geometry equivalence tolerance
    and intersecting angle intervals may form a dominance class.
    """

    if not observations:
        return ()
    maximum_zone_width = max(
        1.0,
        spec.geometry_equivalence_mm
        * boundary_axis_scale_px_per_mm.maximum
    )
    positioned = tuple(
        sorted(
            (
                (
                    line_coordinate_at_trace(
                        observation,
                        boundary_axis=boundary_axis,
                        trace_coordinate_px=reference_trace_px,
                    ),
                    observation,
                )
                for observation in observations
            ),
            key=lambda item: (item[0], str(item[1].observation_id)),
        )
    )
    zones: list[list[tuple[float, PhotoBoundaryObservation]]] = []
    for position, observation in positioned:
        target = next(
            (
                zone
                for zone in zones
                if (
                    position - zone[0][0] <= maximum_zone_width
                    and _angles_overlap(
                        observation.angle_interval_degrees,
                        zone[0][1].angle_interval_degrees,
                    )
                )
            ),
            None,
        )
        if target is None:
            zones.append([(position, observation)])
        else:
            target.append((position, observation))

    retained = tuple(
        min(
            (observation for _position, observation in zone),
            key=lambda item: (
                -item.trace_support_count,
                -item.continuous_support_fraction,
                item.measurement_uncertainty_px,
                item.fit_residual_px,
                str(item.observation_id),
            ),
        )
        for zone in zones
    )
    return tuple(
        sorted(
            retained,
            key=lambda item: (
                line_coordinate_at_trace(
                    item,
                    boundary_axis=boundary_axis,
                    trace_coordinate_px=reference_trace_px,
                ),
                str(item.observation_id),
            ),
        )
    )


@dataclass(frozen=True)
class ObservedAperturePair:
    pair_id: str
    start: PhotoBoundaryObservation
    end: PhotoBoundaryObservation
    start_position_px: FiniteInterval
    end_position_px: FiniteInterval
    width_interval_px: FiniteInterval
    physical_residual_px: float


def positive_content_support_interval(
    lane: SourceLaneEvidence,
    aperture_width_px: float,
) -> FiniteInterval | None:
    """Selection-only long-axis support; it never creates a photo edge."""

    table = lane.content.row_run_table
    domain = lane.domain.work_box
    if table.run_count == 0:
        return None
    difference = np.zeros(domain.width + 1, dtype=np.int64)
    lefts = table.lefts - domain.left
    rights = table.rights - domain.left
    np.add.at(difference, lefts, 1)
    np.add.at(difference, rights, -1)
    support = np.cumsum(difference[:-1], dtype=np.int64).astype(
        np.float64,
        copy=False,
    )
    support /= float(domain.height)
    window = max(1, min(domain.width, round(aperture_width_px / 4.0)))
    cumulative = np.empty(support.size + 1, dtype=np.float64)
    cumulative[0] = 0.0
    np.cumsum(support, out=cumulative[1:])
    smoothed = (
        cumulative[window:] - cumulative[:-window]
    ) / float(window)
    if not smoothed.size:
        return None
    maximum = float(smoothed.max())
    if maximum <= 0.0:
        return None
    active = np.flatnonzero(smoothed >= maximum * 0.5)
    if not active.size:
        return None
    center_offset = window // 2
    return FiniteInterval(
        float(domain.left + int(active[0]) + center_offset),
        float(domain.left + int(active[-1]) + center_offset),
    )


def outer_observed_assignments(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    authoritative_sequence_length: int,
    strip_mode: str,
    known_content_interval_px: FiniteInterval | None,
    expected_grid_translation_px: float | None,
    full_search_radius_px: float,
    lane_long_extent_px: int,
) -> tuple[tuple[str, int], ...]:
    """Upgrade an outer proposal only by selecting a remeasured 2-D line."""

    if not observations or authoritative_sequence_length <= 0:
        return ()
    positioned = tuple(
        sorted(
            (
                (
                    line_coordinate_at_trace(
                        observation,
                        boundary_axis=boundary_axis,
                        trace_coordinate_px=reference_trace_px,
                    ),
                    observation,
                )
                for observation in observations
            ),
            key=lambda item: (item[0], str(item[1].observation_id)),
        )
    )
    if strip_mode == "full" and expected_grid_translation_px is not None:
        leading_eligible = tuple(
            item
            for item in positioned
            if abs(item[0] - expected_grid_translation_px)
            <= full_search_radius_px
        )
        expected_trailing = (
            float(lane_long_extent_px) - expected_grid_translation_px
        )
        trailing_eligible = tuple(
            item
            for item in positioned
            if abs(item[0] - expected_trailing)
            <= full_search_radius_px
        )
        leading_proposals = tuple(
            dict.fromkeys(
                (
                    min(
                        leading_eligible,
                        key=lambda item: (
                            abs(item[0] - expected_grid_translation_px),
                            str(item[1].observation_id),
                        ),
                    )
                    if leading_eligible
                    else None,
                    min(
                        leading_eligible,
                        key=lambda item: (
                            item[0],
                            str(item[1].observation_id),
                        ),
                    )
                    if leading_eligible
                    else None,
                )
            )
        )
        trailing_proposals = tuple(
            dict.fromkeys(
                (
                    min(
                        trailing_eligible,
                        key=lambda item: (
                            abs(item[0] - expected_trailing),
                            str(item[1].observation_id),
                        ),
                    )
                    if trailing_eligible
                    else None,
                    max(
                        trailing_eligible,
                        key=lambda item: (
                            item[0],
                            str(item[1].observation_id),
                        ),
                    )
                    if trailing_eligible
                    else None,
                )
            )
        )
        return tuple(
            dict.fromkeys(
                (
                    *(
                        (str(observation.observation_id), 0)
                        for proposal in leading_proposals
                        if proposal is not None
                        for _position, observation in (proposal,)
                    ),
                    *(
                        (
                            str(observation.observation_id),
                            authoritative_sequence_length * 2 - 1,
                        )
                        for proposal in trailing_proposals
                        if proposal is not None
                        for _position, observation in (proposal,)
                    ),
                )
            )
        )
    if known_content_interval_px is None:
        return ()
    leading = tuple(
        item
        for item in positioned
        if (
            known_content_interval_px.minimum - full_search_radius_px
            <= item[0]
            <= known_content_interval_px.minimum
        )
    )
    trailing = tuple(
        item
        for item in positioned
        if (
            known_content_interval_px.maximum
            <= item[0]
            <= known_content_interval_px.maximum + full_search_radius_px
        )
    )
    leading_proposals = tuple(
        dict.fromkeys(
            (
                min(
                    leading,
                    key=lambda item: (
                        item[0],
                        str(item[1].observation_id),
                    ),
                )
                if leading
                else None,
                max(
                    leading,
                    key=lambda item: (
                        item[0],
                        str(item[1].observation_id),
                    ),
                )
                if leading
                else None,
            )
        )
    )
    trailing_proposals = tuple(
        dict.fromkeys(
            (
                min(
                    trailing,
                    key=lambda item: (
                        item[0],
                        str(item[1].observation_id),
                    ),
                )
                if trailing
                else None,
                max(
                    trailing,
                    key=lambda item: (
                        item[0],
                        str(item[1].observation_id),
                    ),
                )
                if trailing
                else None,
            )
        )
    )
    return tuple(
        dict.fromkeys(
            (
                *(
                    (str(observation.observation_id), 0)
                    for proposal in leading_proposals
                    if proposal is not None
                    for _position, observation in (proposal,)
                ),
                *(
                    (
                        str(observation.observation_id),
                        authoritative_sequence_length * 2 - 1,
                    )
                    for proposal in trailing_proposals
                    if proposal is not None
                    for _position, observation in (proposal,)
                ),
            )
        )
    )


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def indexed_observed_aperture_pairs(
    observations: tuple[PhotoBoundaryObservation, ...],
    *,
    boundary_axis: BoundaryAxis,
    reference_trace_px: float,
    aperture_width_px: PositiveInterval,
) -> tuple[ObservedAperturePair, ...]:
    """Join compatible starts/ends by sorted interval lookup, not a product."""

    positioned = tuple(
        sorted(
            (
                (
                    line_coordinate_interval_at_trace(
                        observation,
                        boundary_axis=boundary_axis,
                        trace_coordinate_px=reference_trace_px,
                    ),
                    observation,
                )
                for observation in observations
            ),
            key=lambda item: (
                item[0].center,
                str(item[1].observation_id),
            ),
        )
    )
    pairs: list[ObservedAperturePair] = []
    first_end_index = 0
    for start_index, (start_interval, start) in enumerate(positioned):
        minimum_end = start_interval.minimum + aperture_width_px.minimum
        while (
            first_end_index < len(positioned)
            and positioned[first_end_index][0].maximum < minimum_end
        ):
            first_end_index += 1
        end_index = max(first_end_index, start_index + 1)
        maximum_end = start_interval.maximum + aperture_width_px.maximum
        while end_index < len(positioned):
            end_interval, end = positioned[end_index]
            if end_interval.minimum > maximum_end:
                break
            width = FiniteInterval(
                end_interval.minimum - start_interval.maximum,
                end_interval.maximum - start_interval.minimum,
            )
            if (
                width.maximum >= aperture_width_px.minimum
                and width.minimum <= aperture_width_px.maximum
            ):
                expected_center = (
                    aperture_width_px.minimum
                    + aperture_width_px.maximum
                ) / 2.0
                pairs.append(
                    ObservedAperturePair(
                        pair_id=_stable_id(
                            "observed-aperture",
                            start.observation_id,
                            end.observation_id,
                        ),
                        start=start,
                        end=end,
                        start_position_px=start_interval,
                        end_position_px=end_interval,
                        width_interval_px=width,
                        physical_residual_px=abs(
                            width.center - expected_center
                        ),
                    )
                )
            end_index += 1
    return tuple(pairs)
