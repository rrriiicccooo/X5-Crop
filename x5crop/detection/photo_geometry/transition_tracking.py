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
from .cross_height_transition_measurement import spatial_region_trace_ordinals
from .line_observations import (
    SideTransitionRegion,
    TransitionRegionMeasurementBasis,
)
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


def _track_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    support_interval_px: FiniteInterval | None = None,
    minimum_independent_support_regions: int = (
        MINIMUM_INDEPENDENT_SUPPORT_REGIONS
    ),
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    measurement_basis: TransitionRegionMeasurementBasis,
) -> tuple[SideTransitionRegion, ...]:
    """Track one typed transition source without assigning boundary roles.

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
        for transition in (
            item.transitions
            if measurement_basis
            == TransitionRegionMeasurementBasis.DIRECT_TRACE
            else item.cross_height_transitions
            if measurement_basis
            == TransitionRegionMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            else item.broad_material_transitions
        )
    }
    transitions = tuple(
        sorted(
            (
                transition
                for transition in transition_by_id.values()
                if (
                    measurement_basis
                    != TransitionRegionMeasurementBasis.CROSS_HEIGHT_AGGREGATE
                    or transition.polarity != 0
                )
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
    if measurement_basis != TransitionRegionMeasurementBasis.DIRECT_TRACE:
        trace_lattices = {
            item.query.trace_positions_px for item in measurement_sets
        }
        if len(trace_lattices) != 1:
            return ()
        lattice = next(iter(trace_lattices))
        regions = spatial_region_trace_ordinals(lattice)
        if not regions:
            return ()
        source_traces = tuple(
            lattice[region[len(region) // 2]] for region in regions
        )
    else:
        source_traces = tuple(
            sorted(
                {
                    trace
                    for item in measurement_sets
                    for trace in item.query.trace_positions_px
                }
            )
        )
    queried_traces = tuple(
        trace
        for trace in source_traces
        if support_interval_px is None
        or support_interval_px.contains(
            float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
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

    def same_aggregate_material_state(
        point: TransitionPoint,
        last: TransitionPoint,
    ) -> bool:
        if measurement_basis == TransitionRegionMeasurementBasis.DIRECT_TRACE:
            return True
        if point.transition.polarity != last.transition.polarity:
            return False
        if (
            measurement_basis
            == TransitionRegionMeasurementBasis.BROAD_MATERIAL_AGGREGATE
        ):
            return (
                point.transition.background_side
                == last.transition.background_side
            )
        return True

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
                    and same_aggregate_material_state(point, last)
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
        mean_gradient_z = (
            sum(point.transition.gradient_z for point in points)
            / len(points)
        )
        mean_tone_or_texture_z = (
            sum(
                max(point.transition.tone_z, point.transition.texture_z)
                for point in points
            )
            / len(points)
        )
        if measurement_basis == (
            TransitionRegionMeasurementBasis.BROAD_MATERIAL_AGGREGATE
        ):
            qualified_strength = (
                independent_regions == SPATIAL_SUPPORT_REGION_COUNT
                and mean_tone_or_texture_z
                >= spec.tone_or_texture_z_minimum
            )
        else:
            qualified_strength = (
                mean_gradient_z >= spec.gradient_z_minimum
                and mean_tone_or_texture_z
                >= spec.tone_or_texture_z_minimum
            )
        if not qualified_strength:
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
        # alternative.  Template fitting may resolve it with W, H, ordinal and
        # the other axis; lexical order may not choose one here.
        for selected_indices, position in alternatives:
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
                position_interval_px=position,
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
                measurement_basis=measurement_basis,
            )
    return tuple(
        sorted(
            regions.values(),
            key=lambda item: (
                item.position_interval_px.center,
                item.region_id,
            ),
        )
    )


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
    """Track direct single-trace transitions into physical segments."""

    return _track_transition_regions(
        measurement_sets,
        reference_trace_px=reference_trace_px,
        boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        support_interval_px=support_interval_px,
        minimum_independent_support_regions=(
            minimum_independent_support_regions
        ),
        spec=spec,
        measurement_basis=TransitionRegionMeasurementBasis.DIRECT_TRACE,
    )


def track_cross_height_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[SideTransitionRegion, ...]:
    """Require all three fixed height regions for one weak joint line."""

    return _track_transition_regions(
        measurement_sets,
        reference_trace_px=reference_trace_px,
        boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        support_interval_px=None,
        minimum_independent_support_regions=SPATIAL_SUPPORT_REGION_COUNT,
        spec=spec,
        measurement_basis=(
            TransitionRegionMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        ),
    )


def track_broad_material_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[SideTransitionRegion, ...]:
    """Track only three-region, two-scale material observations."""

    return _track_transition_regions(
        measurement_sets,
        reference_trace_px=reference_trace_px,
        boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        support_interval_px=None,
        minimum_independent_support_regions=SPATIAL_SUPPORT_REGION_COUNT,
        spec=spec,
        measurement_basis=(
            TransitionRegionMeasurementBasis.BROAD_MATERIAL_AGGREGATE
        ),
    )
