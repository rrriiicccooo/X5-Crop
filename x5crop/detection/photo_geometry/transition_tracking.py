"""Connect registered transitions into finite physical edge runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np

from ...domain import EvidenceState, FiniteInterval, PositiveInterval
from .measurement_points import TransitionPoint
from .trace_support import (
    PIXEL_CENTER_HALF_EXTENT_PX,
    continuous_trace_support_fraction,
)
from .model import (
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SPATIAL_SUPPORT_REGION_COUNT,
    PhotoBoundaryMeasurementSpec,
    independent_spatial_support_count,
)
from .measurement_model import PhotoBoundaryMeasurementSet
from .line_observations import SideTransitionRegion
from .physical_identity import physical_observation_id

@dataclass
class _SideTrack:
    points: list[TransitionPoint]
    last_trace_index: int


def _unique_nearest(
    distances: list[tuple[float, int]],
    tie_tolerance_px: float,
) -> int | None:
    if not distances:
        return None
    ordered = sorted(distances)
    if (
        len(ordered) > 1
        and ordered[1][0] - ordered[0][0] <= tie_tolerance_px
    ):
        return None
    return ordered[0][1]


def provisional_cross_projection_interval(
    coordinate_interval_px: FiniteInterval,
    *,
    trace_coordinate_px: float,
    reference_trace_px: float,
    maximum_angle_degrees: float,
    numeric_uncertainty_px: float,
) -> FiniteInterval:
    """Project one per-trace run before the shared direction is known."""

    if (
        not math.isfinite(trace_coordinate_px)
        or not math.isfinite(reference_trace_px)
        or not math.isfinite(maximum_angle_degrees)
        or not 0.0 <= maximum_angle_degrees < 90.0
        or not math.isfinite(numeric_uncertainty_px)
        or numeric_uncertainty_px < 0.0
    ):
        raise ValueError("provisional cross projection is invalid")
    allowance = (
        abs(trace_coordinate_px - reference_trace_px)
        * math.tan(math.radians(maximum_angle_degrees))
        + numeric_uncertainty_px
    )
    return FiniteInterval(
        coordinate_interval_px.minimum - allowance,
        coordinate_interval_px.maximum + allowance,
    )


def _maximum_coverage_intervals(
    intervals: tuple[FiniteInterval, ...],
) -> tuple[
    int,
    tuple[tuple[frozenset[int], FiniteInterval], ...],
]:
    if not intervals:
        return 0, ()
    endpoints = sorted(
        {
            value
            for interval in intervals
            for value in (interval.minimum, interval.maximum)
        }
    )
    probes = [*endpoints]
    probes.extend(
        (left + right) / 2.0
        for left, right in zip(endpoints, endpoints[1:])
        if right > left
    )
    subsets = {
        frozenset(
            index
            for index, interval in enumerate(intervals)
            if interval.contains(probe, epsilon=1.0e-12)
        )
        for probe in probes
    }
    maximum = max(map(len, subsets), default=0)
    best_subsets = tuple(
        sorted(
            (subset for subset in subsets if len(subset) == maximum),
            key=lambda subset: tuple(sorted(subset)),
        )
    )
    alternatives = tuple(
        (
            subset,
            FiniteInterval(
                max(intervals[index].minimum for index in subset),
                min(intervals[index].maximum for index in subset),
            ),
        )
        for subset in best_subsets
        if subset
    )
    return maximum, alternatives


def median_canonical_location(values: tuple[float, ...]) -> float:
    """Choose a robust representative inside one established placement.

    This is not a fit and owns no physical interval.  The exact median is the
    closed-form minimizer of absolute residuals, so a general optimizer,
    evidence weights, convergence policy, and an empirical loss scale would
    add no authority.  Competing placements are never passed to this helper.
    """

    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("canonical scalar values must be finite and non-empty")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def track_side_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    support_interval_px: FiniteInterval | None = None,
    minimum_independent_support_regions: int = (
        MINIMUM_INDEPENDENT_SUPPORT_REGIONS
    ),
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[SideTransitionRegion, ...]:
    """Track finite local side segments without assigning boundary roles.

    Sequence edges remain source/lane observations and therefore request two
    independent support regions here.  Top/bottom measurement may request one
    region: a local continuous segment is its minimum observation unit, while
    the cross-edge-family owner later proves repetition in a second region.
    """

    if (
        not 1
        <= minimum_independent_support_regions
        <= SPATIAL_SUPPORT_REGION_COUNT
        or any(
        item.state != EvidenceState.SUPPORTED or not item.coverage.complete
        for item in measurement_sets
        )
    ):
        return ()
    transition_by_id = {
        str(transition.transition_id): transition
        for item in measurement_sets
        for transition in item.transitions
    }
    transitions = tuple(
        sorted(
            (
                transition
                for transition in transition_by_id.values()
                if support_interval_px is None
                or support_interval_px.contains(
                    float(transition.trace_coordinate_px),
                    epsilon=PIXEL_CENTER_HALF_EXTENT_PX,
                )
            ),
            key=lambda item: (
                item.trace_coordinate_px,
                item.coordinate_px,
                str(item.transition_id),
            ),
        )
    )
    queried_traces = tuple(
        sorted(
            {
                trace
                for item in measurement_sets
                for trace in item.query.trace_positions_px
                if support_interval_px is None
                or support_interval_px.contains(
                    float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
                )
            }
        )
    )
    if not transitions or not queried_traces:
        return ()
    trace_to_index = {
        trace: index for index, trace in enumerate(queried_traces)
    }
    by_trace: dict[int, list[TransitionPoint]] = defaultdict(list)
    for transition in transitions:
        by_trace[transition.trace_coordinate_px].append(
            TransitionPoint(
                transition=transition,
                trace=float(transition.trace_coordinate_px),
                coordinate=transition.coordinate_px,
            )
        )
    tie_tolerance = spec.paired_sampling_uncertainty_px
    connection_px = spec.line_connection_allowance_px(
        boundary_axis_scale_px_per_mm.maximum
    )
    maximum_slope = math.tan(
        math.radians(spec.maximum_measurable_line_angle_degrees)
    )
    active: list[_SideTrack] = []
    completed: list[_SideTrack] = []
    for trace in queried_traces:
        trace_index = trace_to_index[trace]
        current = sorted(
            by_trace.get(trace, ()),
            key=lambda point: (
                point.coordinate,
                str(point.transition.transition_id),
            ),
        )
        eligible: list[_SideTrack] = []
        for track in active:
            if (
                trace_index - track.last_trace_index
                <= spec.maximum_missing_lattice_steps + 1
            ):
                eligible.append(track)
            else:
                completed.append(track)
        active = eligible
        connected_points: set[int] = set()
        gaps = tuple(
            sorted(
                {
                    trace_index - track.last_trace_index
                    for track in active
                }
            )
        )
        # A contiguous track owns the first reciprocal-nearest opportunity.
        # A track using the single permitted missing step may only consume a
        # transition left unmatched by the contiguous class.  This prevents
        # one ambiguous fork from leaving an older ghost track that blocks
        # the same physical edge on every later trace.
        for gap in gaps:
            track_indices = tuple(
                index
                for index, track in enumerate(active)
                if trace_index - track.last_trace_index == gap
            )
            proposed_by_point: dict[int, list[tuple[float, int]]] = (
                defaultdict(list)
            )
            nearest_by_track: dict[int, int | None] = {}
            for track_index in track_indices:
                track = active[track_index]
                last = track.points[-1]
                allowance = (
                    abs(float(trace) - last.trace) * maximum_slope
                    + connection_px
                )
                distances = [
                    (abs(point.coordinate - last.coordinate), point_index)
                    for point_index, point in enumerate(current)
                    if point_index not in connected_points
                    and abs(point.coordinate - last.coordinate)
                    <= allowance + 1.0e-12
                ]
                nearest = _unique_nearest(distances, tie_tolerance)
                nearest_by_track[track_index] = nearest
                if nearest is not None:
                    distance = abs(
                        current[nearest].coordinate - last.coordinate
                    )
                    proposed_by_point[nearest].append(
                        (distance, track_index)
                    )
            nearest_track_by_point = {
                point_index: _unique_nearest(proposals, tie_tolerance)
                for point_index, proposals in proposed_by_point.items()
            }
            for track_index in track_indices:
                point_index = nearest_by_track[track_index]
                if (
                    point_index is not None
                    and nearest_track_by_point.get(point_index)
                    == track_index
                ):
                    active[track_index].points.append(current[point_index])
                    active[track_index].last_trace_index = trace_index
                    connected_points.add(point_index)
        for point_index, point in enumerate(current):
            if point_index not in connected_points:
                active.append(_SideTrack([point], trace_index))
        still_active: list[_SideTrack] = []
        for track in active:
            if (
                trace_index - track.last_trace_index
                <= spec.maximum_missing_lattice_steps
            ):
                still_active.append(track)
            else:
                completed.append(track)
        active = still_active
    completed.extend(active)

    # One local segment needs at least two distinct traces.  Repeated support
    # belongs to the later physical-family owner; it must not be demanded here
    # when top/bottom can be temporarily hidden by picture content or gaps.
    minimum_support = max(2, minimum_independent_support_regions)
    regions: dict[tuple[str, ...], SideTransitionRegion] = {}
    for track in completed:
        points = tuple(
            sorted(
                track.points,
                key=lambda item: (
                    item.trace,
                    item.coordinate,
                    str(item.transition.transition_id),
                ),
            )
        )
        traces = tuple(point.trace for point in points)
        independent_regions = independent_spatial_support_count(
            queried_traces,
            traces,
        )
        if (
            len(set(traces)) < minimum_support
            or independent_regions < minimum_independent_support_regions
        ):
            continue
        if (
            sum(point.transition.gradient_z for point in points)
            / len(points)
            < spec.gradient_z_minimum
            or sum(
                max(point.transition.tone_z, point.transition.texture_z)
                for point in points
            )
            / len(points)
            < spec.tone_or_texture_z_minimum
        ):
            continue
        projected = tuple(
            provisional_cross_projection_interval(
                point.transition.localization_interval_px,
                trace_coordinate_px=point.trace,
                reference_trace_px=reference_trace_px,
                maximum_angle_degrees=(
                    spec.maximum_measurable_line_angle_degrees
                ),
                numeric_uncertainty_px=connection_px,
            )
            for point in points
        )
        coverage, alternatives = _maximum_coverage_intervals(projected)
        if coverage < minimum_support or not alternatives:
            continue
        # Preserve every equal maximum-coverage line as a distinct physical
        # alternative.  Later complete-chain selection may resolve it with W,
        # H, ordinal and the other axis; lexical order may not choose one here.
        for selected_indices, proposal in alternatives:
            selected = tuple(points[index] for index in sorted(selected_indices))
            selected_traces = tuple(point.trace for point in selected)
            independent_count = independent_spatial_support_count(
                queried_traces,
                selected_traces,
            )
            if independent_count < minimum_independent_support_regions:
                continue
            transition_ids = tuple(
                sorted(
                    (point.transition.transition_id for point in selected),
                    key=str,
                )
            )
            signature = tuple(map(str, transition_ids))
            centers = np.asarray(
                [point.coordinate for point in selected], dtype=np.float64
            )
            residual = float(
                np.median(np.abs(centers - np.median(centers)))
            )
            region_id = physical_observation_id(
                "side-region", *(str(item) for item in transition_ids)
            )
            regions[signature] = SideTransitionRegion(
                region_id=str(region_id),
                proposal_position_interval_px=proposal,
                transition_ids=transition_ids,
                trace_support_count=len(selected),
                queried_trace_count=len(queried_traces),
                independent_support_region_count=independent_count,
                continuous_support_fraction=continuous_trace_support_fraction(
                    queried_traces,
                    selected_traces,
                    spec=spec,
                ),
                fit_residual_px=residual,
                mean_gradient_z=sum(
                    point.transition.gradient_z for point in selected
                )
                / len(selected),
                mean_tone_or_texture_z=sum(
                    max(point.transition.tone_z, point.transition.texture_z)
                    for point in selected
                )
                / len(selected),
                left_background_preference_fraction=(
                    sum(
                        point.transition.left_texture_mean
                        < point.transition.right_texture_mean
                        for point in selected
                    )
                    / len(selected)
                ),
                right_background_preference_fraction=(
                    sum(
                        point.transition.right_texture_mean
                        < point.transition.left_texture_mean
                        for point in selected
                    )
                    / len(selected)
                ),
                ambiguous=False,
            )
    return tuple(
        sorted(
            regions.values(),
            key=lambda item: (
                item.proposal_position_interval_px.center,
                item.region_id,
            ),
        )
    )
