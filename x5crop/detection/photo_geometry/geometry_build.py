from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...domain import FiniteInterval, PositiveInterval
from ..source_core import SourceLaneEvidence
from .model import (
    BoundaryAxis,
    BoundaryRole,
    BoundarySource,
    FrameBoundaryGeometry,
    FramePhotoGeometry,
    PhotoBoundaryObservation,
    SourceCoordinateLine,
)
from .selection import (
    line_coordinate_at_trace,
    line_coordinate_interval_at_trace,
)


@dataclass(frozen=True)
class ContentComponentGeometryIndex:
    positive_cells: np.ndarray
    long_spans_px: np.ndarray
    short_spans_px: np.ndarray
    long_centers_px: np.ndarray

    def __post_init__(self) -> None:
        arrays = (
            self.positive_cells,
            self.long_spans_px,
            self.short_spans_px,
            self.long_centers_px,
        )
        if (
            len({array.shape for array in arrays}) != 1
            or any(array.ndim != 1 for array in arrays)
            or any(array.flags.writeable for array in arrays)
        ):
            raise ValueError("content geometry index must be aligned and immutable")

    @property
    def temporary_bytes(self) -> int:
        return sum(array.nbytes for array in (
            self.positive_cells,
            self.long_spans_px,
            self.short_spans_px,
            self.long_centers_px,
        ))


def content_component_geometry_index(
    lane: SourceLaneEvidence,
) -> ContentComponentGeometryIndex:
    components = lane.content.components
    count = len(components)
    positive_cells = np.fromiter(
        (component.positive_cells for component in components),
        dtype=np.int64,
        count=count,
    )
    long_spans = np.fromiter(
        (
            component.footprint.right - component.footprint.left
            for component in components
        ),
        dtype=np.int32,
        count=count,
    )
    short_spans = np.fromiter(
        (
            component.footprint.bottom - component.footprint.top
            for component in components
        ),
        dtype=np.int32,
        count=count,
    )
    long_centers = np.fromiter(
        (
            (component.footprint.left + component.footprint.right)
            / 2.0
            for component in components
        ),
        dtype=np.float64,
        count=count,
    )
    for array in (
        positive_cells,
        long_spans,
        short_spans,
        long_centers,
    ):
        array.flags.writeable = False
    return ContentComponentGeometryIndex(
        positive_cells=positive_cells,
        long_spans_px=long_spans,
        short_spans_px=short_spans,
        long_centers_px=long_centers,
    )


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{sha256(payload).hexdigest()[:24]}"


def known_content_short_interval(
    lane: SourceLaneEvidence,
    *,
    component_index: ContentComponentGeometryIndex,
    long_axis_interval_px: FiniteInterval,
    expected_short_extent_px: float,
    smoothing_px: int,
) -> FiniteInterval | None:
    """Selection-only support from stable positive-content components.

    The source content detector intentionally retains small components for
    diagnostics.  Those components are not all strong enough to become a hard
    containment fact.  Restrict this assessment to components whose size is
    physically compatible with one aperture, whose positive area is material
    at the current source scale, and whose center belongs to the proposed
    long-axis aperture.  This never creates or moves a photo edge.
    """

    table = lane.content.row_run_table
    if (
        table.run_count == 0
        or expected_short_extent_px <= 0.0
        or long_axis_interval_px.width <= 0.0
    ):
        return None
    minimum_component_cells = max(
        64,
        int(
            math.ceil(
                0.0001
                * long_axis_interval_px.width
                * expected_short_extent_px
            )
        ),
    )
    maximum_long_span_px = long_axis_interval_px.width * 1.25
    maximum_short_span_px = expected_short_extent_px * 1.25
    if component_index.positive_cells.size != len(
        lane.content.components
    ):
        raise ValueError("content geometry index does not match the lane")
    eligible = (
        component_index.positive_cells >= minimum_component_cells
    )
    eligible &= component_index.long_spans_px <= maximum_long_span_px
    eligible &= component_index.short_spans_px <= maximum_short_span_px
    eligible &= (
        component_index.long_centers_px
        >= long_axis_interval_px.minimum - 0.5
    )
    eligible &= (
        component_index.long_centers_px
        <= long_axis_interval_px.maximum + 0.5
    )
    if not bool(np.any(eligible)):
        return None
    selected_runs = eligible[table.component_indices]
    if not bool(np.any(selected_runs)):
        return None

    domain = lane.domain.work_box
    left = int(math.floor(long_axis_interval_px.minimum))
    right = int(math.ceil(long_axis_interval_px.maximum))
    if right <= left:
        return None
    overlaps = np.maximum(
        0,
        np.minimum(table.rights[selected_runs], right)
        - np.maximum(table.lefts[selected_runs], left),
    )
    support = np.bincount(
        table.rows[selected_runs] - domain.top,
        weights=overlaps,
        minlength=domain.height,
    ).astype(np.float64, copy=False)
    support /= float(right - left)
    coordinate_offset = domain.top

    window = max(1, smoothing_px)
    kernel = np.full(window, 1.0 / float(window), dtype=np.float64)
    smoothed = np.convolve(support, kernel, mode="same")
    maximum = float(smoothed.max(initial=0.0))
    if maximum <= 0.0:
        return None
    active = np.flatnonzero(smoothed >= maximum * 0.10)
    if not active.size:
        return None
    return FiniteInterval(
        float(coordinate_offset + int(active[0])),
        float(coordinate_offset + int(active[-1]) + 1),
    )


@dataclass(frozen=True)
class FrameShortAxisCandidate:
    candidate_id: str
    top: FrameBoundaryGeometry
    bottom: FrameBoundaryGeometry
    observed_edge_count: int
    known_content_contained: bool
    support_count: int
    continuous_support_fraction: float
    uncertainty_px: float
    residual_px: float
    protected_short_interval_px: FiniteInterval
    angle_interval_degrees: FiniteInterval
    observed_height_interval_px: FiniteInterval | None


def _angles_overlap(
    left: FiniteInterval,
    right: FiniteInterval,
) -> bool:
    return (
        left.minimum <= right.maximum
        and right.minimum <= left.maximum
    )


def _observed_edge(
    observation: PhotoBoundaryObservation,
    role: BoundaryRole,
) -> FrameBoundaryGeometry:
    return FrameBoundaryGeometry(
        role=role,
        line=observation.line,
        offset_interval_px=observation.offset_interval_px,
        source=BoundarySource.OBSERVED,
        observation_ids=(observation.observation_id,),
        named_inference=None,
    )


def _parallel_line_at_position(
    template: SourceCoordinateLine,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
    position_px: float,
    support_projection_px: FiniteInterval,
) -> SourceCoordinateLine:
    offset = (
        template.normal_x * position_px
        + template.normal_y * trace_coordinate_px
        if boundary_axis == BoundaryAxis.X
        else template.normal_x * trace_coordinate_px
        + template.normal_y * position_px
    )
    return SourceCoordinateLine(
        normal_x=template.normal_x,
        normal_y=template.normal_y,
        offset_px=offset,
        support_projection_px=support_projection_px,
        source_axis_long=template.source_axis_long,
    )


def _inferred_opposite(
    observation: PhotoBoundaryObservation,
    *,
    observed_role: BoundaryRole,
    inferred_role: BoundaryRole,
    short_axis: BoundaryAxis,
    reference_long_px: float,
    height_px: PositiveInterval,
    support_projection_px: FiniteInterval,
) -> FrameBoundaryGeometry:
    observed_position = line_coordinate_interval_at_trace(
        observation,
        boundary_axis=short_axis,
        trace_coordinate_px=reference_long_px,
    )
    if observed_role == BoundaryRole.TOP:
        inferred_position = FiniteInterval(
            observed_position.minimum + height_px.minimum,
            observed_position.maximum + height_px.maximum,
        )
    else:
        inferred_position = FiniteInterval(
            observed_position.minimum - height_px.maximum,
            observed_position.maximum - height_px.minimum,
        )
    line = _parallel_line_at_position(
        observation.line,
        boundary_axis=short_axis,
        trace_coordinate_px=reference_long_px,
        position_px=inferred_position.center,
        support_projection_px=support_projection_px,
    )
    component = (
        line.normal_x
        if short_axis == BoundaryAxis.X
        else line.normal_y
    )
    offsets = tuple(
        line.offset_px
        + (value - inferred_position.center) * component
        for value in (
            inferred_position.minimum,
            inferred_position.maximum,
        )
    )
    return FrameBoundaryGeometry(
        role=inferred_role,
        line=line,
        offset_interval_px=FiniteInterval(min(offsets), max(offsets)),
        source=BoundarySource.INFERRED_OPPOSITE_EDGE,
        observation_ids=(observation.observation_id,),
        named_inference=(
            f"{inferred_role.value}_from_observed_"
            f"{observed_role.value}_rotation_aperture_scale_interval"
        ),
    )


def _safe_short_bounds(
    top: FrameBoundaryGeometry,
    bottom: FrameBoundaryGeometry,
    *,
    short_axis: BoundaryAxis,
    reference_long_px: float,
    interpolation_allowance_px: float,
    protection_px: float,
) -> FiniteInterval:
    def interval(edge: FrameBoundaryGeometry) -> FiniteInterval:
        line = edge.line
        component = (
            line.normal_x
            if short_axis == BoundaryAxis.X
            else line.normal_y
        )
        cross = (
            line.normal_y
            if short_axis == BoundaryAxis.X
            else line.normal_x
        )
        values = tuple(
            (offset - cross * reference_long_px) / component
            for offset in (
                edge.offset_interval_px.minimum,
                edge.offset_interval_px.maximum,
            )
        )
        return FiniteInterval(min(values), max(values))

    top_interval = interval(top)
    bottom_interval = interval(bottom)
    return FiniteInterval(
        top_interval.minimum
        - interpolation_allowance_px
        - protection_px,
        bottom_interval.maximum
        + interpolation_allowance_px
        + protection_px,
    )


def _candidate_dominates(
    left: FrameShortAxisCandidate,
    right: FrameShortAxisCandidate,
) -> bool:
    no_worse = (
        left.observed_edge_count >= right.observed_edge_count
        and left.known_content_contained
        >= right.known_content_contained
        and left.support_count >= right.support_count
        and left.continuous_support_fraction
        >= right.continuous_support_fraction
        and left.uncertainty_px <= right.uncertainty_px
        and left.residual_px <= right.residual_px
    )
    strictly_better = (
        left.observed_edge_count > right.observed_edge_count
        or left.known_content_contained
        > right.known_content_contained
        or left.support_count > right.support_count
        or left.continuous_support_fraction
        > right.continuous_support_fraction
        or left.uncertainty_px < right.uncertainty_px
        or left.residual_px < right.residual_px
    )
    return no_worse and strictly_better


def select_frame_short_axis_candidates(
    top_observations: tuple[PhotoBoundaryObservation, ...],
    bottom_observations: tuple[PhotoBoundaryObservation, ...],
    *,
    short_axis: BoundaryAxis,
    reference_long_px: float,
    height_px: PositiveInterval,
    support_projection_px: FiniteInterval,
    lane_short_interval_px: FiniteInterval,
    known_content_interval_px: FiniteInterval | None,
    interpolation_allowance_px: float,
    protection_px: float,
    scanner_border_exclusion_px: float,
) -> tuple[FrameShortAxisCandidate, ...]:
    raw: list[FrameShortAxisCandidate] = []
    positioned_bottom = tuple(
        sorted(
            (
                (
                    line_coordinate_interval_at_trace(
                        observation,
                        boundary_axis=short_axis,
                        trace_coordinate_px=reference_long_px,
                    ),
                    observation,
                )
                for observation in bottom_observations
            ),
            key=lambda item: (
                item[0].center,
                str(item[1].observation_id),
            ),
        )
    )
    first_bottom_index = 0
    for top_observation in top_observations:
        top_interval = line_coordinate_interval_at_trace(
            top_observation,
            boundary_axis=short_axis,
            trace_coordinate_px=reference_long_px,
        )
        minimum_bottom = top_interval.minimum + height_px.minimum
        while (
            first_bottom_index < len(positioned_bottom)
            and positioned_bottom[first_bottom_index][0].maximum
            < minimum_bottom
        ):
            first_bottom_index += 1
        bottom_index = first_bottom_index
        maximum_bottom = top_interval.maximum + height_px.maximum
        while bottom_index < len(positioned_bottom):
            bottom_interval, bottom_observation = positioned_bottom[
                bottom_index
            ]
            if bottom_interval.minimum > maximum_bottom:
                break
            height = FiniteInterval(
                bottom_interval.minimum - top_interval.maximum,
                bottom_interval.maximum - top_interval.minimum,
            )
            physically_compatible = (
                height.maximum >= height_px.minimum
                and height.minimum <= height_px.maximum
                and _angles_overlap(
                    top_observation.angle_interval_degrees,
                    bottom_observation.angle_interval_degrees,
                )
            )
            scanner_pair = (
                top_interval.minimum
                <= lane_short_interval_px.minimum
                + scanner_border_exclusion_px
                and bottom_interval.maximum
                >= lane_short_interval_px.maximum
                - scanner_border_exclusion_px
            )
            if physically_compatible and not scanner_pair:
                top = _observed_edge(
                    top_observation,
                    BoundaryRole.TOP,
                )
                bottom = _observed_edge(
                    bottom_observation,
                    BoundaryRole.BOTTOM,
                )
                safe = _safe_short_bounds(
                    top,
                    bottom,
                    short_axis=short_axis,
                    reference_long_px=reference_long_px,
                    interpolation_allowance_px=interpolation_allowance_px,
                    protection_px=protection_px,
                )
                contained = (
                    known_content_interval_px is None
                    or (
                        safe.minimum
                        <= known_content_interval_px.minimum
                        and safe.maximum
                        >= known_content_interval_px.maximum
                    )
                )
                raw.append(
                    FrameShortAxisCandidate(
                        candidate_id=_stable_id(
                            "short-pair",
                            top_observation.observation_id,
                            bottom_observation.observation_id,
                        ),
                        top=top,
                        bottom=bottom,
                        observed_edge_count=2,
                        known_content_contained=contained,
                        support_count=(
                            top_observation.trace_support_count
                            + bottom_observation.trace_support_count
                        ),
                        continuous_support_fraction=min(
                            top_observation.continuous_support_fraction,
                            bottom_observation.continuous_support_fraction,
                        ),
                        uncertainty_px=(
                            top_observation.measurement_uncertainty_px
                            + bottom_observation.measurement_uncertainty_px
                        ),
                        residual_px=(
                            top_observation.fit_residual_px
                            + bottom_observation.fit_residual_px
                        ),
                        protected_short_interval_px=safe,
                        angle_interval_degrees=FiniteInterval(
                            max(
                                top_observation
                                .angle_interval_degrees.minimum,
                                bottom_observation
                                .angle_interval_degrees.minimum,
                            ),
                            min(
                                top_observation
                                .angle_interval_degrees.maximum,
                                bottom_observation
                                .angle_interval_degrees.maximum,
                            ),
                        ),
                        observed_height_interval_px=height,
                    )
                )
            bottom_index += 1

    observed_pair_found = bool(raw)
    if not observed_pair_found:
        for observation in top_observations:
            top = _observed_edge(observation, BoundaryRole.TOP)
            bottom = _inferred_opposite(
                observation,
                observed_role=BoundaryRole.TOP,
                inferred_role=BoundaryRole.BOTTOM,
                short_axis=short_axis,
                reference_long_px=reference_long_px,
                height_px=height_px,
                support_projection_px=support_projection_px,
            )
            safe = _safe_short_bounds(
                top,
                bottom,
                short_axis=short_axis,
                reference_long_px=reference_long_px,
                interpolation_allowance_px=interpolation_allowance_px,
                protection_px=protection_px,
            )
            raw.append(
                FrameShortAxisCandidate(
                    candidate_id=_stable_id(
                        "short-one-sided-top",
                        observation.observation_id,
                    ),
                    top=top,
                    bottom=bottom,
                    observed_edge_count=1,
                    known_content_contained=(
                        known_content_interval_px is None
                        or (
                            safe.minimum
                            <= known_content_interval_px.minimum
                            and safe.maximum
                            >= known_content_interval_px.maximum
                        )
                    ),
                    support_count=observation.trace_support_count,
                    continuous_support_fraction=(
                        observation.continuous_support_fraction
                    ),
                    uncertainty_px=(
                        observation.measurement_uncertainty_px
                        + bottom.outward_uncertainty_px
                    ),
                    residual_px=observation.fit_residual_px,
                    protected_short_interval_px=safe,
                    angle_interval_degrees=(
                        observation.angle_interval_degrees
                    ),
                    observed_height_interval_px=None,
                )
            )
    if not observed_pair_found:
        for observation in bottom_observations:
            bottom = _observed_edge(observation, BoundaryRole.BOTTOM)
            top = _inferred_opposite(
                observation,
                observed_role=BoundaryRole.BOTTOM,
                inferred_role=BoundaryRole.TOP,
                short_axis=short_axis,
                reference_long_px=reference_long_px,
                height_px=height_px,
                support_projection_px=support_projection_px,
            )
            safe = _safe_short_bounds(
                top,
                bottom,
                short_axis=short_axis,
                reference_long_px=reference_long_px,
                interpolation_allowance_px=interpolation_allowance_px,
                protection_px=protection_px,
            )
            raw.append(
                FrameShortAxisCandidate(
                    candidate_id=_stable_id(
                        "short-one-sided-bottom",
                        observation.observation_id,
                    ),
                    top=top,
                    bottom=bottom,
                    observed_edge_count=1,
                    known_content_contained=(
                        known_content_interval_px is None
                        or (
                            safe.minimum
                            <= known_content_interval_px.minimum
                            and safe.maximum
                            >= known_content_interval_px.maximum
                        )
                    ),
                    support_count=observation.trace_support_count,
                    continuous_support_fraction=(
                        observation.continuous_support_fraction
                    ),
                    uncertainty_px=(
                        observation.measurement_uncertainty_px
                        + top.outward_uncertainty_px
                    ),
                    residual_px=observation.fit_residual_px,
                    protected_short_interval_px=safe,
                    angle_interval_degrees=(
                        observation.angle_interval_degrees
                    ),
                    observed_height_interval_px=None,
                )
            )

    if any(item.known_content_contained for item in raw):
        raw = [item for item in raw if item.known_content_contained]
    if raw:
        maximum_observed_edges = max(
            item.observed_edge_count for item in raw
        )
        raw = [
            item
            for item in raw
            if item.observed_edge_count == maximum_observed_edges
        ]
    protection_absorbers = [
        item
        for item in raw
        if all(
            item.protected_short_interval_px.minimum
            <= other.protected_short_interval_px.minimum
            and item.protected_short_interval_px.maximum
            >= other.protected_short_interval_px.maximum
            for other in raw
        )
    ]
    if protection_absorbers:
        raw = protection_absorbers
    nondominated = tuple(
        item
        for item in raw
        if not any(
            other is not item and _candidate_dominates(other, item)
            for other in raw
        )
    )
    return tuple(
        sorted(
            nondominated,
            key=lambda item: (
                -item.observed_edge_count,
                -item.known_content_contained,
                -item.support_count,
                -item.continuous_support_fraction,
                item.uncertainty_px,
                item.residual_px,
                item.candidate_id,
            ),
        )
    )


def build_frame_photo_geometry(
    *,
    lane_id: str,
    lane_ordinal: int,
    start: FrameBoundaryGeometry,
    end: FrameBoundaryGeometry,
    short_candidate: FrameShortAxisCandidate,
    content_component_ids: tuple[str, ...],
    ownership: str,
) -> FramePhotoGeometry:
    top = short_candidate.top
    bottom = short_candidate.bottom
    polygon = (
        top.line.intersection(start.line),
        top.line.intersection(end.line),
        bottom.line.intersection(end.line),
        bottom.line.intersection(start.line),
    )
    geometry_id = _stable_id(
        "frame-photo-geometry",
        lane_id,
        lane_ordinal,
        *(
            f"{edge.role.value}:{edge.source.value}:"
            f"{edge.line.offset_px:.9f}:"
            f"{edge.offset_interval_px.minimum:.9f}:"
            f"{edge.offset_interval_px.maximum:.9f}"
            for edge in (top, bottom, start, end)
        ),
    )
    return FramePhotoGeometry(
        geometry_id=geometry_id,
        lane_id=lane_id,
        lane_ordinal=lane_ordinal,
        top=top,
        bottom=bottom,
        start=start,
        end=end,
        source_polygon=polygon,
        content_component_ids=content_component_ids,
        ownership=ownership,
    )
