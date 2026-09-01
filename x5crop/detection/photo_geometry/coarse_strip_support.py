"""Role-free whole-strip observation used to localize precision queries.

The coarse pass deliberately knows nothing about START/END/TOP/BOTTOM. It
only turns two sparse, whole-lane measurements into conservative long- and
short-axis support intervals. Those intervals may reduce later raster work;
they never authorize phase, pitch, cross position, or output geometry.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from dataclasses import replace
from enum import Enum

import numpy as np

from ...domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from ...formats import OUTPUT_PROTECTION_SPEC
from ..source_core import SourceLaneEvidence
from .axis_layout import axis_interval, source_axes
from .broad_material_transition_measurement import (
    measure_broad_material_transition_regions,
)
from .corridors import source_lane_box
from .coarse_enclosing_model import (
    CoarseEnclosingResolution,
    CoarseEnclosingSupport,
    CoarseSharedDirection,
)
from .coarse_enclosing_support import (
    observe_coarse_short_axis_tracks,
)
from .measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
)
from .model import BoundaryAxis, PHOTO_BOUNDARY_MEASUREMENT_SPEC, QueryPurpose
from .registered_transition_measurement import (
    TraceMeasurement,
    measure_trace,
    measured_transition_peaks,
)
from .physical_identity import physical_observation_id
from .template_measurement_plan_model import TemplateMeasurementPlan


COARSE_STRIP_SUPPORT_REVISION = (
    "x5crop_coarse_strip_support_spatial_material_v2"
)
COARSE_SHARP_TRACE_COUNT = 5
COARSE_BROAD_REGION_TRACE_COUNT = 3 * 3


class CoarseSupportAuthority(str, Enum):
    PIXEL_OBSERVED = "pixel_observed"
    HOLDER_CONSERVATIVE = "holder_conservative"


@dataclass(frozen=True)
class CoarseAxisSupport:
    """One canonical-axis interval and the authority that produced it."""

    interval_px: FiniteInterval
    direct_interval_px: FiniteInterval | None
    authority: CoarseSupportAuthority
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.interval_px, FiniteInterval)
            or not isinstance(self.authority, CoarseSupportAuthority)
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("coarse axis support is invalid")
        if self.authority == CoarseSupportAuthority.PIXEL_OBSERVED:
            if (
                not isinstance(self.direct_interval_px, FiniteInterval)
                or not self.observation_ids
                or self.interval_px.minimum > self.direct_interval_px.minimum
                or self.interval_px.maximum < self.direct_interval_px.maximum
            ):
                raise ValueError("pixel coarse support lost its direct evidence")
        elif self.direct_interval_px is not None or self.observation_ids:
            raise ValueError("holder coarse support cannot claim pixel evidence")


@dataclass(frozen=True)
class CoarseStripSupportReceipt:
    registered_query_count: int
    trace_position_count: int
    coordinate_sample_count: int
    pixel_query_count: int
    peak_temporary_bytes: int
    aggregate_profile_count: int
    aggregate_endpoint_lookup_count: int

    def __post_init__(self) -> None:
        values = (
            self.registered_query_count,
            self.trace_position_count,
            self.coordinate_sample_count,
            self.pixel_query_count,
            self.peak_temporary_bytes,
            self.aggregate_profile_count,
            self.aggregate_endpoint_lookup_count,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("coarse support receipt is invalid")
        if self.registered_query_count != 2:
            raise ValueError("coarse support requires exactly two axis queries")
        if self.aggregate_profile_count != 2:
            raise ValueError("coarse support requires one aggregate per axis")


@dataclass(frozen=True)
class CoarseStripSupport:
    """Conservative support in canonical work-image long/short coordinates."""

    lane_id: str
    long_axis: CoarseAxisSupport
    short_axis: CoarseAxisSupport
    shared_direction: CoarseSharedDirection | None
    enclosing_support: CoarseEnclosingSupport | None
    enclosing_resolution: CoarseEnclosingResolution
    receipt: CoarseStripSupportReceipt

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not isinstance(self.long_axis, CoarseAxisSupport)
            or not isinstance(self.short_axis, CoarseAxisSupport)
            or (
                self.shared_direction is not None
                and not isinstance(
                    self.shared_direction,
                    CoarseSharedDirection,
                )
            )
            or (
                self.enclosing_support is not None
                and not isinstance(
                    self.enclosing_support,
                    CoarseEnclosingSupport,
                )
            )
            or not isinstance(
                self.enclosing_resolution,
                CoarseEnclosingResolution,
            )
            or not isinstance(self.receipt, CoarseStripSupportReceipt)
        ):
            raise ValueError("coarse strip support is invalid")
        if (
            self.enclosing_resolution.state == EvidenceState.SUPPORTED
        ) != (self.enclosing_support is not None):
            raise ValueError(
                "coarse enclosing support disagrees with its resolution"
            )


def _sparse_positions(values: tuple[int, ...], maximum: int = 5) -> tuple[int, ...]:
    if not values or maximum < 2:
        raise ValueError("coarse support requires a finite trace lattice")
    if len(values) <= maximum:
        return values
    indices = {
        int(round(index * (len(values) - 1) / (maximum - 1)))
        for index in range(maximum)
    }
    return tuple(values[index] for index in sorted(indices))


def _coarse_short_trace_lattices(
    values: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Return one registered union and the two fixed channel views."""

    sharp_positions = _sparse_positions(
        values,
        maximum=COARSE_SHARP_TRACE_COUNT,
    )
    broad_positions = _sparse_positions(
        values,
        maximum=COARSE_BROAD_REGION_TRACE_COUNT,
    )
    registered = tuple(sorted({*sharp_positions, *broad_positions}))
    ordinal_by_position = {
        position: ordinal for ordinal, position in enumerate(registered)
    }
    return (
        registered,
        tuple(ordinal_by_position[value] for value in sharp_positions),
        tuple(ordinal_by_position[value] for value in broad_positions),
    )


def _query(
    *,
    query_id: str,
    registration_index: int,
    lane_id: str,
    purpose: QueryPurpose,
    boundary_axis: BoundaryAxis,
    traces: tuple[int, ...],
    interval: FiniteInterval,
    expected_support_px: float,
    boundary_scale: PositiveInterval,
    trace_scale: PositiveInterval,
) -> PhotoBoundaryMeasurementQuery:
    halo = PHOTO_BOUNDARY_MEASUREMENT_SPEC.measurement_halo_px(
        boundary_scale.maximum
    )
    return PhotoBoundaryMeasurementQuery(
        query_id=query_id,
        registration_index=registration_index,
        lane_id=lane_id,
        purpose=purpose,
        boundary_axis=boundary_axis,
        trace_positions_px=traces,
        search_intervals_px=tuple(interval for _ in traces),
        transition_ownership_intervals_px=tuple(interval for _ in traces),
        expected_support_px=expected_support_px,
        boundary_axis_scale_px_per_mm=boundary_scale,
        trace_axis_scale_px_per_mm=trace_scale,
        measurement_halo_px=halo,
        registration_provenance_ids=("coarse-strip-support", query_id),
    )


def registered_coarse_support_queries(
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
) -> tuple[PhotoBoundaryMeasurementQuery, PhotoBoundaryMeasurementQuery]:
    """Register the complete role-free pass before reading its pixels."""

    if (
        measurement_plan.lane_id != lane.domain.lane_id
        or measurement_plan.layout != layout
    ):
        raise ValueError("coarse support requires the compiled lane plan")
    scales = lane.scan_canvas.axis_scales
    if scales is None:
        raise ValueError("coarse support requires scan-canvas scale authority")
    long_axis, short_axis = source_axes(layout)
    source_box = source_lane_box(lane, layout)
    projected = measurement_plan.projected_queries
    long_traces = _sparse_positions(projected.sequence_trace_positions_px)
    short_traces, _sharp_ordinals, _broad_ordinals = (
        _coarse_short_trace_lattices(
            projected.cross_trace_positions_px,
        )
    )
    identity = measurement_plan.plan_identity
    return (
        _query(
            query_id=(
                f"query:{COARSE_STRIP_SUPPORT_REVISION}:"
                f"{identity}:coarse-long"
            ),
            registration_index=0,
            lane_id=lane.domain.lane_id,
            purpose=QueryPurpose.COARSE_STRIP_LONG,
            boundary_axis=long_axis,
            traces=long_traces,
            interval=axis_interval(source_box, long_axis),
            expected_support_px=measurement_plan.template_spec.frame_height_px.maximum,
            boundary_scale=scales.width_axis_px_per_mm,
            trace_scale=scales.height_axis_px_per_mm,
        ),
        _query(
            query_id=(
                f"query:{COARSE_STRIP_SUPPORT_REVISION}:"
                f"{identity}:coarse-short"
            ),
            registration_index=1,
            lane_id=lane.domain.lane_id,
            purpose=QueryPurpose.COARSE_STRIP_SHORT,
            boundary_axis=short_axis,
            traces=short_traces,
            interval=axis_interval(source_box, short_axis),
            expected_support_px=measurement_plan.template_spec.frame_width_px.maximum,
            boundary_scale=scales.height_axis_px_per_mm,
            trace_scale=scales.width_axis_px_per_mm,
        ),
    )


def _aggregate_query_profile(
    field: PhotoBoundaryMeasurementField,
    query: PhotoBoundaryMeasurementQuery,
    *,
    aggregate_trace_ordinals: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Collapse one registered lattice into one role-free median profile."""

    if len(set(query.search_intervals_px)) != 1:
        raise ValueError("coarse aggregate requires one common search interval")
    if aggregate_trace_ordinals is not None and (
        not aggregate_trace_ordinals
        or tuple(sorted(set(aggregate_trace_ordinals)))
        != aggregate_trace_ordinals
        or aggregate_trace_ordinals[0] < 0
        or aggregate_trace_ordinals[-1] >= len(query.trace_positions_px)
    ):
        raise ValueError("coarse aggregate trace ordinals are invalid")
    samples = np.stack(
        tuple(
            field.source_gray[trace, :]
            if query.boundary_axis == BoundaryAxis.X
            else field.source_gray[:, trace]
            for trace in query.trace_positions_px
        ),
        axis=0,
    )
    selected = (
        samples
        if aggregate_trace_ordinals is None
        else samples[np.asarray(aggregate_trace_ordinals, dtype=np.intp)]
    )
    if selected.size == 0:
        raise ValueError("coarse aggregate requires at least one trace")
    profile = np.median(selected, axis=0).astype(np.uint8)
    return profile, samples, int(samples.nbytes + profile.nbytes)


def _aggregate_measurement_set(
    field: PhotoBoundaryMeasurementField,
    query: PhotoBoundaryMeasurementQuery,
    *,
    aggregate_trace_ordinals: tuple[int, ...] | None = None,
) -> tuple[PhotoBoundaryMeasurementSet, np.ndarray, np.ndarray, int]:
    """Read each coarse coordinate once; coarse queries do not emit edges."""

    profile, samples, temporary_bytes = _aggregate_query_profile(
        field,
        query,
        aggregate_trace_ordinals=aggregate_trace_ordinals,
    )
    coordinate_count = sum(
        int(interval.maximum - interval.minimum) + 1
        for interval in query.search_intervals_px
    )
    coverage = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=len(query.trace_positions_px),
        completed_trace_count=len(query.trace_positions_px),
        registered_coordinate_count=coordinate_count,
        completed_coordinate_count=coordinate_count,
        pixel_query_count=coordinate_count,
        streaming_block_count=max(
            1,
            int(
                np.ceil(
                    coordinate_count
                    / PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_streaming_block_pixels
                )
            ),
        ),
        peak_temporary_bytes=temporary_bytes,
        complete=True,
    )
    return (
        PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.SUPPORTED,
            transitions=(),
            cross_height_transitions=(),
            coverage=coverage,
        ),
        profile,
        samples,
        temporary_bytes,
    )


def _measure_coarse_short_trace_lattice(
    samples: np.ndarray,
    query: PhotoBoundaryMeasurementQuery,
) -> tuple[tuple[TraceMeasurement, ...], int]:
    """Measure each registered coarse-short trace once for both channels."""

    if (
        query.purpose != QueryPurpose.COARSE_STRIP_SHORT
        or samples.ndim != 2
        or samples.shape[0] != len(query.trace_positions_px)
    ):
        raise ValueError("coarse short trace lattice is invalid")
    measured = tuple(
        measure_trace(
            samples[ordinal],
            query.search_intervals_px[ordinal],
            query.boundary_axis_scale_px_per_mm.maximum,
            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            include_broad_material=True,
        )
        for ordinal in range(len(query.trace_positions_px))
    )
    return measured, int(
        samples.nbytes
        + max((item.temporary_bytes for item in measured), default=0)
    )


def _close_short_gaps(mask: np.ndarray, maximum_gap: int) -> np.ndarray:
    result = mask.copy()
    values = np.flatnonzero(mask)
    if values.size < 2:
        return result
    for left, right in zip(values, values[1:]):
        if 1 < right - left <= maximum_gap + 1:
            result[left : right + 1] = True
    return result


def _aggregate_long_hull(
    profile: np.ndarray,
    query: PhotoBoundaryMeasurementQuery,
    *,
    frame_width_px: PositiveInterval,
) -> tuple[FiniteInterval | None, tuple[ObservationId, ...], int, int]:
    """Find one dominant role-free material region on the whole long axis."""

    low, high = np.percentile(profile, (5.0, 99.5))
    contrast = float(high - low)
    if contrast < 8.0:
        return None, (), 0, int(profile.nbytes)
    threshold = float(high) - max(4.0, 0.035 * contrast)
    material = profile.astype(np.float64, copy=False) < threshold
    density_window = max(
        3,
        2
        * PHOTO_BOUNDARY_MEASUREMENT_SPEC.local_window_px(
            query.boundary_axis_scale_px_per_mm.maximum
        ),
    )
    density = np.convolve(
        material.astype(np.int16),
        np.ones(density_window, dtype=np.int16),
        mode="same",
    )
    supported = density >= max(1, int(np.ceil(0.05 * density_window)))
    supported = _close_short_gaps(
        supported,
        max(1, int(np.ceil(frame_width_px.maximum))),
    )
    changes = np.flatnonzero(np.diff(supported.astype(np.int8))) + 1
    temporary_bytes = int(
        profile.nbytes
        + material.nbytes
        + density.nbytes
        + supported.nbytes
        + changes.nbytes
    )
    boundaries = (0, *changes.tolist(), supported.size)
    runs = tuple(
        (start, stop)
        for start, stop in zip(boundaries, boundaries[1:])
        if supported[start] and stop - start >= frame_width_px.minimum * 0.5
    )
    if not runs:
        return None, (), len(changes), temporary_bytes
    start, stop = max(runs, key=lambda item: item[1] - item[0])
    direct = FiniteInterval(float(start), float(stop - 1))
    return (
        direct,
        (
            physical_observation_id(
                "coarse-long-support",
                query.query_id,
                tuple(query.trace_positions_px),
                f"{direct.minimum:.6f}",
                f"{direct.maximum:.6f}",
            ),
        ),
        len(changes),
        temporary_bytes,
    )


def _aggregate_short_hull(
    measurement: PhotoBoundaryMeasurementSet,
    *,
    expected_height_px: FiniteInterval,
    profile: np.ndarray,
    aggregate_temporary: int,
) -> tuple[FiniteInterval | None, tuple[ObservationId, ...], int, int]:
    """Find one bounded whole-strip support without materializing pairs.

    This hull only localizes later precision queries.  It cannot authorize a
    TOP/BOTTOM role, cross placement, or output boundary.
    """

    query = measurement.query
    measured = measure_trace(
        profile,
        query.search_intervals_px[0],
        query.boundary_axis_scale_px_per_mm.maximum,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    )
    peaks = measured_transition_peaks(
        measured,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        split_gradient_reversals=True,
    )
    positions = tuple(item.canonical_coordinate for item in peaks)
    maximum_span = (
        OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        * expected_height_px.maximum
    )
    top_indices: list[int] = []
    bottom_indices: list[int] = []
    lookup_count = 0
    for top_index, top in enumerate(peaks):
        lower = bisect_left(
            positions,
            top.canonical_coordinate + expected_height_px.minimum,
            lo=top_index + 1,
        )
        upper = bisect_right(
            positions,
            top.canonical_coordinate + maximum_span,
            lo=lower,
        )
        lookup_count += 2
        if lower < upper:
            top_indices.append(top_index)
            bottom_indices.append(upper - 1)
    temporary_bytes = aggregate_temporary + measured.temporary_bytes
    if not top_indices:
        return None, (), temporary_bytes, lookup_count
    direct = FiniteInterval(
        min(
            peaks[index].physical_position_interval.minimum
            for index in top_indices
        ),
        max(
            peaks[index].physical_position_interval.maximum
            for index in bottom_indices
        ),
    )
    if direct.width > maximum_span:
        return None, (), temporary_bytes, lookup_count
    return (
        direct,
        (
            physical_observation_id(
                "coarse-short-support",
                query.query_id,
                tuple(query.trace_positions_px),
                f"{direct.minimum:.6f}",
                f"{direct.maximum:.6f}",
            ),
        ),
        temporary_bytes,
        lookup_count,
    )


def _expanded_support(
    direct: FiniteInterval,
    authority: FiniteInterval,
    *,
    margin_px: float,
    minimum_width_px: float,
) -> FiniteInterval:
    if margin_px < 0.0 or minimum_width_px <= 0.0:
        raise ValueError("coarse support expansion is invalid")
    lower = max(authority.minimum, direct.minimum - margin_px)
    upper = min(authority.maximum, direct.maximum + margin_px)
    target = min(authority.width, max(minimum_width_px, upper - lower))
    center = (lower + upper) / 2.0
    lower, upper = center - target / 2.0, center + target / 2.0
    if lower < authority.minimum:
        upper += authority.minimum - lower
        lower = authority.minimum
    if upper > authority.maximum:
        lower -= upper - authority.maximum
        upper = authority.maximum
    return FiniteInterval(
        max(authority.minimum, lower),
        min(authority.maximum, upper),
    )


def _axis_support(
    direct: FiniteInterval | None,
    observation_ids: tuple[ObservationId, ...],
    authority: FiniteInterval,
    *,
    margin_px: float,
    minimum_width_px: float,
) -> CoarseAxisSupport:
    if direct is None:
        return CoarseAxisSupport(
            authority,
            None,
            CoarseSupportAuthority.HOLDER_CONSERVATIVE,
            (),
        )
    return CoarseAxisSupport(
        _expanded_support(
            direct,
            authority,
            margin_px=margin_px,
            minimum_width_px=minimum_width_px,
        ),
        direct,
        CoarseSupportAuthority.PIXEL_OBSERVED,
        observation_ids,
    )


def observe_coarse_strip_support(
    field: PhotoBoundaryMeasurementField,
    lane: SourceLaneEvidence,
    *,
    layout: str,
    measurement_plan: TemplateMeasurementPlan,
) -> tuple[CoarseStripSupport, tuple[PhotoBoundaryMeasurementSet, ...]]:
    """Execute one bounded whole-strip pass and derive local query support."""

    queries = registered_coarse_support_queries(
        lane,
        layout=layout,
        measurement_plan=measurement_plan,
    )
    (
        registered_short_traces,
        sharp_trace_ordinals,
        broad_trace_ordinals,
    ) = _coarse_short_trace_lattices(
        measurement_plan.projected_queries.cross_trace_positions_px,
    )
    if queries[1].trace_positions_px != registered_short_traces:
        raise ValueError("coarse short trace registration changed after planning")
    long_measurement, long_profile, _long_samples, long_temporary = (
        _aggregate_measurement_set(field, queries[0])
    )
    short_measurement, short_profile, short_samples, short_temporary = (
        _aggregate_measurement_set(
            field,
            queries[1],
            aggregate_trace_ordinals=sharp_trace_ordinals,
        )
    )
    short_trace_measurements, short_trace_temporary = (
        _measure_coarse_short_trace_lattice(
            short_samples,
            short_measurement.query,
        )
    )
    broad_regions, broad_temporary = (
        measure_broad_material_transition_regions(
            short_measurement.query,
            short_trace_measurements,
            trace_ordinals=broad_trace_ordinals,
        )
    )
    short_measurement = replace(
        short_measurement,
        broad_material_transitions=broad_regions,
    )
    measurements = (long_measurement, short_measurement)
    work = lane.domain.work_box
    long_authority = FiniteInterval(float(work.left), float(work.right - 1))
    short_authority = FiniteInterval(float(work.top), float(work.bottom - 1))
    scales = lane.scan_canvas.axis_scales
    assert scales is not None
    direct_long, long_ids, long_lookups, long_analysis_temporary = (
        _aggregate_long_hull(
            long_profile,
            measurements[0].query,
            frame_width_px=measurement_plan.template_spec.frame_width_px,
        )
    )
    direct_short, short_ids, aggregate_temporary, endpoint_lookups = (
        _aggregate_short_hull(
            measurements[1],
            expected_height_px=measurement_plan.template_spec.frame_height_px,
            profile=short_profile,
            aggregate_temporary=short_temporary,
        )
    )
    measurements = (
        replace(
            measurements[0],
            coverage=replace(
                measurements[0].coverage,
                peak_temporary_bytes=max(
                    long_temporary,
                    long_analysis_temporary,
                ),
            ),
        ),
        replace(
            measurements[1],
            coverage=replace(
                measurements[1].coverage,
                peak_temporary_bytes=max(
                    aggregate_temporary,
                    short_trace_temporary,
                    broad_temporary,
                ),
            ),
        ),
    )
    template = measurement_plan.template_spec
    (
        shared_direction,
        enclosing_support,
        enclosing_resolution,
    ) = observe_coarse_short_axis_tracks(
        measurements[1],
        trace_measurements=short_trace_measurements,
        sharp_trace_ordinals=sharp_trace_ordinals,
        aggregate_interval_px=direct_short,
        expected_height_px=template.frame_height_px,
        reference_trace_px=long_authority.center,
    )
    group_span = (
        template.frame_width_px.maximum
        + max(0, template.count - 1) * template.pitch_px.maximum
    )
    long_support = _axis_support(
        direct_long,
        long_ids,
        long_authority,
        margin_px=template.pitch_px.maximum,
        minimum_width_px=group_span + 2.0 * template.pitch_px.maximum,
    )
    support_height = (
        OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        * template.frame_height_px.maximum
        + 2.0 * measurement_plan.projected_queries.measurement_halo_px
    )
    short_support = _axis_support(
        direct_short,
        short_ids,
        short_authority,
        margin_px=0.05 * template.frame_height_px.maximum,
        minimum_width_px=support_height,
    )
    coverage = tuple(item.coverage for item in measurements)
    receipt = CoarseStripSupportReceipt(
        registered_query_count=len(measurements),
        trace_position_count=sum(
            len(item.query.trace_positions_px) for item in measurements
        ),
        coordinate_sample_count=sum(
            item.registered_coordinate_count for item in coverage
        ),
        pixel_query_count=sum(item.pixel_query_count for item in coverage),
        peak_temporary_bytes=max(
            long_temporary,
            long_analysis_temporary,
            aggregate_temporary,
            short_trace_temporary,
            broad_temporary,
            *(item.peak_temporary_bytes for item in coverage),
        ),
        aggregate_profile_count=2,
        aggregate_endpoint_lookup_count=long_lookups + endpoint_lookups,
    )
    return (
        CoarseStripSupport(
            lane.domain.lane_id,
            long_support,
            short_support,
            shared_direction,
            enclosing_support,
            enclosing_resolution,
            receipt,
        ),
        measurements,
    )
