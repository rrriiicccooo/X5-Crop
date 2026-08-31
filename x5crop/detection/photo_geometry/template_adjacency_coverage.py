"""Prove which fixed-template adjacencies were fully observed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import QueryPurpose
from .template_model import SequenceFit


class AdjacencyCoverageState(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class AdjacencyTraceCoverage:
    """Exact ownership union covering one corridor on one registered trace."""

    trace_position_px: int
    covering_query_ids: tuple[str, ...]
    covered_intervals_px: tuple[FiniteInterval, ...]
    required_coordinate_count: int
    covered_coordinate_count: int
    complete: bool

    def __post_init__(self) -> None:
        if (
            tuple(sorted(set(self.covering_query_ids)))
            != self.covering_query_ids
            or tuple(
                sorted(
                    self.covered_intervals_px,
                    key=lambda item: (item.minimum, item.maximum),
                )
            )
            != self.covered_intervals_px
            or min(
                self.required_coordinate_count,
                self.covered_coordinate_count,
            )
            < 0
            or self.covered_coordinate_count > self.required_coordinate_count
            or self.complete
            and (
                self.covered_coordinate_count
                != self.required_coordinate_count
                or self.required_coordinate_count <= 0
            )
        ):
            raise ValueError("adjacency trace coverage is invalid")


@dataclass(frozen=True)
class AdjacencyObservationCoverage:
    """Coverage of one selected adjacency by pre-registered sequence queries."""

    relation_ordinal: int
    required_interval_px: FiniteInterval
    covering_query_ids: tuple[str, ...]
    trace_coverage: tuple[AdjacencyTraceCoverage, ...]
    required_trace_count: int
    covered_trace_count: int
    required_coordinate_count: int
    covered_coordinate_count: int
    normal_inference_required: bool
    state: AdjacencyCoverageState

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not isinstance(self.required_interval_px, FiniteInterval)
            or tuple(sorted(set(self.covering_query_ids)))
            != self.covering_query_ids
            or tuple(item.trace_position_px for item in self.trace_coverage)
            != tuple(
                sorted({item.trace_position_px for item in self.trace_coverage})
            )
            or any(
                not isinstance(item, AdjacencyTraceCoverage)
                for item in self.trace_coverage
            )
            or min(
                self.required_trace_count,
                self.covered_trace_count,
                self.required_coordinate_count,
                self.covered_coordinate_count,
            )
            < 0
            or self.covered_trace_count > self.required_trace_count
            or self.covered_coordinate_count > self.required_coordinate_count
            or not isinstance(self.normal_inference_required, bool)
            or not isinstance(self.state, AdjacencyCoverageState)
        ):
            raise ValueError("adjacency observation coverage is invalid")
        complete = (
            self.required_trace_count > 0
            and self.covered_trace_count == self.required_trace_count
            and self.covered_coordinate_count == self.required_coordinate_count
        )
        if complete != (self.state == AdjacencyCoverageState.COMPLETE):
            raise ValueError("adjacency coverage state disagrees with its counts")
        if (
            self.required_trace_count != len(self.trace_coverage)
            or self.covered_trace_count
            != sum(item.complete for item in self.trace_coverage)
            or self.required_coordinate_count
            != sum(item.required_coordinate_count for item in self.trace_coverage)
            or self.covered_coordinate_count
            != sum(item.covered_coordinate_count for item in self.trace_coverage)
            or self.covering_query_ids
            != tuple(
                sorted(
                    {
                        query_id
                        for item in self.trace_coverage
                        for query_id in item.covering_query_ids
                    }
                )
            )
        ):
            raise ValueError("adjacency aggregate coverage disagrees with traces")


def _integer_coordinate_bounds(
    interval: FiniteInterval,
) -> tuple[int, int] | None:
    minimum = int(math.ceil(interval.minimum))
    maximum = int(math.floor(interval.maximum))
    return None if maximum < minimum else (minimum, maximum)


def _integer_coordinate_count(interval: FiniteInterval) -> int:
    bounds = _integer_coordinate_bounds(interval)
    return 0 if bounds is None else bounds[1] - bounds[0] + 1


def _trace_coverage(
    trace_position_px: int,
    required: FiniteInterval,
    intervals: tuple[tuple[FiniteInterval, str], ...],
) -> AdjacencyTraceCoverage:
    required_bounds = _integer_coordinate_bounds(required)
    required_count = _integer_coordinate_count(required)
    clipped_with_ids: list[tuple[int, int, str]] = []
    if required_bounds is not None:
        required_start, required_end = required_bounds
        for interval, query_id in intervals:
            bounds = _integer_coordinate_bounds(interval)
            if bounds is None:
                continue
            start = max(required_start, bounds[0])
            end = min(required_end, bounds[1])
            if start <= end:
                clipped_with_ids.append((start, end, query_id))
    clipped_with_ids.sort(key=lambda item: (item[0], item[1], item[2]))
    query_ids = tuple(sorted({item[2] for item in clipped_with_ids}))
    clipped = tuple(
        FiniteInterval(float(start), float(end))
        for start, end, _query_id in clipped_with_ids
    )
    if not clipped:
        return AdjacencyTraceCoverage(
            trace_position_px=trace_position_px,
            covering_query_ids=(),
            covered_intervals_px=(),
            required_coordinate_count=required_count,
            covered_coordinate_count=0,
            complete=False,
        )
    merged: list[FiniteInterval] = []
    for interval in clipped:
        if not merged or interval.minimum > merged[-1].maximum + 1.0:
            merged.append(interval)
        else:
            merged[-1] = FiniteInterval(
                merged[-1].minimum,
                max(merged[-1].maximum, interval.maximum),
            )
    count = min(
        required_count,
        sum(_integer_coordinate_count(interval) for interval in merged),
    )
    complete = required_count > 0 and count == required_count
    return AdjacencyTraceCoverage(
        trace_position_px=trace_position_px,
        covering_query_ids=query_ids,
        covered_intervals_px=tuple(merged),
        required_coordinate_count=required_count,
        covered_coordinate_count=count,
        complete=complete,
    )


def assess_adjacency_observation_coverage(
    fit: SequenceFit,
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    directly_observed_ordinals: tuple[int, ...],
) -> tuple[AdjacencyObservationCoverage, ...]:
    """Map selected adjacency intervals to already executed query ownership."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("adjacency coverage requires a sequence fit")
    observed = tuple(sorted(set(directly_observed_ordinals)))
    if observed != directly_observed_ordinals or any(
        ordinal <= 0 or ordinal >= fit.template.count
        for ordinal in observed
    ):
        raise ValueError("direct adjacency ordinals are invalid")
    if any(
        not isinstance(item, PhotoBoundaryMeasurementSet)
        or item.query.purpose != QueryPurpose.SEQUENCE_ANCHOR_WINDOW
        for item in measurement_sets
    ):
        raise TypeError("adjacency coverage requires sequence-window measurements")
    trace_positions = tuple(
        sorted(
            {
                trace
                for item in measurement_sets
                for trace in item.query.trace_positions_px
            }
        )
    )
    coverage_by_trace: dict[int, list[tuple[FiniteInterval, str]]] = {
        trace: [] for trace in trace_positions
    }
    for item in measurement_sets:
        if not item.coverage.complete:
            continue
        for trace, ownership in zip(
            item.query.trace_positions_px,
            item.query.transition_ownership_intervals_px,
            strict=True,
        ):
            coverage_by_trace[trace].append((ownership, item.query.query_id))
    values: list[AdjacencyObservationCoverage] = []
    for adjacency_index in range(max(0, fit.template.count - 1)):
        relation_ordinal = adjacency_index + 1
        left = fit.model_full_role_intervals_px[2 * adjacency_index + 1]
        right = fit.model_full_role_intervals_px[2 * adjacency_index + 2]
        required = FiniteInterval(
            min(left.minimum, right.minimum),
            max(left.maximum, right.maximum),
        )
        required_per_trace = _integer_coordinate_count(required)
        trace_coverage = tuple(
            _trace_coverage(
                trace,
                required,
                tuple(coverage_by_trace[trace]),
            )
            for trace in trace_positions
        )
        covered_trace_count = sum(item.complete for item in trace_coverage)
        covered_coordinate_count = sum(
            item.covered_coordinate_count for item in trace_coverage
        )
        query_ids = tuple(
            sorted(
                {
                    query_id
                    for item in trace_coverage
                    for query_id in item.covering_query_ids
                }
            )
        )
        required_coordinate_count = required_per_trace * len(trace_positions)
        state = (
            AdjacencyCoverageState.COMPLETE
            if trace_positions
            and covered_trace_count == len(trace_positions)
            and covered_coordinate_count == required_coordinate_count
            else AdjacencyCoverageState.INCOMPLETE
        )
        values.append(
            AdjacencyObservationCoverage(
                relation_ordinal=relation_ordinal,
                required_interval_px=required,
                covering_query_ids=query_ids,
                trace_coverage=trace_coverage,
                required_trace_count=len(trace_positions),
                covered_trace_count=covered_trace_count,
                required_coordinate_count=required_coordinate_count,
                covered_coordinate_count=min(
                    covered_coordinate_count,
                    required_coordinate_count,
                ),
                normal_inference_required=(relation_ordinal not in observed),
                state=state,
            )
        )
    return tuple(values)


__all__ = [
    "AdjacencyCoverageState",
    "AdjacencyObservationCoverage",
    "AdjacencyTraceCoverage",
    "assess_adjacency_observation_coverage",
]
