from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import math

import numpy as np

from ...domain import (
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)


SEPARATOR_DIFFERENCE_THRESHOLD_U8 = 16
SEPARATOR_ROW_CHUNK_SIZE = 128
SEPARATOR_MINIMUM_SUPPORT_FRACTION = 0.04
SEPARATOR_SUPPORT_PERCENTILE = 90.0
SEPARATOR_BAND_SUCCESSOR_MAX = 2


@dataclass(frozen=True)
class SeparatorMeasurementStatistics:
    domain_pixels: int
    measured_adjacencies: int
    line_observation_count: int
    row_chunk_count: int
    exact_measurement_count: int
    exact_cache_hit_count: int
    deterministic_seconds: float
    peak_temporary_bytes: int

    def __post_init__(self) -> None:
        counts = (
            self.domain_pixels,
            self.measured_adjacencies,
            self.line_observation_count,
            self.row_chunk_count,
            self.exact_measurement_count,
            self.exact_cache_hit_count,
            self.peak_temporary_bytes,
        )
        if any(value < 0 for value in counts):
            raise ValueError("separator statistics cannot be negative")
        if (
            not math.isfinite(self.deterministic_seconds)
            or self.deterministic_seconds < 0.0
        ):
            raise ValueError("separator duration must be finite")


@dataclass(frozen=True)
class SeparatorLineObservation:
    observation_id: ObservationId
    boundary_px: float
    interval_px: FiniteInterval
    support_fraction: float
    mean_absolute_difference: float
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.boundary_px)
            or not self.interval_px.contains(self.boundary_px)
            or not 0.0 <= self.support_fraction <= 1.0
            or not 0.0 <= self.mean_absolute_difference <= 255.0
            or self.provenance.root_measurement
            != MeasurementIdentity.SEPARATOR_FIELD
        ):
            raise ValueError("separator line observation is invalid")


@dataclass(frozen=True)
class SeparatorBandObservation:
    observation_id: ObservationId
    leading_transition: SeparatorLineObservation
    trailing_transition: SeparatorLineObservation
    band_interval_px: FiniteInterval
    width_interval_px: FiniteInterval
    center_interval_px: FiniteInterval
    support: float
    appearance: str
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            self.leading_transition.boundary_px
            >= self.trailing_transition.boundary_px
            or self.band_interval_px.minimum
            >= self.band_interval_px.maximum
            or self.width_interval_px.minimum < 0.0
            or self.center_interval_px.minimum
            > self.center_interval_px.maximum
            or not math.isfinite(self.support)
            or self.support < 0.0
            or self.appearance not in {"ordinary", "wide"}
            or self.provenance.root_measurement
            != MeasurementIdentity.SEPARATOR_FIELD
        ):
            raise ValueError("separator band observation is invalid")


@dataclass(frozen=True)
class LongAxisSeparatorMeasurementField:
    lane_id: str
    long_extent_px: int
    short_extent_px: int
    difference_support: np.ndarray
    mean_absolute_difference: np.ndarray
    support_threshold: float
    lines: tuple[SeparatorLineObservation, ...]
    statistics: SeparatorMeasurementStatistics
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not self.lane_id or min(self.long_extent_px, self.short_extent_px) <= 0:
            raise ValueError("separator field requires a positive lane domain")
        expected = self.long_extent_px - 1
        for array in (self.difference_support, self.mean_absolute_difference):
            if (
                not isinstance(array, np.ndarray)
                or array.ndim != 1
                or array.dtype != np.float32
                or array.size != expected
                or array.flags.writeable
            ):
                raise TypeError(
                    "separator measurement arrays must be immutable float32 fields"
                )
        if (
            not math.isfinite(self.support_threshold)
            or not 0.0 <= self.support_threshold <= 1.0
            or self.provenance.root_measurement
            != MeasurementIdentity.SEPARATOR_FIELD
        ):
            raise ValueError("separator measurement provenance is invalid")
        identities = tuple(line.observation_id for line in self.lines)
        if len(set(identities)) != len(identities):
            raise ValueError("separator line identities must be unique")

    @property
    def state(self) -> EvidenceState:
        return (
            EvidenceState.SUPPORTED
            if self.difference_support.size
            else EvidenceState.UNAVAILABLE
        )


class SeparatorObservationKind(str):
    def __new__(cls, value: str) -> "SeparatorObservationKind":
        if value not in {"edge_pair", "one_sided"}:
            raise ValueError("unknown separator observation kind")
        return str.__new__(cls, value)


@dataclass(frozen=True)
class SeparatorCorridorObservation:
    observation_id: ObservationId
    kind: SeparatorObservationKind
    previous_photo_end_px: FiniteInterval
    next_photo_start_px: FiniteInterval
    support: float
    source_line_ids: tuple[ObservationId, ...]
    learned_gutter_px: FiniteInterval | None
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, SeparatorObservationKind)
            or not math.isfinite(self.support)
            or self.support < 0.0
            or self.provenance.root_measurement
            != MeasurementIdentity.SEPARATOR_FIELD
            or not self.source_line_ids
        ):
            raise ValueError("separator corridor observation is invalid")
        if self.kind == "edge_pair":
            if (
                len(self.source_line_ids) != 2
                or self.learned_gutter_px is not None
                or self.previous_photo_end_px.maximum
                > self.next_photo_start_px.minimum
            ):
                raise ValueError("edge-pair observation must preserve line order")
        elif (
            len(self.source_line_ids) != 1
            or self.learned_gutter_px is None
        ):
            raise ValueError(
                "one-sided observation requires one line and learned gutter"
            )


@dataclass(frozen=True)
class SeparatorObservationWorkStatistics:
    raw_line_count: int
    pair_query_count: int
    compatible_pair_count: int
    retained_band_count: int
    one_sided_count: int
    truncated_pair_count: int

    def __post_init__(self) -> None:
        values = (
            self.raw_line_count,
            self.pair_query_count,
            self.compatible_pair_count,
            self.retained_band_count,
            self.one_sided_count,
            self.truncated_pair_count,
        )
        if any(value < 0 for value in values):
            raise ValueError("separator observation work cannot be negative")
        if self.pair_query_count != self.raw_line_count:
            raise ValueError("separator band search requires one query per line")
        if (
            self.retained_band_count > self.compatible_pair_count
            or self.truncated_pair_count
            != self.compatible_pair_count - self.retained_band_count
        ):
            raise ValueError("separator pair truncation receipt is inconsistent")


@dataclass(frozen=True)
class SeparatorObservationSet:
    gutter_px: FiniteInterval
    equality_interval_px: float
    learned_gutter_px: FiniteInterval | None
    bands: tuple[SeparatorBandObservation, ...]
    corridors: tuple[SeparatorCorridorObservation, ...]
    work: SeparatorObservationWorkStatistics

    def __post_init__(self) -> None:
        if self.equality_interval_px <= 0.0:
            raise ValueError("separator observation equality interval is invalid")
        if len(self.bands) != self.work.retained_band_count:
            raise ValueError("separator band receipt disagrees with observations")
        if (self.learned_gutter_px is not None) != (len(self.bands) >= 2):
            raise ValueError(
                "learned gutter requires at least two retained separator bands"
            )
        if (
            sum(item.kind == "one_sided" for item in self.corridors)
            != self.work.one_sided_count
        ):
            raise ValueError("one-sided separator receipt is inconsistent")


def _immutable_float32(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float32)
    result.flags.writeable = False
    return result


def observe_long_axis_separator_field(
    gray_lane: np.ndarray,
    lane_id: str,
) -> LongAxisSeparatorMeasurementField:
    """Measure the canonical cross-lane long-axis field once.

    This owner reads base-gray pixels directly. Positive-content components are
    intentionally neither an input nor a dependency.
    """
    started = perf_counter()
    if (
        not isinstance(gray_lane, np.ndarray)
        or gray_lane.ndim != 2
        or min(gray_lane.shape) <= 0
        or not lane_id
    ):
        raise ValueError("separator measurement requires one positive gray lane")
    short_extent, long_extent = gray_lane.shape
    provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.SEPARATOR_FIELD,
        observation_id=ObservationId(f"separator_field:{lane_id}"),
        dependencies=(MeasurementIdentity.BASE_GRAY,),
        description=(
            "exact cross-lane adjacent-pixel support field; independent of "
            "positive-content components, count, and placement offset"
        ),
    )
    if long_extent == 1:
        empty_support = _immutable_float32(np.empty(0, dtype=np.float32))
        empty_difference = _immutable_float32(np.empty(0, dtype=np.float32))
        return LongAxisSeparatorMeasurementField(
            lane_id=lane_id,
            long_extent_px=long_extent,
            short_extent_px=short_extent,
            difference_support=empty_support,
            mean_absolute_difference=empty_difference,
            support_threshold=0.0,
            lines=(),
            statistics=SeparatorMeasurementStatistics(
                domain_pixels=int(gray_lane.size),
                measured_adjacencies=0,
                line_observation_count=0,
                row_chunk_count=0,
                exact_measurement_count=1,
                exact_cache_hit_count=0,
                deterministic_seconds=perf_counter() - started,
                peak_temporary_bytes=0,
            ),
            provenance=provenance,
        )

    support_counts = np.zeros(long_extent - 1, dtype=np.int32)
    absolute_sums = np.zeros(long_extent - 1, dtype=np.int64)
    peak_temporary_bytes = support_counts.nbytes + absolute_sums.nbytes
    row_chunk_count = 0
    for row_start in range(0, short_extent, SEPARATOR_ROW_CHUNK_SIZE):
        row_stop = min(short_extent, row_start + SEPARATOR_ROW_CHUNK_SIZE)
        values = gray_lane[row_start:row_stop].astype(np.int16, copy=False)
        differences = np.abs(np.diff(values, axis=1))
        support_counts += np.count_nonzero(
            differences >= SEPARATOR_DIFFERENCE_THRESHOLD_U8,
            axis=0,
        ).astype(np.int32, copy=False)
        absolute_sums += np.sum(differences, axis=0, dtype=np.int64)
        peak_temporary_bytes = max(
            peak_temporary_bytes,
            support_counts.nbytes
            + absolute_sums.nbytes
            + values.nbytes
            + differences.nbytes,
        )
        row_chunk_count += 1

    difference_support = support_counts.astype(np.float32)
    difference_support /= np.float32(short_extent)
    mean_absolute_difference = absolute_sums.astype(np.float32)
    mean_absolute_difference /= np.float32(short_extent)
    support_threshold = max(
        SEPARATOR_MINIMUM_SUPPORT_FRACTION,
        float(np.percentile(difference_support, SEPARATOR_SUPPORT_PERCENTILE)),
    )

    admitted = difference_support >= support_threshold
    starts = np.flatnonzero(admitted & np.r_[True, ~admitted[:-1]])
    stops = (
        np.flatnonzero(admitted & np.r_[~admitted[1:], True]) + 1
    )
    lines: list[SeparatorLineObservation] = []
    for index, (start, stop) in enumerate(zip(starts, stops, strict=True)):
        peak_index = int(start + np.argmax(difference_support[start:stop]))
        observation_id = ObservationId(f"{lane_id}:separator_line:{index:06d}")
        line_provenance = MeasurementProvenance(
            root_measurement=MeasurementIdentity.SEPARATOR_FIELD,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.BASE_GRAY,),
            description=(
                "cross-lane adjacent-pixel support maximum within one "
                "threshold-connected long-axis interval"
            ),
        )
        lines.append(
            SeparatorLineObservation(
                observation_id=observation_id,
                boundary_px=float(peak_index + 1),
                interval_px=FiniteInterval(
                    float(start) + 0.5,
                    float(stop) + 0.5,
                ),
                support_fraction=float(difference_support[peak_index]),
                mean_absolute_difference=float(
                    mean_absolute_difference[peak_index]
                ),
                provenance=line_provenance,
            )
        )

    difference_support = _immutable_float32(difference_support)
    mean_absolute_difference = _immutable_float32(mean_absolute_difference)
    return LongAxisSeparatorMeasurementField(
        lane_id=lane_id,
        long_extent_px=long_extent,
        short_extent_px=short_extent,
        difference_support=difference_support,
        mean_absolute_difference=mean_absolute_difference,
        support_threshold=support_threshold,
        lines=tuple(lines),
        statistics=SeparatorMeasurementStatistics(
            domain_pixels=int(gray_lane.size),
            measured_adjacencies=int(short_extent * (long_extent - 1)),
            line_observation_count=len(lines),
            row_chunk_count=row_chunk_count,
            exact_measurement_count=1,
            exact_cache_hit_count=0,
            deterministic_seconds=perf_counter() - started,
            peak_temporary_bytes=int(peak_temporary_bytes),
        ),
        provenance=provenance,
    )


def separator_corridor_observations(
    field: LongAxisSeparatorMeasurementField,
    gutter_px: FiniteInterval,
    *,
    equality_interval_px: float,
) -> SeparatorObservationSet:
    """Create canonical edge-pair and one-sided observations.

    The result remains count- and offset-independent. Search corridors later
    select at most two of these observed facts.
    """
    if equality_interval_px <= 0.0:
        raise ValueError("separator equality interval must be positive")
    maximum_gap = max(
        equality_interval_px,
        gutter_px.maximum + equality_interval_px,
    )
    minimum_gap = max(
        0.0,
        gutter_px.minimum - equality_interval_px,
    )
    observations: list[SeparatorCorridorObservation] = []
    bands: list[SeparatorBandObservation] = []
    lines = field.lines
    positions = np.asarray(
        [line.boundary_px for line in lines],
        dtype=np.float64,
    )
    compatible_pair_count = 0
    retained_pair_count = 0
    unmatched_lines: list[SeparatorLineObservation] = []
    for left_index, left in enumerate(lines):
        lower_index = max(
            left_index + 1,
            int(
                np.searchsorted(
                    positions,
                    left.boundary_px + minimum_gap,
                    side="left",
                )
            ),
        )
        upper_index = int(
            np.searchsorted(
                positions,
                left.boundary_px + maximum_gap,
                side="right",
            )
        )
        compatible = tuple(lines[lower_index:upper_index])
        compatible_pair_count += len(compatible)
        retained = tuple(
            sorted(
                compatible,
                key=lambda right: (
                    abs(
                        (right.boundary_px - left.boundary_px)
                        - gutter_px.center
                    ),
                    -right.support_fraction,
                    str(right.observation_id),
                ),
            )[:SEPARATOR_BAND_SUCCESSOR_MAX]
        )
        retained_pair_count += len(retained)
        for right in retained:
            observation_id = ObservationId(
                f"{left.observation_id}+{right.observation_id}"
            )
            width_interval = FiniteInterval(
                max(
                    0.0,
                    right.interval_px.minimum - left.interval_px.maximum,
                ),
                max(
                    0.0,
                    right.interval_px.maximum - left.interval_px.minimum,
                ),
            )
            center_interval = FiniteInterval(
                (
                    left.interval_px.minimum
                    + right.interval_px.minimum
                )
                / 2.0,
                (
                    left.interval_px.maximum
                    + right.interval_px.maximum
                )
                / 2.0,
            )
            band = SeparatorBandObservation(
                observation_id=observation_id,
                leading_transition=left,
                trailing_transition=right,
                band_interval_px=FiniteInterval(
                    left.boundary_px,
                    right.boundary_px,
                ),
                width_interval_px=width_interval,
                center_interval_px=center_interval,
                support=left.support_fraction + right.support_fraction,
                appearance=(
                    "wide"
                    if width_interval.maximum > gutter_px.maximum
                    else "ordinary"
                ),
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.SEPARATOR_FIELD,
                    observation_id=observation_id,
                    dependencies=(MeasurementIdentity.BASE_GRAY,),
                    description=(
                        "ordered transition pair forming one typed separator "
                        "band within the component gutter search interval"
                    ),
                ),
            )
            bands.append(band)
            observations.append(
                SeparatorCorridorObservation(
                    observation_id=observation_id,
                    kind=SeparatorObservationKind("edge_pair"),
                    previous_photo_end_px=left.interval_px,
                    next_photo_start_px=right.interval_px,
                    support=band.support,
                    source_line_ids=(
                        left.observation_id,
                        right.observation_id,
                    ),
                    learned_gutter_px=None,
                    provenance=MeasurementProvenance(
                        root_measurement=MeasurementIdentity.SEPARATOR_FIELD,
                        observation_id=observation_id,
                        dependencies=(MeasurementIdentity.BASE_GRAY,),
                        description=(
                            "ordered separator edge pair admitted by the "
                            "typed component gutter interval"
                        ),
                    ),
                )
            )
        if not retained:
            unmatched_lines.append(left)

    learned_gutter = (
        FiniteInterval(
            min(item.width_interval_px.minimum for item in bands),
            max(item.width_interval_px.maximum for item in bands),
        )
        if len(bands) >= 2
        else None
    )
    if learned_gutter is not None:
        for left in unmatched_lines:
            observation_id = ObservationId(f"{left.observation_id}:one_sided")
            observations.append(
                SeparatorCorridorObservation(
                    observation_id=observation_id,
                    kind=SeparatorObservationKind("one_sided"),
                    previous_photo_end_px=left.interval_px,
                    next_photo_start_px=left.interval_px,
                    support=left.support_fraction,
                    source_line_ids=(left.observation_id,),
                    learned_gutter_px=learned_gutter,
                    provenance=MeasurementProvenance(
                        root_measurement=MeasurementIdentity.SEPARATOR_FIELD,
                        observation_id=observation_id,
                        dependencies=(MeasurementIdentity.BASE_GRAY,),
                        description=(
                            "one-sided separator/photo-edge observation; role "
                            "is assigned only inside a bounded local corridor"
                        ),
                    ),
                )
            )
    corridors = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.previous_photo_end_px.center,
                item.next_photo_start_px.center,
                str(item.observation_id),
            ),
        )
    )
    return SeparatorObservationSet(
        gutter_px=gutter_px,
        equality_interval_px=equality_interval_px,
        learned_gutter_px=learned_gutter,
        bands=tuple(
            sorted(
                bands,
                key=lambda item: (
                    item.band_interval_px.minimum,
                    item.band_interval_px.maximum,
                    str(item.observation_id),
                ),
            )
        ),
        corridors=corridors,
        work=SeparatorObservationWorkStatistics(
            raw_line_count=len(lines),
            pair_query_count=len(lines),
            compatible_pair_count=compatible_pair_count,
            retained_band_count=retained_pair_count,
            one_sided_count=sum(
                item.kind == "one_sided" for item in corridors
            ),
            truncated_pair_count=(
                compatible_pair_count - retained_pair_count
            ),
        ),
    )
