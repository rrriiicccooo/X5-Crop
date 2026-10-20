"""Prove which fixed-template adjacencies were fully observed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import QueryPurpose
from .template_model import MAX_TEMPLATE_FIT_PASSES, SequenceFit, TemplateSpec


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
            or any(not identity for identity in self.covering_query_ids)
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
            or any(not identity for identity in self.covering_query_ids)
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
        if any(interval.minimum < self.required_interval_px.minimum
               or interval.maximum > self.required_interval_px.maximum
               for trace in self.trace_coverage for interval in trace.covered_intervals_px):
            raise ValueError("adjacency trace coverage leaves its required corridor")


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
    required_count = (
        0
        if required_bounds is None
        else required_bounds[1] - required_bounds[0] + 1
    )
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
    if not clipped_with_ids:
        return AdjacencyTraceCoverage(
            trace_position_px=trace_position_px,
            covering_query_ids=(),
            covered_intervals_px=(),
            required_coordinate_count=required_count,
            covered_coordinate_count=0,
            complete=False,
        )
    merged: list[tuple[int, int]] = []
    for start, end, _query_id in clipped_with_ids:
        if not merged or float(start) > float(merged[-1][1]) + 1.0:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    count = min(
        required_count,
        sum(end - start + 1 for start, end in merged),
    )
    complete = required_count > 0 and count == required_count
    return AdjacencyTraceCoverage(
        trace_position_px=trace_position_px,
        covering_query_ids=query_ids,
        covered_intervals_px=tuple(
            FiniteInterval(float(start), float(end))
            for start, end in merged
        ),
        required_coordinate_count=required_count,
        covered_coordinate_count=count,
        complete=complete,
    )


def _registered_trace_intervals(measurement_sets):
    trace_positions = tuple(sorted({trace for item in measurement_sets
        for trace in item.query.trace_positions_px}))
    by_trace = {trace: [] for trace in trace_positions}
    for item in measurement_sets:
        if item.coverage.complete:
            for trace, ownership in zip(item.query.trace_positions_px,
                    item.query.transition_ownership_intervals_px, strict=True):
                by_trace[trace].append((ownership, item.query.query_id))
    return tuple((trace, tuple(by_trace[trace])) for trace in trace_positions)


class AdjacencyCoveragePreparation:
    """One member's bounded neutral query coverage; never inference permission."""

    def __init__(self, measurement_sets, template: TemplateSpec):
        self.measurement_sets = measurement_sets
        self.template = template
        self._trace_intervals = _registered_trace_intervals(measurement_sets)
        self._corridors = {}
        self.maximum_corridors = MAX_TEMPLATE_FIT_PASSES * max(0, template.count - 1)
        self.lookup_count = self.preparation_count = 0
        self.reserved_bytes = self.reserve_bytes(measurement_sets, template)

    @staticmethod
    def reserve_bytes(measurement_sets, template):
        trace_count = len({trace for item in measurement_sets for trace in item.query.trace_positions_px})
        input_bytes = 4096 + 128 * sum(len(item.query.trace_positions_px) for item in measurement_sets)
        corridor_bytes = 256 + trace_count * (512 + 128 * len(measurement_sets))
        return input_bytes + (MAX_TEMPLATE_FIT_PASSES * max(0, template.count - 1) + 1) * corridor_bytes

    def check_inputs(self, fit, measurement_sets):
        if fit.template != self.template or (
                measurement_sets is not self.measurement_sets and measurement_sets != self.measurement_sets):
            raise ValueError("adjacency coverage preparation belongs to different template or registered queries")

    def for_interval(self, required):
        self.lookup_count += 1
        coverage = self._corridors.get(required)
        if coverage is not None:
            return coverage
        self.preparation_count += 1
        coverage = tuple(_trace_coverage(trace, required, intervals)
            for trace, intervals in self._trace_intervals)
        if len(self._corridors) < self.maximum_corridors:
            self._corridors[required] = coverage
        return coverage


def assess_adjacency_observation_coverage(
    fit: SequenceFit,
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    directly_observed_ordinals: tuple[int, ...],
    input_preparation: AdjacencyCoveragePreparation | None = None,
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
    if input_preparation is not None:
        input_preparation.check_inputs(fit, measurement_sets)
        trace_intervals = input_preparation._trace_intervals
    else:
        trace_intervals = _registered_trace_intervals(measurement_sets)
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
        trace_coverage = (tuple(_trace_coverage(trace, required, intervals)
            for trace, intervals in trace_intervals) if input_preparation is None
            else input_preparation.for_interval(required))
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
        required_coordinate_count = required_per_trace * len(trace_intervals)
        state = (
            AdjacencyCoverageState.COMPLETE
            if trace_intervals
            and covered_trace_count == len(trace_intervals)
            and covered_coordinate_count == required_coordinate_count
            else AdjacencyCoverageState.INCOMPLETE
        )
        values.append(
            AdjacencyObservationCoverage(
                relation_ordinal=relation_ordinal,
                required_interval_px=required,
                covering_query_ids=query_ids,
                trace_coverage=trace_coverage,
                required_trace_count=len(trace_intervals),
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
