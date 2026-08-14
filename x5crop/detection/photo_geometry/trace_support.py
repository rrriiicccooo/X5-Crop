"""Raster-continuity facts for registered physical edge traces."""

from __future__ import annotations

import numpy as np

from .model import (
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    SPATIAL_SUPPORT_REGION_COUNT,
    PhotoBoundaryMeasurementSpec,
    independent_spatial_support_count,
)


# Pixel coordinates name sample centres.  Half a pixel is the exact boundary
# of one sample cell; one pixel is its complete non-zero raster span.
PIXEL_CENTER_HALF_EXTENT_PX = 0.5
PIXEL_CENTER_EXTENT_PX = 1.0


def _continuous_support_runs(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
    *,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[tuple[int | float, ...], ...]:
    if not queried_traces or not supporting_traces:
        return ()
    queried = tuple(sorted(queried_traces))
    supporting = tuple(sorted(set(supporting_traces)))
    steps = np.diff(np.asarray(queried, dtype=np.float64))
    step = float(np.median(steps)) if steps.size else PIXEL_CENTER_EXTENT_PX
    maximum_gap = (
        step * (spec.maximum_missing_lattice_steps + 1)
        + spec.paired_sampling_uncertainty_px
    )
    runs: list[list[int | float]] = [[supporting[0]]]
    for trace in supporting[1:]:
        if trace - runs[-1][-1] > maximum_gap:
            runs.append([])
        runs[-1].append(trace)
    return tuple(tuple(run) for run in runs)


def continuous_trace_support_fraction(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
    *,
    spec: PhotoBoundaryMeasurementSpec,
) -> float:
    """Return the longest allowed-gap support run over the queried span."""

    if not queried_traces or not supporting_traces:
        return 0.0
    queried = tuple(sorted(queried_traces))
    runs = _continuous_support_runs(
        queried_traces,
        supporting_traces,
        spec=spec,
    )
    longest = max(float(run[-1] - run[0]) for run in runs)
    queried_span = max(
        spec.paired_sampling_uncertainty_px,
        float(queried[-1] - queried[0]),
    )
    return min(1.0, longest / queried_span)


def trace_support_is_one_connected_run(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
    *,
    spec: PhotoBoundaryMeasurementSpec,
) -> bool:
    """Return whether all supplied support belongs to one raster run."""

    runs = _continuous_support_runs(
        queried_traces,
        supporting_traces,
        spec=spec,
    )
    return len(runs) == 1


def source_spanning_continuous_trace_support(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
    *,
    spec: PhotoBoundaryMeasurementSpec,
) -> bool:
    """Return whether one connected edge run reaches both query-domain ends.

    Touching the three coarse support regions is independent-support evidence;
    it is not source-spanning authority.  A spanning line must remain one
    connected raster run and reach both ends of the already registered trace
    lattice, allowing only the same declared missing-lattice allowance used to
    connect neighbouring samples.  This is an ordinal/domain fact, not a
    support-percentage threshold.
    """

    if not queried_traces:
        return False
    queried = tuple(sorted(queried_traces))
    steps = np.diff(np.asarray(queried, dtype=np.float64))
    step = float(np.median(steps)) if steps.size else PIXEL_CENTER_EXTENT_PX
    end_allowance = (
        step * (spec.maximum_missing_lattice_steps + 1)
        + spec.paired_sampling_uncertainty_px
    )
    return any(
        run[0] <= queried[0] + end_allowance
        and run[-1] >= queried[-1] - end_allowance
        for run in _continuous_support_runs(
            queried_traces,
            supporting_traces,
            spec=spec,
        )
    )


def shared_independent_trace_support_count(
    queried_traces: tuple[int, ...],
    *supporting_trace_sets: tuple[int | float, ...],
) -> int:
    """Count independent regions where every observation is directly seen.

    A top/bottom height span is direct evidence only where both physical edges
    were measured on the same registered trace.  Intersecting their canonical
    trace coordinates prevents two disjoint local lines from gaining a direct
    pair authority through extrapolation alone.
    """

    if not queried_traces or len(supporting_trace_sets) < 2:
        return 0
    common = set(supporting_trace_sets[0])
    for supporting in supporting_trace_sets[1:]:
        common.intersection_update(supporting)
    if not common:
        return 0
    count = independent_spatial_support_count(
        queried_traces,
        tuple(sorted(common)),
    )
    if count < MINIMUM_INDEPENDENT_SUPPORT_REGIONS:
        return count
    return count
