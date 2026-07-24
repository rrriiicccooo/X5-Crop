from __future__ import annotations

from bisect import bisect_left
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations, product
import math

from ...configuration.photo_edges import PhotoEdgeDetectionParameters
from ...domain import (
    EvidenceState,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...formats import FrameSizeMm
from ...geometry.affine import AFFINE_INVERTIBILITY_FLOOR
from ..evidence.photo_edges import (
    DualLaneJointCell,
    DualLanePhotoEdgeJointRegion,
    NormalRegionCell,
    NormalRegionWitness,
    NumericInterval,
    PhotoEdgeFact,
    PhotoEdgeFragmentSummary,
    PhotoEdgeLineRegionCell,
    PhotoEdgeLineWitness,
    PhotoEdgeNormalFeasibleRegion,
    PhotoEdgeObservation,
    PhotoEdgePairGeometry,
    PhotoEdgePairHypothesis,
    PhotoEdgePhysicalLabel,
    PhotoEdgeSearchCorridor,
    PhotoEdgeCoordinateSpace,
    RegionSetRelation,
)
from ..evidence.scan_canvas import CanvasPixelScale
from .photo_edge_observation import PhotoEdgeFragment


_POLYGON_EPSILON = 1e-12
_ACTIVE_CONSTRAINT_TOLERANCE = 1e-9
_SLOPE_SIGN_BOUNDARY = 0.0
_MULTI_FRAGMENT_GROUP_MINIMUM_SIZE = 2


@dataclass
class GeometryWorkBudget:
    maximum_region_cells: int
    maximum_consensus_states: int
    consumed_region_cells: int = 0
    consumed_consensus_states: int = 0
    exhausted: bool = False
    discovery_incomplete: bool = False

    def consume_region_cell(self) -> bool:
        if self.consumed_region_cells >= self.maximum_region_cells:
            self.exhausted = True
            return False
        self.consumed_region_cells += 1
        return True

    def consume_consensus_state(self) -> bool:
        if self.consumed_consensus_states >= self.maximum_consensus_states:
            self.exhausted = True
            return False
        self.consumed_consensus_states += 1
        return True

@dataclass(frozen=True)
class PhotoEdgeGeometryResult:
    hypotheses: tuple[PhotoEdgePairHypothesis, ...]
    fragment_summaries: tuple[PhotoEdgeFragmentSummary, ...]
    audit_observations: tuple[PhotoEdgeObservation, ...]
    attempted_hypothesis_count: int
    budget_exhausted: bool
    search_unavailable: bool


@dataclass(frozen=True)
class _PixelLineFeasibleRegion:
    polygons: tuple[tuple[tuple[float, float], ...], ...]

    @property
    def slope_interval(self) -> NumericInterval | None:
        slopes = tuple(
            point[0]
            for polygon in self.polygons
            for point in polygon
        )
        if not slopes:
            return None
        return NumericInterval(min(slopes), max(slopes))


def _clip_polygon(
    polygon: tuple[tuple[float, float], ...],
    a: float,
    b: float,
    maximum: float,
) -> tuple[tuple[float, float], ...]:
    if not polygon:
        return ()

    def inside(point: tuple[float, float]) -> bool:
        return a * point[0] + b * point[1] <= maximum + _POLYGON_EPSILON

    def intersection(
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> tuple[float, float]:
        start_value = a * start[0] + b * start[1] - maximum
        end_value = a * end[0] + b * end[1] - maximum
        denominator = start_value - end_value
        if abs(denominator) <= _POLYGON_EPSILON:
            return start
        fraction = start_value / denominator
        return (
            start[0] + fraction * (end[0] - start[0]),
            start[1] + fraction * (end[1] - start[1]),
        )

    output: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersection(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside
    return tuple(output)


def _pixel_line_feasible_region(
    observations: tuple[PhotoEdgeObservation, ...],
    maximum_angle_degrees: float,
    *,
    long_extent_px: int,
    short_extent_px: int,
) -> _PixelLineFeasibleRegion:
    usable = tuple(
        observation
        for observation in observations
        if not observation.censored
    )
    if not usable:
        return _PixelLineFeasibleRegion(())
    maximum_slope = math.tan(math.radians(maximum_angle_degrees))
    intercept_limit = (
        float(short_extent_px)
        + maximum_slope * float(long_extent_px)
    )
    polygons: list[tuple[tuple[float, float], ...]] = []
    for slope_minimum, slope_maximum, positive_slope in (
        (-maximum_slope, _SLOPE_SIGN_BOUNDARY, False),
        (_SLOPE_SIGN_BOUNDARY, maximum_slope, True),
    ):
        polygon = (
            (slope_minimum, -intercept_limit),
            (slope_maximum, -intercept_limit),
            (slope_maximum, intercept_limit),
            (slope_minimum, intercept_limit),
        )
        for observation in usable:
            long_minimum = observation.long_axis_footprint.minimum
            long_maximum = observation.long_axis_footprint.maximum
            short_minimum = (
                observation.short_axis_position_interval.minimum
            )
            short_maximum = (
                observation.short_axis_position_interval.maximum
            )
            lower_long = (
                long_maximum if positive_slope else long_minimum
            )
            upper_long = (
                long_minimum if positive_slope else long_maximum
            )
            polygon = _clip_polygon(
                polygon,
                -lower_long,
                -1.0,
                -short_minimum,
            )
            polygon = _clip_polygon(
                polygon,
                upper_long,
                1.0,
                short_maximum,
            )
            if not polygon:
                break
        if polygon:
            polygons.append(polygon)
    return _PixelLineFeasibleRegion(tuple(polygons))


def _clip_pixel_line_polygon_to_cell(
    polygon: tuple[tuple[float, float], ...],
    slope: NumericInterval,
    intercept: NumericInterval,
) -> tuple[tuple[float, float], ...]:
    clipped = _clip_polygon(
        polygon,
        1.0,
        0.0,
        slope.maximum,
    )
    clipped = _clip_polygon(
        clipped,
        -1.0,
        0.0,
        -slope.minimum,
    )
    clipped = _clip_polygon(
        clipped,
        0.0,
        1.0,
        intercept.maximum,
    )
    return _clip_polygon(
        clipped,
        0.0,
        -1.0,
        -intercept.minimum,
    )


def _line_region_intersects_geometry(
    region: _PixelLineFeasibleRegion,
    geometry: PhotoEdgePairGeometry,
    *,
    top: bool,
) -> bool:
    return any(
        _clip_pixel_line_polygon_to_cell(
            polygon,
            cell.pixel_slope,
            (
                cell.top_intercept_px
                if top
                else cell.bottom_intercept_px
            ),
        )
        for polygon in region.polygons
        for cell in geometry.cells
    )


def _rectangle_polygon(
    top: NumericInterval,
    bottom: NumericInterval,
) -> tuple[tuple[float, float], ...]:
    return (
        (top.minimum, bottom.minimum),
        (top.maximum, bottom.minimum),
        (top.maximum, bottom.maximum),
        (top.minimum, bottom.maximum),
    )


def _ordered_polygon(
    top: NumericInterval,
    bottom: NumericInterval,
    minimum_height: float = _POLYGON_EPSILON,
) -> tuple[tuple[float, float], ...]:
    return _clip_polygon(
        _rectangle_polygon(top, bottom),
        1.0,
        -1.0,
        -minimum_height,
    )


def _physical_polygon(
    raw: tuple[tuple[float, float], ...],
    label: PhotoEdgePhysicalLabel,
    maximum_center_offset_mm: float,
    maximum_dimension_deviation_mm: float,
) -> tuple[tuple[float, float], ...]:
    height = label.frame_size_mm.height_mm
    minimum_height = height - maximum_dimension_deviation_mm
    maximum_height = height + maximum_dimension_deviation_mm
    polygon = _clip_polygon(
        raw,
        1.0,
        -1.0,
        -minimum_height,
    )
    polygon = _clip_polygon(
        polygon,
        -1.0,
        1.0,
        maximum_height,
    )
    polygon = _clip_polygon(
        polygon,
        1.0,
        1.0,
        2.0 * maximum_center_offset_mm,
    )
    return _clip_polygon(
        polygon,
        -1.0,
        -1.0,
        2.0 * maximum_center_offset_mm,
    )


def _point_in_physical_band(
    point: tuple[float, float],
    label: PhotoEdgePhysicalLabel,
    maximum_center_offset_mm: float,
    maximum_dimension_deviation_mm: float,
) -> bool:
    top, bottom = point
    height = bottom - top
    center = 0.5 * (top + bottom)
    return bool(
        label.frame_size_mm.height_mm
        - maximum_dimension_deviation_mm
        - _POLYGON_EPSILON
        <= height
        <= label.frame_size_mm.height_mm
        + maximum_dimension_deviation_mm
        + _POLYGON_EPSILON
        and abs(center)
        <= maximum_center_offset_mm + _POLYGON_EPSILON
    )


def _projection_interval_at_theta(
    observation: PhotoEdgeObservation,
    theta: float,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval:
    long_center = 0.5 * float(long_extent_px - 1)
    short_center = 0.5 * float(short_extent_px - 1)
    corners = tuple(
        (
            (long_value - long_center) / scale.long_axis_px_per_mm,
            (short_value - short_center) / scale.short_axis_px_per_mm,
        )
        for long_value in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        )
        for short_value in (
            observation.short_axis_position_interval.minimum,
            observation.short_axis_position_interval.maximum,
        )
    )
    projections = tuple(
        -math.sin(theta) * u + math.cos(theta) * v
        for u, v in corners
    )
    return NumericInterval(min(projections), max(projections))


def _projection_interval_over_theta(
    observation: PhotoEdgeObservation,
    theta: NumericInterval,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval:
    long_center = 0.5 * float(long_extent_px - 1)
    short_center = 0.5 * float(short_extent_px - 1)
    corners = tuple(
        (
            (long_value - long_center) / scale.long_axis_px_per_mm,
            (short_value - short_center) / scale.short_axis_px_per_mm,
        )
        for long_value in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        )
        for short_value in (
            observation.short_axis_position_interval.minimum,
            observation.short_axis_position_interval.maximum,
        )
    )
    values: list[float] = []
    for u, v in corners:
        radius = math.hypot(u, v)
        phase = math.atan2(u, v)
        candidates = [theta.minimum, theta.maximum]
        if radius > 0.0:
            lower_index = math.floor(
                (theta.minimum + phase) / math.pi
            ) - 1
            upper_index = math.ceil(
                (theta.maximum + phase) / math.pi
            ) + 1
            for index in range(lower_index, upper_index + 1):
                critical = index * math.pi - phase
                if theta.minimum <= critical <= theta.maximum:
                    candidates.append(critical)
        values.extend(
            -math.sin(candidate) * u + math.cos(candidate) * v
            for candidate in candidates
        )
    return NumericInterval(min(values), max(values))


def _common_offset_interval_at_theta(
    observations: tuple[PhotoEdgeObservation, ...],
    theta: float,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval | None:
    intervals = tuple(
        _projection_interval_at_theta(
            observation,
            theta,
            scale,
            long_extent_px,
            short_extent_px,
        )
        for observation in observations
    )
    minimum = max(interval.minimum for interval in intervals)
    maximum = min(interval.maximum for interval in intervals)
    if maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _common_offset_outer_interval(
    observations: tuple[PhotoEdgeObservation, ...],
    theta: NumericInterval,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval | None:
    intervals = tuple(
        _projection_interval_over_theta(
            observation,
            theta,
            scale,
            long_extent_px,
            short_extent_px,
        )
        for observation in observations
    )
    minimum = max(interval.minimum for interval in intervals)
    maximum = min(interval.maximum for interval in intervals)
    if maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _containment_offset_interval(
    observations: tuple[PhotoEdgeObservation, ...],
    theta: float,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval:
    long_center = 0.5 * float(long_extent_px - 1)
    short_half_mm = (
        0.5 * float(short_extent_px - 1)
        / scale.short_axis_px_per_mm
    )
    long_values = tuple(
        (coordinate - long_center) / scale.long_axis_px_per_mm
        for observation in observations
        for coordinate in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        )
    )
    lower = max(
        -math.sin(theta) * u - math.cos(theta) * short_half_mm
        for u in long_values
    )
    upper = min(
        -math.sin(theta) * u + math.cos(theta) * short_half_mm
        for u in long_values
    )
    return NumericInterval(lower, upper)


def _linear_trig_interval(
    sin_coefficient: float,
    cos_coefficient: float,
    theta: NumericInterval,
) -> NumericInterval:
    values = [
        (
            sin_coefficient * math.sin(candidate)
            + cos_coefficient * math.cos(candidate)
        )
        for candidate in (theta.minimum, theta.maximum)
    ]
    phase = math.atan2(
        sin_coefficient,
        cos_coefficient,
    )
    first = math.floor((theta.minimum - phase) / math.pi) - 1
    last = math.ceil((theta.maximum - phase) / math.pi) + 1
    for index in range(first, last + 1):
        critical = phase + index * math.pi
        if theta.minimum <= critical <= theta.maximum:
            values.append(
                sin_coefficient * math.sin(critical)
                + cos_coefficient * math.cos(critical)
            )
    return NumericInterval(min(values), max(values))


def _containment_offset_outer_interval(
    observations: tuple[PhotoEdgeObservation, ...],
    theta: NumericInterval,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> NumericInterval | None:
    long_center = 0.5 * float(long_extent_px - 1)
    short_half_mm = (
        0.5 * float(short_extent_px - 1)
        / scale.short_axis_px_per_mm
    )
    long_values = tuple(
        (coordinate - long_center) / scale.long_axis_px_per_mm
        for observation in observations
        for coordinate in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        )
    )
    lower_bound = max(
        _linear_trig_interval(
            -u,
            -short_half_mm,
            theta,
        ).minimum
        for u in long_values
    )
    upper_bound = min(
        _linear_trig_interval(
            -u,
            short_half_mm,
            theta,
        ).maximum
        for u in long_values
    )
    if upper_bound < lower_bound:
        return None
    return NumericInterval(lower_bound, upper_bound)


def _intersect_numeric(
    left: NumericInterval,
    right: NumericInterval,
) -> NumericInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    if maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _label_order(
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
) -> tuple[PhotoEdgePhysicalLabel, ...]:
    labels = {
        corridor.physical_label.identity: corridor.physical_label
        for corridor in corridors
    }
    return tuple(labels[identity] for identity in sorted(labels))


def _theta_interval_for_pixel_search(
    maximum_pixel_angle_degrees: float,
    scale: CanvasPixelScale,
) -> NumericInterval:
    pixel_slope = math.tan(math.radians(maximum_pixel_angle_degrees))
    physical_slope = (
        pixel_slope
        * scale.long_axis_px_per_mm
        / scale.short_axis_px_per_mm
    )
    physical_angle = math.atan(physical_slope)
    return NumericInterval(-physical_angle, physical_angle)


def _cell_theta_resolution(
    parameters: PhotoEdgeDetectionParameters,
    scale: CanvasPixelScale,
    long_extent_px: int,
) -> float:
    pixel_span = max(1.0, float(long_extent_px - 1))
    pixel_angle = math.atan(
        parameters.geometry.subpixel_resolution_px / pixel_span
    )
    physical_slope = (
        math.tan(pixel_angle)
        * scale.long_axis_px_per_mm
        / scale.short_axis_px_per_mm
    )
    return max(math.atan(physical_slope), _POLYGON_EPSILON)


def _active_constraints(
    observations: tuple[PhotoEdgeObservation, ...],
    theta: float,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> tuple[ObservationId, ...]:
    intervals = tuple(
        (
            observation,
            _projection_interval_at_theta(
                observation,
                theta,
                scale,
                long_extent_px,
                short_extent_px,
            ),
        )
        for observation in observations
    )
    lower = max(interval.minimum for _, interval in intervals)
    upper = min(interval.maximum for _, interval in intervals)
    tolerance = _ACTIVE_CONSTRAINT_TOLERANCE
    lower_ids = tuple(
        observation.observation_id
        for observation, interval in intervals
        if abs(interval.minimum - lower) <= tolerance
    )
    upper_ids = tuple(
        observation.observation_id
        for observation, interval in intervals
        if abs(interval.maximum - upper) <= tolerance
    )
    return tuple(
        dict.fromkeys(
            (
                min(lower_ids, key=str),
                min(upper_ids, key=str),
            )
        )
    )


def _witness_for_label_at_theta(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    theta: float,
    label: PhotoEdgePhysicalLabel,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
    parameters: PhotoEdgeDetectionParameters,
) -> NormalRegionWitness | None:
    top = _common_offset_interval_at_theta(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom = _common_offset_interval_at_theta(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    if top is None or bottom is None:
        return None
    top_containment = _containment_offset_interval(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom_containment = _containment_offset_interval(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    top = _intersect_numeric(top, top_containment)
    bottom = _intersect_numeric(bottom, bottom_containment)
    if top is None or bottom is None:
        return None
    polygon = _physical_polygon(
        _ordered_polygon(top, bottom),
        label,
        parameters.maximum_center_offset_mm,
        parameters.maximum_photo_dimension_deviation_mm,
    )
    if not polygon:
        return None
    top_value = sum(point[0] for point in polygon) / float(len(polygon))
    bottom_value = sum(point[1] for point in polygon) / float(len(polygon))
    witness = NormalRegionWitness(
        physical_angle_radians=theta,
        top_normal_offset_mm=top_value,
        bottom_normal_offset_mm=bottom_value,
        physical_label=label,
    )
    for observation in top_observations:
        if not (
            _projection_interval_at_theta(
                observation,
                theta,
                scale,
                long_extent_px,
                short_extent_px,
            ).minimum
            - _POLYGON_EPSILON
            <= top_value
            <= _projection_interval_at_theta(
                observation,
                theta,
                scale,
                long_extent_px,
                short_extent_px,
            ).maximum
            + _POLYGON_EPSILON
        ):
            return None
    for observation in bottom_observations:
        interval = _projection_interval_at_theta(
            observation,
            theta,
            scale,
            long_extent_px,
            short_extent_px,
        )
        if not (
            interval.minimum - _POLYGON_EPSILON
            <= bottom_value
            <= interval.maximum + _POLYGON_EPSILON
        ):
            return None
    if not _point_in_physical_band(
        (top_value, bottom_value),
        label,
        parameters.maximum_center_offset_mm,
        parameters.maximum_photo_dimension_deviation_mm,
    ):
        return None
    return witness


def _normal_cell_signature(
    theta_path: str,
    theta: NumericInterval,
    top: NumericInterval,
    bottom: NumericInterval,
    labels: tuple[PhotoEdgePhysicalLabel, ...],
    active: tuple[ObservationId, ...],
    offset_resolution_mm: float,
) -> str:
    def grid(value: float, *, upper: bool) -> int:
        scaled = value / offset_resolution_mm
        return math.ceil(scaled) if upper else math.floor(scaled)

    payload = (
        theta_path,
        f"{theta.minimum:.16g}",
        f"{theta.maximum:.16g}",
        str(grid(top.minimum, upper=False)),
        str(grid(top.maximum, upper=True)),
        str(grid(bottom.minimum, upper=False)),
        str(grid(bottom.maximum, upper=True)),
        ",".join(label.identity for label in labels),
        ",".join(str(identity) for identity in active),
    )
    return sha256("|".join(payload).encode("utf-8")).hexdigest()


def _raw_subset_labels(
    raw: tuple[tuple[float, float], ...],
    labels: tuple[PhotoEdgePhysicalLabel, ...],
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[PhotoEdgePhysicalLabel, ...]:
    return tuple(
        label
        for label in labels
        if raw
        and all(
            _point_in_physical_band(
                point,
                label,
                parameters.maximum_center_offset_mm,
                parameters.maximum_photo_dimension_deviation_mm,
            )
            for point in raw
        )
    )


def _build_normal_cell(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    theta_path: str,
    theta: NumericInterval,
    labels: tuple[PhotoEdgePhysicalLabel, ...],
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
    parameters: PhotoEdgeDetectionParameters,
) -> tuple[
    NormalRegionCell | None,
    RegionSetRelation,
    bool,
    bool,
    bool,
]:
    top_outer = _common_offset_outer_interval(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom_outer = _common_offset_outer_interval(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    if top_outer is None or bottom_outer is None:
        return None, RegionSetRelation.DISJOINT, False, False, False
    raw = _ordered_polygon(top_outer, bottom_outer)
    if not raw:
        return None, RegionSetRelation.DISJOINT, False, False, False
    top_containment = _containment_offset_outer_interval(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom_containment = _containment_offset_outer_interval(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    if top_containment is None or bottom_containment is None:
        return None, RegionSetRelation.DISJOINT, False, True, False
    top_outer = _intersect_numeric(top_outer, top_containment)
    bottom_outer = _intersect_numeric(bottom_outer, bottom_containment)
    if top_outer is None or bottom_outer is None:
        return None, RegionSetRelation.DISJOINT, False, True, False
    raw = _ordered_polygon(top_outer, bottom_outer)
    if not raw:
        return None, RegionSetRelation.DISJOINT, False, True, False
    possible_labels = tuple(
        label
        for label in labels
        if _physical_polygon(
            raw,
            label,
            parameters.maximum_center_offset_mm,
            parameters.maximum_photo_dimension_deviation_mm,
        )
    )
    if not possible_labels:
        return None, RegionSetRelation.DISJOINT, False, True, True
    theta_values = tuple(
        dict.fromkeys(
            (
                theta.midpoint,
                theta.minimum,
                theta.maximum,
            )
        )
    )
    witness_grid = {
        (label.identity, candidate_theta): (
            _witness_for_label_at_theta(
                top_observations,
                bottom_observations,
                candidate_theta,
                label,
                scale,
                long_extent_px,
                short_extent_px,
                parameters,
            )
        )
        for label in possible_labels
        for candidate_theta in theta_values
    }
    witnesses = tuple(
        witness
        for label in possible_labels
        for witness in (
            next(
                (
                    witness_grid[(label.identity, candidate_theta)]
                    for candidate_theta in theta_values
                    if witness_grid[(label.identity, candidate_theta)]
                    is not None
                ),
                None,
            ),
        )
        if witness is not None
    )
    if not witnesses:
        return (
            None,
            RegionSetRelation.NUMERICALLY_INDETERMINATE,
            True,
            True,
            True,
        )
    subset_labels = _raw_subset_labels(raw, labels, parameters)
    if len(subset_labels) == 1 and possible_labels == subset_labels:
        relation = RegionSetRelation.SUBSET
    else:
        relation = RegionSetRelation.PARTIAL_INTERSECTION
    active = tuple(
        dict.fromkeys(
            (
                *_active_constraints(
                    top_observations,
                    theta.midpoint,
                    scale,
                    long_extent_px,
                    short_extent_px,
                ),
                *_active_constraints(
                    bottom_observations,
                    theta.midpoint,
                    scale,
                    long_extent_px,
                    short_extent_px,
                ),
            )
        )
    )
    offset_resolution_mm = (
        parameters.geometry.subpixel_resolution_px
        / scale.short_axis_px_per_mm
    )
    signature = _normal_cell_signature(
        theta_path,
        theta,
        top_outer,
        bottom_outer,
        possible_labels,
        active,
        offset_resolution_mm,
    )
    sampled_feasibility = tuple(
        any(
            witness_grid[(label.identity, candidate_theta)] is not None
            for label in possible_labels
        )
        for candidate_theta in theta_values
    )
    needs_subdivision = (
        relation != RegionSetRelation.SUBSET
        or not all(sampled_feasibility)
    )
    return (
        NormalRegionCell(
            theta_binary_path=theta_path,
            physical_angle_radians=theta,
            top_normal_offset_mm=top_outer,
            bottom_normal_offset_mm=bottom_outer,
            possible_physical_labels=possible_labels,
            verified_witnesses=witnesses,
            active_constraint_ids=active,
            canonical_signature=signature,
        ),
        relation,
        needs_subdivision,
        True,
        True,
    )


def _normal_to_line_cell(
    cell: NormalRegionCell,
    scale: CanvasPixelScale,
    long_extent_px: int,
    short_extent_px: int,
) -> PhotoEdgeLineRegionCell:
    long_center = 0.5 * float(long_extent_px - 1)
    short_center = 0.5 * float(short_extent_px - 1)

    def line(theta: float, normal_offset: float) -> tuple[float, float]:
        cosine = math.cos(theta)
        if abs(cosine) < AFFINE_INVERTIBILITY_FLOOR:
            raise ValueError("photo edge is not a short-axis function")
        slope = (
            scale.short_axis_px_per_mm
            / scale.long_axis_px_per_mm
            * math.tan(theta)
        )
        intercept = (
            short_center
            + scale.short_axis_px_per_mm * normal_offset / cosine
            - slope * long_center
        )
        return slope, intercept

    top_lines = tuple(
        line(theta, offset)
        for theta in (
            cell.physical_angle_radians.minimum,
            cell.physical_angle_radians.maximum,
        )
        for offset in (
            cell.top_normal_offset_mm.minimum,
            cell.top_normal_offset_mm.maximum,
        )
    )
    bottom_lines = tuple(
        line(theta, offset)
        for theta in (
            cell.physical_angle_radians.minimum,
            cell.physical_angle_radians.maximum,
        )
        for offset in (
            cell.bottom_normal_offset_mm.minimum,
            cell.bottom_normal_offset_mm.maximum,
        )
    )
    slopes = tuple(value[0] for value in (*top_lines, *bottom_lines))
    witnesses = tuple(
        PhotoEdgeLineWitness(
            pixel_slope=line(
                witness.physical_angle_radians,
                witness.top_normal_offset_mm,
            )[0],
            top_intercept_px=line(
                witness.physical_angle_radians,
                witness.top_normal_offset_mm,
            )[1],
            bottom_intercept_px=line(
                witness.physical_angle_radians,
                witness.bottom_normal_offset_mm,
            )[1],
            top_intercept_feasible_px=NumericInterval.exact(
                line(
                    witness.physical_angle_radians,
                    witness.top_normal_offset_mm,
                )[1]
            ),
            bottom_intercept_feasible_px=NumericInterval.exact(
                line(
                    witness.physical_angle_radians,
                    witness.bottom_normal_offset_mm,
                )[1]
            ),
            physical_label=witness.physical_label,
        )
        for witness in cell.verified_witnesses
    )
    return PhotoEdgeLineRegionCell(
        source_cell_signature=cell.canonical_signature,
        pixel_slope=NumericInterval(min(slopes), max(slopes)),
        top_intercept_px=NumericInterval(
            min(value[1] for value in top_lines),
            max(value[1] for value in top_lines),
        ),
        bottom_intercept_px=NumericInterval(
            min(value[1] for value in bottom_lines),
            max(value[1] for value in bottom_lines),
        ),
        possible_physical_labels=cell.possible_physical_labels,
        verified_witnesses=witnesses,
        active_constraint_ids=cell.active_constraint_ids,
    )


def solve_normal_region(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    scale: CanvasPixelScale,
    parameters: PhotoEdgeDetectionParameters,
    budget: GeometryWorkBudget,
    *,
    long_extent_px: int,
    short_extent_px: int,
) -> tuple[PhotoEdgePairGeometry | None, EvidenceState, tuple[PhotoEdgeFact, ...]]:
    labels = _label_order(corridors)
    initial_theta = _theta_interval_for_pixel_search(
        parameters.maximum_search_angle_degrees,
        scale,
    )
    theta_resolution = _cell_theta_resolution(
        parameters,
        scale,
        long_extent_px,
    )
    pending: list[tuple[str, NumericInterval, int]] = [
        ("", initial_theta, 0)
    ]
    retained: list[NormalRegionCell] = []
    relations: list[RegionSetRelation] = []
    indeterminate = False
    observation_geometry_possible = False
    contained_geometry_possible = False
    while pending:
        theta_path, theta, depth = pending.pop(0)
        if not budget.consume_region_cell():
            indeterminate = True
            break
        (
            cell,
            relation,
            needs_subdivision,
            observation_cell_possible,
            contained_cell_possible,
        ) = _build_normal_cell(
            top_observations,
            bottom_observations,
            theta_path,
            theta,
            labels,
            scale,
            long_extent_px,
            short_extent_px,
            parameters,
        )
        observation_geometry_possible = (
            observation_geometry_possible
            or observation_cell_possible
        )
        contained_geometry_possible = (
            contained_geometry_possible
            or contained_cell_possible
        )
        if relation == RegionSetRelation.DISJOINT:
            continue
        if (
            needs_subdivision
            and depth < parameters.geometry.maximum_subdivision_depth
            and theta.width > theta_resolution
        ):
            midpoint = theta.midpoint
            pending.extend(
                (
                    (
                        f"{theta_path}0",
                        NumericInterval(theta.minimum, midpoint),
                        depth + 1,
                    ),
                    (
                        f"{theta_path}1",
                        NumericInterval(midpoint, theta.maximum),
                        depth + 1,
                    ),
                )
            )
            continue
        if cell is None:
            indeterminate = True
            relations.append(RegionSetRelation.NUMERICALLY_INDETERMINATE)
            continue
        retained.append(cell)
        relations.append(relation)
    unique_cells = {
        cell.canonical_signature: cell for cell in retained
    }
    cells = tuple(unique_cells[key] for key in sorted(unique_cells))
    if not cells and not indeterminate:
        if not observation_geometry_possible:
            state = EvidenceState.UNAVAILABLE
            fact = PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE
        elif not contained_geometry_possible:
            state = EvidenceState.CONTRADICTED
            fact = PhotoEdgeFact.CONTAINMENT_CONTRADICTED
        else:
            state = EvidenceState.CONTRADICTED
            fact = PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED
        return (
            None,
            state,
            (fact,),
        )
    if indeterminate or any(
        relation == RegionSetRelation.NUMERICALLY_INDETERMINATE
        for relation in relations
    ):
        relation = RegionSetRelation.NUMERICALLY_INDETERMINATE
        state = EvidenceState.UNAVAILABLE
        facts = (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,)
    elif all(
        relation == RegionSetRelation.SUBSET for relation in relations
    ):
        all_labels = {
            label.identity: label
            for cell in cells
            for label in cell.possible_physical_labels
        }
        if len(all_labels) == 1:
            relation = RegionSetRelation.SUBSET
            state = EvidenceState.SUPPORTED
            facts = ()
        else:
            relation = RegionSetRelation.PARTIAL_INTERSECTION
            state = EvidenceState.UNAVAILABLE
            facts = (PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED,)
    else:
        all_labels = {
            label.identity
            for cell in cells
            for label in cell.possible_physical_labels
        }
        relation = RegionSetRelation.PARTIAL_INTERSECTION
        state = EvidenceState.UNAVAILABLE
        facts = (
            (
                PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED
                if len(all_labels) > 1
                else PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE
            ),
        )
    if not cells:
        return None, EvidenceState.UNAVAILABLE, (
            PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,
        )
    normal_region = PhotoEdgeNormalFeasibleRegion(
        cells=cells,
        set_relation=relation,
        numerically_indeterminate=indeterminate,
        consumed_region_cells=budget.consumed_region_cells,
        consumed_consensus_states=budget.consumed_consensus_states,
    )
    geometry = PhotoEdgePairGeometry(
        cells=tuple(
            _normal_to_line_cell(
                cell,
                scale,
                long_extent_px,
                short_extent_px,
            )
            for cell in cells
        ),
        normal_region=normal_region,
        work_long_axis_extent_px=long_extent_px,
        work_short_axis_extent_px=short_extent_px,
        interpolation_position_uncertainty_px=0.0,
        coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
        numerically_indeterminate=indeterminate,
    )
    return geometry, state, facts


def _fragment_role_eligible(
    fragment: PhotoEdgeFragment,
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    *,
    top: bool,
) -> bool:
    observations = tuple(
        observation
        for observation in fragment.observations
        if not observation.censored
    )
    if not observations:
        return False
    return any(
        all(
            corridor.side_interval_at(
                observation.long_axis_footprint.midpoint,
                top=top,
            ).intersects(observation.short_axis_position_interval)
            for observation in observations
        )
        for corridor in corridors
    )


def _minimal_support_groups(
    fragments: tuple[PhotoEdgeFragment, ...],
    minimum_observations: int,
    line_regions: dict[ObservationId, _PixelLineFeasibleRegion],
    parameters: PhotoEdgeDetectionParameters,
    *,
    long_extent_px: int,
    short_extent_px: int,
) -> tuple[tuple[tuple[ObservationId, ...], ...], bool]:
    fragment_map = {
        fragment.fragment_id: fragment for fragment in fragments
    }

    def ordered_groups(
        values: list[tuple[ObservationId, ...]],
    ) -> tuple[tuple[ObservationId, ...], ...]:
        region_cache: dict[
            tuple[ObservationId, ...],
            _PixelLineFeasibleRegion,
        ] = {}

        def key(
            fragment_ids: tuple[ObservationId, ...],
        ) -> tuple[float, float, float, tuple[str, ...]]:
            selected = tuple(
                fragment_map[fragment_id]
                for fragment_id in fragment_ids
            )
            region = region_cache.get(fragment_ids)
            if region is None:
                if len(fragment_ids) == 1:
                    region = line_regions[fragment_ids[0]]
                else:
                    region = _pixel_line_feasible_region(
                        tuple(
                            observation
                            for fragment in selected
                            for observation in fragment.observations
                            if not observation.censored
                        ),
                        parameters.maximum_search_angle_degrees,
                        long_extent_px=long_extent_px,
                        short_extent_px=short_extent_px,
                    )
                region_cache[fragment_ids] = region
            slope = region.slope_interval
            return (
                0.5
                * (
                    min(
                        fragment.short_axis_position_interval.minimum
                        for fragment in selected
                    )
                    + max(
                        fragment.short_axis_position_interval.maximum
                        for fragment in selected
                    )
                ),
                0.0 if slope is None else slope.midpoint,
                0.5
                * (
                    min(
                        fragment.long_axis_footprint.minimum
                        for fragment in selected
                    )
                    + max(
                        fragment.long_axis_footprint.maximum
                        for fragment in selected
                    )
                ),
                tuple(str(identity) for identity in fragment_ids),
            )

        sorted_values = tuple(sorted(values, key=key))
        intervals = deque([(0, len(sorted_values))])
        balanced: list[tuple[ObservationId, ...]] = []
        while intervals:
            start, end = intervals.popleft()
            if start >= end:
                continue
            midpoint = (start + end) // 2
            balanced.append(sorted_values[midpoint])
            intervals.append((start, midpoint))
            intervals.append((midpoint + 1, end))
        return tuple(balanced)

    ordered = tuple(
        sorted(
            (
                fragment
                for fragment in fragments
                if line_regions[fragment.fragment_id].polygons
            ),
            key=lambda fragment: (
                -(
                    fragment.long_axis_footprint.maximum
                    - fragment.long_axis_footprint.minimum
                ),
                fragment.short_axis_position_interval.midpoint,
                fragment.long_axis_footprint.minimum,
                str(fragment.fragment_id),
            ),
        )
    )
    groups: list[tuple[ObservationId, ...]] = []
    under_supported: list[PhotoEdgeFragment] = []
    for fragment in ordered:
        observations = tuple(
            observation
            for observation in fragment.observations
            if not observation.censored
        )
        if len(
            _minimum_support_witnesses(
                observations,
                minimum_observations,
            )
        ) >= minimum_observations:
            groups.append((fragment.fragment_id,))
        else:
            under_supported.append(fragment)
    limit = parameters.geometry.maximum_consensus_states
    if len(groups) >= limit:
        balanced = ordered_groups(groups)
        return balanced[:limit], len(groups) > limit
    inspected = 0
    incomplete = False
    maximum_group_size = min(
        minimum_observations,
        len(under_supported),
    )
    for size in range(
        _MULTI_FRAGMENT_GROUP_MINIMUM_SIZE,
        maximum_group_size + 1,
    ):
        for selected in combinations(under_supported, size):
            if inspected >= limit or len(groups) >= limit:
                incomplete = True
                break
            inspected += 1
            observations = tuple(
                observation
                for fragment in selected
                for observation in fragment.observations
                if not observation.censored
            )
            if len(
                _minimum_support_witnesses(
                    observations,
                    minimum_observations,
                )
            ) < minimum_observations:
                continue
            if any(
                len(
                    _minimum_support_witnesses(
                        tuple(
                            observation
                            for other in selected
                            if other is not fragment
                            for observation in other.observations
                            if not observation.censored
                        ),
                        minimum_observations,
                    )
                )
                >= minimum_observations
                for fragment in selected
            ):
                continue
            if not _pixel_line_feasible_region(
                observations,
                parameters.maximum_search_angle_degrees,
                long_extent_px=long_extent_px,
                short_extent_px=short_extent_px,
            ).polygons:
                continue
            groups.append(
                tuple(
                    sorted(
                        (
                            fragment.fragment_id
                            for fragment in selected
                        ),
                        key=str,
                    )
                )
            )
        if incomplete:
            break
    return ordered_groups(groups), incomplete


def _diagonal_seed_pairs(
    top_groups: tuple[tuple[ObservationId, ...], ...],
    bottom_groups: tuple[tuple[ObservationId, ...], ...],
    *,
    maximum_inspections: int,
    maximum_seeds: int,
    pair_is_possible: Callable[
        [tuple[ObservationId, ...], tuple[ObservationId, ...]],
        bool,
    ],
) -> tuple[
    tuple[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        ...,
    ],
    bool,
]:
    if not top_groups or not bottom_groups:
        return (), False
    seeds: list[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
    ] = []
    inspected = 0
    incomplete = False
    diagonal_count = len(top_groups) + len(bottom_groups) - 1
    for diagonal in range(max(0, diagonal_count)):
        top_start = max(0, diagonal - len(bottom_groups) + 1)
        top_end = min(len(top_groups), diagonal + 1)
        for top_index in range(top_start, top_end):
            if (
                inspected >= maximum_inspections
                or len(seeds) >= maximum_seeds
            ):
                incomplete = True
                break
            bottom_index = diagonal - top_index
            top_ids = top_groups[top_index]
            bottom_ids = bottom_groups[bottom_index]
            inspected += 1
            if (
                set(top_ids) & set(bottom_ids)
                or not pair_is_possible(top_ids, bottom_ids)
            ):
                continue
            seeds.append((top_ids, bottom_ids))
        if incomplete:
            break
    return tuple(seeds), incomplete


@dataclass
class _NearestCoordinateCursor:
    fixed_index: int
    left_index: int
    right_index: int


def _nearest_coordinate_index(
    cursor: _NearestCoordinateCursor,
    coordinates: tuple[float, ...],
    target: float,
) -> int | None:
    left = cursor.left_index
    right = cursor.right_index
    if left < 0 and right >= len(coordinates):
        return None
    if left < 0:
        cursor.right_index += 1
        return right
    if right >= len(coordinates):
        cursor.left_index -= 1
        return left
    left_distance = abs(coordinates[left] - target)
    right_distance = abs(coordinates[right] - target)
    if left_distance <= right_distance:
        cursor.left_index -= 1
        return left
    cursor.right_index += 1
    return right


def _coordinate_seed_pairs(
    top_groups: tuple[tuple[ObservationId, ...], ...],
    bottom_groups: tuple[tuple[ObservationId, ...], ...],
    *,
    maximum_inspections: int,
    maximum_seeds: int,
    pair_is_possible: Callable[
        [tuple[ObservationId, ...], tuple[ObservationId, ...]],
        bool,
    ],
    top_discovery_coordinate: Callable[
        [tuple[ObservationId, ...]], float
    ],
    bottom_discovery_coordinate: Callable[
        [tuple[ObservationId, ...]], float
    ],
    top_group_order_key: Callable[
        [tuple[ObservationId, ...]], tuple[object, ...]
    ]
    | None,
    bottom_group_order_key: Callable[
        [tuple[ObservationId, ...]], tuple[object, ...]
    ]
    | None,
    paired_coordinate_sum: float,
    seed_order_key: Callable[
        [
            tuple[ObservationId, ...],
            tuple[ObservationId, ...],
        ],
        tuple[object, ...],
    ]
    | None,
) -> tuple[
    tuple[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        ...,
    ],
    bool,
]:
    ordered_top = tuple(
        sorted(
            top_groups,
            key=lambda group: (
                top_discovery_coordinate(group),
                tuple(str(identity) for identity in group),
            ),
        )
    )
    ordered_bottom = tuple(
        sorted(
            bottom_groups,
            key=lambda group: (
                bottom_discovery_coordinate(group),
                tuple(str(identity) for identity in group),
            ),
        )
    )
    top_coordinates = tuple(
        top_discovery_coordinate(group) for group in ordered_top
    )
    bottom_coordinates = tuple(
        bottom_discovery_coordinate(group) for group in ordered_bottom
    )

    def make_cursor(
        fixed_index: int,
        coordinates: tuple[float, ...],
        target: float,
    ) -> _NearestCoordinateCursor:
        insertion = bisect_left(coordinates, target)
        return _NearestCoordinateCursor(
            fixed_index=fixed_index,
            left_index=insertion - 1,
            right_index=insertion,
        )

    tasks: list[
        tuple[
            tuple[object, ...],
            bool,
            _NearestCoordinateCursor,
        ]
    ] = []
    for index, group in enumerate(ordered_top):
        tasks.append(
            (
                (
                    ()
                    if top_group_order_key is None
                    else top_group_order_key(group)
                ),
                True,
                make_cursor(
                    index,
                    bottom_coordinates,
                    paired_coordinate_sum
                    - top_discovery_coordinate(group),
                ),
            )
        )
    for index, group in enumerate(ordered_bottom):
        tasks.append(
            (
                (
                    ()
                    if bottom_group_order_key is None
                    else bottom_group_order_key(group)
                ),
                False,
                make_cursor(
                    index,
                    top_coordinates,
                    paired_coordinate_sum
                    - bottom_discovery_coordinate(group),
                ),
            )
        )
    tasks.sort(
        key=lambda task: (
            task[0],
            not task[1],
            task[2].fixed_index,
        )
    )

    seeds: dict[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        None,
    ] = {}
    inspected = 0
    depth = 0
    while (
        tasks
        and inspected < maximum_inspections
        and len(seeds) < maximum_seeds
    ):
        advanced = False
        for _, top_fixed, current in tasks[
            : min(depth + 1, len(tasks))
        ]:
            if (
                inspected >= maximum_inspections
                or len(seeds) >= maximum_seeds
            ):
                break
            coordinates = (
                bottom_coordinates if top_fixed else top_coordinates
            )
            fixed_group = (
                ordered_top[current.fixed_index]
                if top_fixed
                else ordered_bottom[current.fixed_index]
            )
            target = paired_coordinate_sum - (
                top_discovery_coordinate(fixed_group)
                if top_fixed
                else bottom_discovery_coordinate(fixed_group)
            )
            counterpart_index = _nearest_coordinate_index(
                current,
                coordinates,
                target,
            )
            if counterpart_index is None:
                continue
            advanced = True
            if top_fixed:
                top_ids = fixed_group
                bottom_ids = ordered_bottom[counterpart_index]
            else:
                top_ids = ordered_top[counterpart_index]
                bottom_ids = fixed_group
            inspected += 1
            if (
                not set(top_ids) & set(bottom_ids)
                and pair_is_possible(top_ids, bottom_ids)
            ):
                seeds[(top_ids, bottom_ids)] = None
        if not advanced and depth + 1 >= len(tasks):
            break
        depth += 1
    ordered_seeds = tuple(seeds)
    if seed_order_key is not None:
        ordered_seeds = tuple(
            sorted(
                ordered_seeds,
                key=lambda seed: seed_order_key(seed[0], seed[1]),
            )
        )
    exhaustive = bool(
        all(
            cursor.left_index < 0
            and cursor.right_index
            >= (
                len(bottom_coordinates)
                if top_fixed
                else len(top_coordinates)
            )
            for _, top_fixed, cursor in tasks
        )
    )
    return ordered_seeds, not exhaustive


def _observations_for_fragments(
    fragment_ids: tuple[ObservationId, ...],
    fragments: dict[ObservationId, PhotoEdgeFragment],
) -> tuple[PhotoEdgeObservation, ...]:
    return tuple(
        observation
        for fragment_id in fragment_ids
        for observation in fragments[fragment_id].observations
        if not observation.censored
    )


def _regions_share_slope(
    top: _PixelLineFeasibleRegion,
    bottom: _PixelLineFeasibleRegion,
) -> bool:
    top_slope = top.slope_interval
    bottom_slope = bottom.slope_interval
    return bool(
        top_slope is not None
        and bottom_slope is not None
        and _intersect_numeric(top_slope, bottom_slope) is not None
    )


def _fixed_pair_outer_admissible(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    scale: CanvasPixelScale,
    parameters: PhotoEdgeDetectionParameters,
    *,
    long_extent_px: int,
    short_extent_px: int,
) -> bool:
    theta = _theta_interval_for_pixel_search(
        parameters.maximum_search_angle_degrees,
        scale,
    )
    top_outer = _common_offset_outer_interval(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom_outer = _common_offset_outer_interval(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    if top_outer is None or bottom_outer is None:
        return False
    top_containment = _containment_offset_outer_interval(
        top_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    bottom_containment = _containment_offset_outer_interval(
        bottom_observations,
        theta,
        scale,
        long_extent_px,
        short_extent_px,
    )
    if top_containment is None or bottom_containment is None:
        return False
    top_outer = _intersect_numeric(top_outer, top_containment)
    bottom_outer = _intersect_numeric(
        bottom_outer,
        bottom_containment,
    )
    if top_outer is None or bottom_outer is None:
        return False
    raw = _ordered_polygon(top_outer, bottom_outer)
    if not raw:
        return False
    return any(
        _physical_polygon(
            raw,
            label,
            parameters.maximum_center_offset_mm,
            parameters.maximum_photo_dimension_deviation_mm,
        )
        for label in _label_order(corridors)
    )


def _minimum_support_witnesses(
    observations: tuple[PhotoEdgeObservation, ...],
    minimum_observations: int,
) -> tuple[PhotoEdgeObservation, ...]:
    witnesses: list[PhotoEdgeObservation] = []
    for observation in sorted(
        observations,
        key=lambda item: (
            item.long_axis_footprint.maximum,
            item.long_axis_footprint.minimum,
            str(item.observation_id),
        ),
    ):
        if (
            witnesses
            and observation.long_axis_footprint.minimum
            < witnesses[-1].long_axis_footprint.maximum
        ):
            continue
        witnesses.append(observation)
        if len(witnesses) == minimum_observations:
            break
    return tuple(witnesses)


def _hypothesis_id(
    prefix: str,
    top_ids: tuple[ObservationId, ...],
    bottom_ids: tuple[ObservationId, ...],
    region_signature: str,
) -> ObservationId:
    digest = sha256(
        (
            "|".join(str(identity) for identity in top_ids)
            + "||"
            + "|".join(str(identity) for identity in bottom_ids)
            + "||"
            + region_signature
        ).encode("utf-8")
    ).hexdigest()[:20]
    return ObservationId(f"{prefix}:pair:{digest}")


def _solve_hypothesis(
    prefix: str,
    top_ids: tuple[ObservationId, ...],
    bottom_ids: tuple[ObservationId, ...],
    fragment_map: dict[ObservationId, PhotoEdgeFragment],
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    scale: CanvasPixelScale,
    parameters: PhotoEdgeDetectionParameters,
    budget: GeometryWorkBudget,
    long_extent_px: int,
    short_extent_px: int,
) -> PhotoEdgePairHypothesis:
    top_observations = _observations_for_fragments(top_ids, fragment_map)
    bottom_observations = _observations_for_fragments(
        bottom_ids,
        fragment_map,
    )
    geometry, state, facts = solve_normal_region(
        top_observations,
        bottom_observations,
        corridors,
        scale,
        parameters,
        budget,
        long_extent_px=long_extent_px,
        short_extent_px=short_extent_px,
    )
    physical_labels = tuple(
        {
            label.identity: label
            for cell in (() if geometry is None else geometry.cells)
            for label in cell.possible_physical_labels
        }[identity]
        for identity in sorted(
            {
                label.identity
                for cell in (() if geometry is None else geometry.cells)
                for label in cell.possible_physical_labels
            }
        )
    )
    region_signature = (
        "disjoint"
        if geometry is None or geometry.normal_region is None
        else geometry.normal_region.canonical_signature
    )
    observation_id = _hypothesis_id(
        prefix,
        top_ids,
        bottom_ids,
        region_signature,
    )
    return PhotoEdgePairHypothesis(
        observation_id=observation_id,
        top_fragment_ids=top_ids,
        bottom_fragment_ids=bottom_ids,
        geometry=geometry,
        physical_labels=physical_labels,
        state=state,
        facts=facts,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.SCAN_CANVAS_GEOMETRY,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ),
            description="maximal admissible photo-edge pair hypothesis",
            boundary_anchors=tuple(
                (
                    *top_ids,
                    *bottom_ids,
                )
            ),
        ),
    )


def _pixel_line_supports_fragment(
    fragment: PhotoEdgeFragment,
    slope: float,
    intercept: float,
) -> bool:
    observations = tuple(
        observation
        for observation in fragment.observations
        if not observation.censored
    )
    return bool(
        observations
        and all(
            (
                interval := _pixel_intercept_interval_at_slope(
                    observation,
                    slope,
                )
            ).minimum
            - _POLYGON_EPSILON
            <= intercept
            <= interval.maximum + _POLYGON_EPSILON
            for observation in observations
        )
    )


def _witness_saturated_states(
    hypothesis: PhotoEdgePairHypothesis,
    ordered_fragments: tuple[PhotoEdgeFragment, ...],
    top_eligible: frozenset[ObservationId],
    bottom_eligible: frozenset[ObservationId],
) -> tuple[
    tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
    ...,
]:
    if hypothesis.geometry is None:
        return ()
    states: dict[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        None,
    ] = {}
    witnesses = tuple(
        witness
        for cell in hypothesis.geometry.cells
        for witness in cell.verified_witnesses
    )
    for witness in sorted(
        witnesses,
        key=lambda item: (
            item.pixel_slope,
            item.top_intercept_px,
            item.bottom_intercept_px,
            item.physical_label.identity,
        ),
    ):
        top_ids = tuple(
            sorted(
                (
                    fragment.fragment_id
                    for fragment in ordered_fragments
                    if (
                        fragment.fragment_id in top_eligible
                        and _pixel_line_supports_fragment(
                            fragment,
                            witness.pixel_slope,
                            witness.top_intercept_px,
                        )
                    )
                ),
                key=str,
            )
        )
        top_set = set(top_ids)
        bottom_ids = tuple(
            sorted(
                (
                    fragment.fragment_id
                    for fragment in ordered_fragments
                    if (
                        fragment.fragment_id not in top_set
                        and fragment.fragment_id in bottom_eligible
                        and _pixel_line_supports_fragment(
                            fragment,
                            witness.pixel_slope,
                            witness.bottom_intercept_px,
                        )
                    )
                ),
                key=str,
            )
        )
        if top_ids and bottom_ids:
            states[(top_ids, bottom_ids)] = None
    return tuple(sorted(states))


def _grow_maximal_hypotheses(
    prefix: str,
    seeds: tuple[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        ...,
    ],
    fragment_map: dict[ObservationId, PhotoEdgeFragment],
    line_regions: dict[ObservationId, _PixelLineFeasibleRegion],
    top_eligible: frozenset[ObservationId],
    bottom_eligible: frozenset[ObservationId],
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    scale: CanvasPixelScale,
    parameters: PhotoEdgeDetectionParameters,
    budget: GeometryWorkBudget,
    long_extent_px: int,
    short_extent_px: int,
) -> tuple[PhotoEdgePairHypothesis, ...]:
    queue = list(seeds)
    visited: set[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
    ] = set()
    solved: dict[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        PhotoEdgePairHypothesis,
    ] = {}
    ordered_fragments = tuple(
        sorted(
            fragment_map.values(),
            key=lambda fragment: (
                -(
                    fragment.long_axis_footprint.maximum
                    - fragment.long_axis_footprint.minimum
                ),
                fragment.short_axis_position_interval.midpoint,
                fragment.long_axis_footprint.minimum,
                str(fragment.fragment_id),
            ),
        )
    )

    def solve(
        state: tuple[
            tuple[ObservationId, ...],
            tuple[ObservationId, ...],
        ],
    ) -> PhotoEdgePairHypothesis | None:
        existing = solved.get(state)
        if existing is not None:
            return existing
        if not budget.consume_consensus_state():
            return None
        hypothesis = _solve_hypothesis(
            prefix,
            state[0],
            state[1],
            fragment_map,
            corridors,
            scale,
            parameters,
            budget,
            long_extent_px,
            short_extent_px,
        )
        solved[state] = hypothesis
        return hypothesis

    maximal: list[PhotoEdgePairHypothesis] = []
    while queue and not budget.exhausted:
        top_ids, bottom_ids = queue.pop(0)
        key = (top_ids, bottom_ids)
        if key in visited:
            continue
        visited.add(key)
        hypothesis = solve(key)
        if hypothesis is None:
            break
        if hypothesis.state == EvidenceState.CONTRADICTED:
            continue
        if hypothesis.geometry is None:
            maximal.append(hypothesis)
            continue
        saturated_addition = False
        saturated_queue: list[
            tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
        ] = []
        for saturated in _witness_saturated_states(
            hypothesis,
            ordered_fragments,
            top_eligible,
            bottom_eligible,
        ):
            if (
                saturated == key
                or not set(top_ids).issubset(saturated[0])
                or not set(bottom_ids).issubset(saturated[1])
            ):
                continue
            preview = solve(saturated)
            if (
                preview is not None
                and preview.state != EvidenceState.CONTRADICTED
                and preview.geometry is not None
            ):
                saturated_addition = True
                if saturated not in visited:
                    saturated_queue.append(saturated)
        if saturated_addition:
            queue.extend(sorted(set(saturated_queue)))
            continue
        additions: list[
            tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
        ] = []
        used = set(top_ids) | set(bottom_ids)
        for fragment in ordered_fragments:
            fragment_id = fragment.fragment_id
            if fragment_id in used:
                continue
            region = line_regions[fragment_id]
            if (
                fragment_id in top_eligible
                and _line_region_intersects_geometry(
                    region,
                    hypothesis.geometry,
                    top=True,
                )
            ):
                additions.append(
                    (
                        tuple(sorted((*top_ids, fragment_id), key=str)),
                        bottom_ids,
                    )
                )
            if (
                fragment_id in bottom_eligible
                and _line_region_intersects_geometry(
                    region,
                    hypothesis.geometry,
                    top=False,
                )
            ):
                additions.append(
                    (
                        top_ids,
                        tuple(sorted((*bottom_ids, fragment_id), key=str)),
                    )
                )
        feasible_addition = False
        feasible_queue: list[
            tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
        ] = []
        for addition in additions:
            if addition in visited:
                continue
            preview = solve(addition)
            if (
                preview is not None
                and preview.state != EvidenceState.CONTRADICTED
                and preview.geometry is not None
            ):
                feasible_addition = True
                feasible_queue.append(addition)
        if not feasible_addition:
            maximal.append(hypothesis)
        else:
            queue.extend(sorted(set(feasible_queue)))
    subset_maximal = tuple(
        hypothesis
        for hypothesis in maximal
        if not any(
            hypothesis is not other
            and set(hypothesis.top_fragment_ids).issubset(
                other.top_fragment_ids
            )
            and set(hypothesis.bottom_fragment_ids).issubset(
                other.bottom_fragment_ids
            )
            and (
                set(hypothesis.top_fragment_ids)
                != set(other.top_fragment_ids)
                or set(hypothesis.bottom_fragment_ids)
                != set(other.bottom_fragment_ids)
            )
            for other in maximal
        )
    )
    canonical: dict[str, PhotoEdgePairHypothesis] = {}
    for hypothesis in sorted(
        subset_maximal,
        key=lambda item: (
            item.top_fragment_ids,
            item.bottom_fragment_ids,
            str(item.observation_id),
        ),
    ):
        signature = (
            "none"
            if hypothesis.geometry is None
            or hypothesis.geometry.normal_region is None
            else hypothesis.geometry.normal_region.canonical_signature
        )
        canonical.setdefault(signature, hypothesis)
    return tuple(canonical[key] for key in sorted(canonical))


def _audit_surfaces(
    fragments: tuple[PhotoEdgeFragment, ...],
    hypotheses: tuple[PhotoEdgePairHypothesis, ...],
    minimum_observations: int,
) -> tuple[
    tuple[PhotoEdgeFragmentSummary, ...],
    tuple[PhotoEdgeObservation, ...],
]:
    active_ids = {
        identity
        for hypothesis in hypotheses
        if hypothesis.geometry is not None
        for cell in hypothesis.geometry.cells
        for identity in cell.active_constraint_ids
    }
    witness_ids: set[ObservationId] = set()
    retained_fragment_ids = {
        fragment_id
        for hypothesis in hypotheses
        for fragment_id in (
            *hypothesis.top_fragment_ids,
            *hypothesis.bottom_fragment_ids,
        )
    }
    fragment_map = {
        fragment.fragment_id: fragment for fragment in fragments
    }
    for hypothesis in hypotheses:
        for side_ids in (
            hypothesis.top_fragment_ids,
            hypothesis.bottom_fragment_ids,
        ):
            observations = _minimum_support_witnesses(
                _observations_for_fragments(
                    side_ids,
                    fragment_map,
                ),
                minimum_observations,
            )
            witness_ids.update(
                observation.observation_id
                for observation in observations
            )
    audit_ids = active_ids | witness_ids
    summaries = tuple(
        PhotoEdgeFragmentSummary(
            fragment_id=fragment.fragment_id,
            long_axis_footprint=fragment.long_axis_footprint,
            short_axis_position_interval=(
                fragment.short_axis_position_interval
            ),
            canonical_observation_count=len(fragment.observations),
            ordered_constraint_sha256=fragment.constraint_sha256,
            censored=fragment.censored,
            active_observation_ids=tuple(
                observation.observation_id
                for observation in fragment.observations
                if observation.observation_id in active_ids
            ),
            minimum_support_witness_ids=tuple(
                observation.observation_id
                for observation in fragment.observations
                if observation.observation_id in witness_ids
            ),
        )
        for fragment in fragments
        if fragment.fragment_id in retained_fragment_ids
    )
    observations = tuple(
        observation
        for fragment in fragments
        if fragment.fragment_id in retained_fragment_ids
        for observation in fragment.observations
        if observation.observation_id in audit_ids
    )
    return summaries, observations


def solve_fixed_canvas_photo_edge_geometry(
    fragments: tuple[PhotoEdgeFragment, ...],
    corridors: tuple[PhotoEdgeSearchCorridor, ...],
    scale: CanvasPixelScale,
    parameters: PhotoEdgeDetectionParameters,
    *,
    observation_prefix: str,
    long_extent_px: int,
    short_extent_px: int,
) -> PhotoEdgeGeometryResult:
    budget = GeometryWorkBudget(
        maximum_region_cells=parameters.geometry.maximum_region_cells,
        maximum_consensus_states=(
            parameters.geometry.maximum_consensus_states
        ),
    )
    usable = tuple(
        fragment
        for fragment in fragments
        if any(
            not observation.censored
            for observation in fragment.observations
        )
    )
    fragment_map = {
        fragment.fragment_id: fragment for fragment in usable
    }
    line_regions = {
        fragment.fragment_id: _pixel_line_feasible_region(
            tuple(
                observation
                for observation in fragment.observations
                if not observation.censored
            ),
            parameters.maximum_search_angle_degrees,
            long_extent_px=long_extent_px,
            short_extent_px=short_extent_px,
        )
        for fragment in usable
    }
    top_role_candidates = tuple(
        fragment
        for fragment in usable
        if _fragment_role_eligible(fragment, corridors, top=True)
    )
    bottom_role_candidates = tuple(
        fragment
        for fragment in usable
        if _fragment_role_eligible(fragment, corridors, top=False)
    )
    top = tuple(
        fragment
        for fragment in top_role_candidates
        if line_regions[fragment.fragment_id].polygons
    )
    bottom = tuple(
        fragment
        for fragment in bottom_role_candidates
        if line_regions[fragment.fragment_id].polygons
    )
    top_groups, top_incomplete = _minimal_support_groups(
        top,
        parameters.minimum_independent_observations,
        line_regions,
        parameters,
        long_extent_px=long_extent_px,
        short_extent_px=short_extent_px,
    )
    bottom_groups, bottom_incomplete = _minimal_support_groups(
        bottom,
        parameters.minimum_independent_observations,
        line_regions,
        parameters,
        long_extent_px=long_extent_px,
        short_extent_px=short_extent_px,
    )
    group_regions: dict[
        tuple[ObservationId, ...],
        _PixelLineFeasibleRegion,
    ] = {}

    def group_region(
        fragment_ids: tuple[ObservationId, ...],
    ) -> _PixelLineFeasibleRegion:
        existing = group_regions.get(fragment_ids)
        if existing is not None:
            return existing
        region = _pixel_line_feasible_region(
            _observations_for_fragments(fragment_ids, fragment_map),
            parameters.maximum_search_angle_degrees,
            long_extent_px=long_extent_px,
            short_extent_px=short_extent_px,
        )
        group_regions[fragment_ids] = region
        return region

    def pair_is_possible(
        top_ids: tuple[ObservationId, ...],
        bottom_ids: tuple[ObservationId, ...],
    ) -> bool:
        if not _regions_share_slope(
            group_region(top_ids),
            group_region(bottom_ids),
        ):
            return False
        return _fixed_pair_outer_admissible(
            _observations_for_fragments(top_ids, fragment_map),
            _observations_for_fragments(bottom_ids, fragment_map),
            corridors,
            scale,
            parameters,
            long_extent_px=long_extent_px,
            short_extent_px=short_extent_px,
        )

    long_center_px = 0.5 * float(long_extent_px - 1)
    short_center_px = 0.5 * float(short_extent_px - 1)

    def discovery_coordinate(
        fragment_ids: tuple[ObservationId, ...],
    ) -> float:
        projected = tuple(
            intercept + slope * long_center_px
            for polygon in group_region(fragment_ids).polygons
            for slope, intercept in polygon
        )
        if not projected:
            raise ValueError(
                "photo-edge discovery group requires a line region"
            )
        return NumericInterval(min(projected), max(projected)).midpoint

    def nominal_deviation_mm(
        fragment_ids: tuple[ObservationId, ...],
        *,
        top_side: bool,
    ) -> float:
        observations = _observations_for_fragments(
            fragment_ids,
            fragment_map,
        )

        def interval_distance(
            interval: PixelInterval,
            coordinate: float,
        ) -> float:
            if coordinate < interval.minimum:
                return interval.minimum - coordinate
            if coordinate > interval.maximum:
                return coordinate - interval.maximum
            return 0.0

        return min(
            max(
                interval_distance(
                    observation.short_axis_position_interval,
                    (
                        corridor.nominal_top_px
                        if top_side
                        else corridor.nominal_bottom_px
                    ),
                )
                for observation in observations
            )
            / scale.short_axis_px_per_mm
            for corridor in corridors
        )

    def seed_order_key(
        top_ids: tuple[ObservationId, ...],
        bottom_ids: tuple[ObservationId, ...],
    ) -> tuple[object, ...]:
        top_coordinate = discovery_coordinate(top_ids)
        bottom_coordinate = discovery_coordinate(bottom_ids)
        top_slope = group_region(top_ids).slope_interval
        bottom_slope = group_region(bottom_ids).slope_interval
        if top_slope is None or bottom_slope is None:
            raise ValueError(
                "photo-edge discovery group requires a slope interval"
            )
        shared_slope = _intersect_numeric(top_slope, bottom_slope)
        if shared_slope is None:
            raise ValueError(
                "photo-edge discovery seed requires a shared slope"
            )
        representative_pixel_slope = shared_slope.midpoint
        physical_slope = (
            representative_pixel_slope
            * scale.long_axis_px_per_mm
            / scale.short_axis_px_per_mm
        )
        normalizer = math.sqrt(1.0 + physical_slope**2)
        pair_center_px = NumericInterval(
            min(top_coordinate, bottom_coordinate),
            max(top_coordinate, bottom_coordinate),
        ).midpoint
        center_offset_mm = abs(
            (pair_center_px - short_center_px)
            / scale.short_axis_px_per_mm
            / normalizer
        )
        physical_height_mm = (
            (bottom_coordinate - top_coordinate)
            / scale.short_axis_px_per_mm
            / normalizer
        )
        height_deviation_mm = min(
            abs(
                physical_height_mm
                - label.frame_size_mm.height_mm
            )
            for label in _label_order(corridors)
        )
        center_ratio = (
            center_offset_mm / parameters.maximum_center_offset_mm
        )
        height_ratio = (
            height_deviation_mm
            / parameters.maximum_photo_dimension_deviation_mm
        )
        nominal_ratio = max(
            nominal_deviation_mm(top_ids, top_side=True),
            nominal_deviation_mm(bottom_ids, top_side=False),
        ) / max(
            parameters.maximum_center_offset_mm,
            parameters.maximum_photo_dimension_deviation_mm,
        )
        return (
            nominal_ratio,
            max(center_ratio, height_ratio),
            center_ratio,
            height_ratio,
            abs(representative_pixel_slope),
            tuple(str(identity) for identity in top_ids),
            tuple(str(identity) for identity in bottom_ids),
        )

    seeds, seed_incomplete = _coordinate_seed_pairs(
        top_groups,
        bottom_groups,
        maximum_inspections=parameters.geometry.maximum_region_cells,
        maximum_seeds=parameters.geometry.maximum_consensus_states,
        pair_is_possible=pair_is_possible,
        top_discovery_coordinate=discovery_coordinate,
        bottom_discovery_coordinate=discovery_coordinate,
        top_group_order_key=lambda fragment_ids: (
            nominal_deviation_mm(fragment_ids, top_side=True),
            tuple(str(identity) for identity in fragment_ids),
        ),
        bottom_group_order_key=lambda fragment_ids: (
            nominal_deviation_mm(fragment_ids, top_side=False),
            tuple(str(identity) for identity in fragment_ids),
        ),
        paired_coordinate_sum=float(short_extent_px - 1),
        seed_order_key=seed_order_key,
    )
    budget.discovery_incomplete = (
        top_incomplete
        or bottom_incomplete
        or seed_incomplete
    )
    hypotheses = _grow_maximal_hypotheses(
        observation_prefix,
        seeds,
        fragment_map,
        line_regions,
        frozenset(fragment.fragment_id for fragment in top),
        frozenset(fragment.fragment_id for fragment in bottom),
        corridors,
        scale,
        parameters,
        budget,
        long_extent_px,
        short_extent_px,
    )
    summaries, audit = _audit_surfaces(
        fragments,
        hypotheses,
        parameters.minimum_independent_observations,
    )
    return PhotoEdgeGeometryResult(
        hypotheses=hypotheses,
        fragment_summaries=summaries,
        audit_observations=audit,
        attempted_hypothesis_count=budget.consumed_consensus_states,
        budget_exhausted=(
            budget.exhausted or budget.discovery_incomplete
        ),
        search_unavailable=bool(
            (
                len(
                    _minimum_support_witnesses(
                        tuple(
                            observation
                            for fragment in top_role_candidates
                            for observation in fragment.observations
                            if not observation.censored
                        ),
                        parameters.minimum_independent_observations,
                    )
                )
                >= parameters.minimum_independent_observations
                and not top_groups
            )
            or (
                len(
                    _minimum_support_witnesses(
                        tuple(
                            observation
                            for fragment in bottom_role_candidates
                            for observation in fragment.observations
                            if not observation.censored
                        ),
                        parameters.minimum_independent_observations,
                    )
                )
                >= parameters.minimum_independent_observations
                and not bottom_groups
            )
        ),
    )


def _pixel_intercept_interval_at_slope(
    observation: PhotoEdgeObservation,
    slope: float,
) -> NumericInterval:
    values = tuple(
        short_value - slope * long_value
        for long_value in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        )
        for short_value in (
            observation.short_axis_position_interval.minimum,
            observation.short_axis_position_interval.maximum,
        )
    )
    return NumericInterval(min(values), max(values))


def _pixel_intercept_outer_interval(
    observations: tuple[PhotoEdgeObservation, ...],
    slope: NumericInterval,
) -> NumericInterval | None:
    intervals = tuple(
        NumericInterval(
            min(
                short_value - slope_value * long_value
                for slope_value in (slope.minimum, slope.maximum)
                for long_value in (
                    observation.long_axis_footprint.minimum,
                    observation.long_axis_footprint.maximum,
                )
                for short_value in (
                    observation.short_axis_position_interval.minimum,
                    observation.short_axis_position_interval.maximum,
                )
            ),
            max(
                short_value - slope_value * long_value
                for slope_value in (slope.minimum, slope.maximum)
                for long_value in (
                    observation.long_axis_footprint.minimum,
                    observation.long_axis_footprint.maximum,
                )
                for short_value in (
                    observation.short_axis_position_interval.minimum,
                    observation.short_axis_position_interval.maximum,
                )
            ),
        )
        for observation in observations
    )
    minimum = max(interval.minimum for interval in intervals)
    maximum = min(interval.maximum for interval in intervals)
    if maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _pixel_intercept_at_slope(
    observations: tuple[PhotoEdgeObservation, ...],
    slope: float,
    short_extent_px: int,
) -> NumericInterval | None:
    intervals = tuple(
        _pixel_intercept_interval_at_slope(observation, slope)
        for observation in observations
    )
    minimum = max(interval.minimum for interval in intervals)
    maximum = min(interval.maximum for interval in intervals)
    for observation in observations:
        for coordinate in (
            observation.long_axis_footprint.minimum,
            observation.long_axis_footprint.maximum,
        ):
            minimum = max(minimum, -slope * coordinate)
            maximum = min(
                maximum,
                float(short_extent_px - 1) - slope * coordinate,
            )
    if maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _pixel_pair_witness(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    slope: float,
    short_extent_px: int,
    label: PhotoEdgePhysicalLabel,
) -> PhotoEdgeLineWitness | None:
    top = _pixel_intercept_at_slope(
        top_observations,
        slope,
        short_extent_px,
    )
    bottom = _pixel_intercept_at_slope(
        bottom_observations,
        slope,
        short_extent_px,
    )
    if top is None or bottom is None:
        return None
    polygon = _ordered_polygon(top, bottom)
    if not polygon:
        return None
    top_value = sum(point[0] for point in polygon) / float(len(polygon))
    bottom_value = sum(point[1] for point in polygon) / float(len(polygon))
    return PhotoEdgeLineWitness(
        pixel_slope=slope,
        top_intercept_px=top_value,
        bottom_intercept_px=bottom_value,
        top_intercept_feasible_px=top,
        bottom_intercept_feasible_px=bottom,
        physical_label=label,
    )


def solve_image_only_pair_geometry(
    top_observations: tuple[PhotoEdgeObservation, ...],
    bottom_observations: tuple[PhotoEdgeObservation, ...],
    frame_size_mm: FrameSizeMm,
    parameters: PhotoEdgeDetectionParameters,
    budget: GeometryWorkBudget,
    *,
    long_extent_px: int,
    short_extent_px: int,
) -> tuple[PhotoEdgePairGeometry | None, EvidenceState, tuple[PhotoEdgeFact, ...]]:
    label = PhotoEdgePhysicalLabel(None, None, frame_size_mm)
    maximum_slope = math.tan(
        math.radians(parameters.maximum_search_angle_degrees)
    )
    slope_resolution = (
        parameters.geometry.subpixel_resolution_px
        / float(max(1, long_extent_px - 1))
    )
    pending: list[tuple[str, NumericInterval, int]] = [
        ("", NumericInterval(-maximum_slope, maximum_slope), 0)
    ]
    cells: list[PhotoEdgeLineRegionCell] = []
    indeterminate = False
    while pending:
        path, slope, depth = pending.pop(0)
        if not budget.consume_region_cell():
            indeterminate = True
            break
        top_outer = _pixel_intercept_outer_interval(
            top_observations,
            slope,
        )
        bottom_outer = _pixel_intercept_outer_interval(
            bottom_observations,
            slope,
        )
        if top_outer is None or bottom_outer is None:
            continue
        raw = _ordered_polygon(top_outer, bottom_outer)
        if not raw:
            continue
        slope_values = tuple(
            dict.fromkeys((slope.midpoint, slope.minimum, slope.maximum))
        )
        witnesses = tuple(
            witness
            for slope_value in slope_values
            for witness in (
                _pixel_pair_witness(
                    top_observations,
                    bottom_observations,
                    slope_value,
                    short_extent_px,
                    label,
                ),
            )
            if witness is not None
        )
        if (
            len(witnesses) < len(slope_values)
            and depth < parameters.geometry.maximum_subdivision_depth
            and slope.width > slope_resolution
        ):
            midpoint = slope.midpoint
            pending.extend(
                (
                    (
                        f"{path}0",
                        NumericInterval(slope.minimum, midpoint),
                        depth + 1,
                    ),
                    (
                        f"{path}1",
                        NumericInterval(midpoint, slope.maximum),
                        depth + 1,
                    ),
                )
            )
            continue
        if not witnesses:
            indeterminate = True
            continue
        unique_witnesses = tuple(
            {
                (
                    witness.pixel_slope,
                    witness.top_intercept_px,
                    witness.bottom_intercept_px,
                ): witness
                for witness in witnesses
            }[key]
            for key in sorted(
                {
                    (
                        witness.pixel_slope,
                        witness.top_intercept_px,
                        witness.bottom_intercept_px,
                    )
                    for witness in witnesses
                }
            )
        )
        active = tuple(
            dict.fromkeys(
                (
                    *_active_pixel_constraints(
                        top_observations,
                        slope.midpoint,
                    ),
                    *_active_pixel_constraints(
                        bottom_observations,
                        slope.midpoint,
                    ),
                )
            )
        )
        signature = sha256(
            (
                f"{path}|{slope.minimum:.16g}|{slope.maximum:.16g}|"
                f"{top_outer.minimum:.8f}|{top_outer.maximum:.8f}|"
                f"{bottom_outer.minimum:.8f}|{bottom_outer.maximum:.8f}|"
                + ",".join(str(identity) for identity in active)
            ).encode("utf-8")
        ).hexdigest()
        cells.append(
            PhotoEdgeLineRegionCell(
                source_cell_signature=signature,
                pixel_slope=slope,
                top_intercept_px=top_outer,
                bottom_intercept_px=bottom_outer,
                possible_physical_labels=(label,),
                verified_witnesses=unique_witnesses,
                active_constraint_ids=active,
            )
        )
    unique = {
        cell.source_cell_signature: cell for cell in cells
    }
    retained = tuple(unique[key] for key in sorted(unique))
    if not retained:
        return (
            None,
            EvidenceState.UNAVAILABLE,
            (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,),
        )
    state = (
        EvidenceState.UNAVAILABLE
        if indeterminate
        else EvidenceState.SUPPORTED
    )
    facts = (
        (PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,)
        if indeterminate
        else ()
    )
    return (
        PhotoEdgePairGeometry(
            cells=retained,
            normal_region=None,
            work_long_axis_extent_px=long_extent_px,
            work_short_axis_extent_px=short_extent_px,
            interpolation_position_uncertainty_px=0.0,
            coordinate_space=PhotoEdgeCoordinateSpace.SOURCE,
            numerically_indeterminate=indeterminate,
        ),
        state,
        facts,
    )


def _active_pixel_constraints(
    observations: tuple[PhotoEdgeObservation, ...],
    slope: float,
) -> tuple[ObservationId, ...]:
    intervals = tuple(
        (
            observation,
            _pixel_intercept_interval_at_slope(observation, slope),
        )
        for observation in observations
    )
    lower = max(interval.minimum for _, interval in intervals)
    upper = min(interval.maximum for _, interval in intervals)
    lower_ids = tuple(
        observation.observation_id
        for observation, interval in intervals
        if (
            abs(interval.minimum - lower)
            <= _ACTIVE_CONSTRAINT_TOLERANCE
        )
    )
    upper_ids = tuple(
        observation.observation_id
        for observation, interval in intervals
        if (
            abs(interval.maximum - upper)
            <= _ACTIVE_CONSTRAINT_TOLERANCE
        )
    )
    return tuple(
        dict.fromkeys(
            (
                min(lower_ids, key=str),
                min(upper_ids, key=str),
            )
        )
    )


def _image_hypothesis(
    prefix: str,
    top_ids: tuple[ObservationId, ...],
    bottom_ids: tuple[ObservationId, ...],
    fragment_map: dict[ObservationId, PhotoEdgeFragment],
    frame_size_mm: FrameSizeMm,
    parameters: PhotoEdgeDetectionParameters,
    budget: GeometryWorkBudget,
    long_extent_px: int,
    short_extent_px: int,
) -> PhotoEdgePairHypothesis:
    geometry, state, facts = solve_image_only_pair_geometry(
        _observations_for_fragments(top_ids, fragment_map),
        _observations_for_fragments(bottom_ids, fragment_map),
        frame_size_mm,
        parameters,
        budget,
        long_extent_px=long_extent_px,
        short_extent_px=short_extent_px,
    )
    label = PhotoEdgePhysicalLabel(None, None, frame_size_mm)
    signature = (
        "disjoint"
        if geometry is None
        else sha256(
            "|".join(
                cell.source_cell_signature for cell in geometry.cells
            ).encode("utf-8")
        ).hexdigest()
    )
    observation_id = _hypothesis_id(
        prefix,
        top_ids,
        bottom_ids,
        signature,
    )
    return PhotoEdgePairHypothesis(
        observation_id=observation_id,
        top_fragment_ids=top_ids,
        bottom_fragment_ids=bottom_ids,
        geometry=geometry,
        physical_labels=(() if geometry is None else (label,)),
        state=state,
        facts=facts,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_EDGES,
            observation_id=observation_id,
            dependencies=(
                MeasurementIdentity.GRAY_WORK,
                MeasurementIdentity.FORMAT_PHYSICAL_SPEC,
            ),
            description="image-only lane photo-edge pair hypothesis",
            boundary_anchors=(*top_ids, *bottom_ids),
        ),
    )


def solve_image_only_lane_geometry(
    fragments: tuple[PhotoEdgeFragment, ...],
    frame_size_mm: FrameSizeMm,
    parameters: PhotoEdgeDetectionParameters,
    *,
    observation_prefix: str,
    long_extent_px: int,
    short_extent_px: int,
) -> PhotoEdgeGeometryResult:
    budget = GeometryWorkBudget(
        parameters.geometry.maximum_region_cells,
        parameters.geometry.maximum_consensus_states,
    )
    usable = tuple(
        fragment
        for fragment in fragments
        if any(
            not observation.censored
            for observation in fragment.observations
        )
    )
    fragment_map = {
        fragment.fragment_id: fragment for fragment in usable
    }
    line_regions = {
        fragment.fragment_id: _pixel_line_feasible_region(
            tuple(
                observation
                for observation in fragment.observations
                if not observation.censored
            ),
            parameters.maximum_search_angle_degrees,
            long_extent_px=long_extent_px,
            short_extent_px=short_extent_px,
        )
        for fragment in usable
    }
    groups, group_incomplete = _minimal_support_groups(
        usable,
        parameters.minimum_independent_observations,
        line_regions,
        parameters,
        long_extent_px=long_extent_px,
        short_extent_px=short_extent_px,
    )
    group_regions: dict[
        tuple[ObservationId, ...],
        _PixelLineFeasibleRegion,
    ] = {}

    def group_region(
        fragment_ids: tuple[ObservationId, ...],
    ) -> _PixelLineFeasibleRegion:
        existing = group_regions.get(fragment_ids)
        if existing is not None:
            return existing
        region = _pixel_line_feasible_region(
            _observations_for_fragments(fragment_ids, fragment_map),
            parameters.maximum_search_angle_degrees,
            long_extent_px=long_extent_px,
            short_extent_px=short_extent_px,
        )
        group_regions[fragment_ids] = region
        return region

    def pair_is_possible(
        top_ids: tuple[ObservationId, ...],
        bottom_ids: tuple[ObservationId, ...],
    ) -> bool:
        return bool(
            max(
                fragment_map[identity].short_axis_position_interval.midpoint
                for identity in top_ids
            )
            < min(
                fragment_map[identity].short_axis_position_interval.midpoint
                for identity in bottom_ids
            )
            and _regions_share_slope(
                group_region(top_ids),
                group_region(bottom_ids),
            )
        )

    seeds, seed_incomplete = _diagonal_seed_pairs(
        groups,
        groups,
        maximum_inspections=parameters.geometry.maximum_region_cells,
        maximum_seeds=parameters.geometry.maximum_consensus_states,
        pair_is_possible=pair_is_possible,
    )
    budget.discovery_incomplete = group_incomplete or seed_incomplete
    queue = list(seeds)
    visited: set[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]]
    ] = set()
    solved: dict[
        tuple[tuple[ObservationId, ...], tuple[ObservationId, ...]],
        PhotoEdgePairHypothesis,
    ] = {}

    def solve(
        state: tuple[
            tuple[ObservationId, ...],
            tuple[ObservationId, ...],
        ],
    ) -> PhotoEdgePairHypothesis | None:
        existing = solved.get(state)
        if existing is not None:
            return existing
        if not budget.consume_consensus_state():
            return None
        hypothesis = _image_hypothesis(
            observation_prefix,
            state[0],
            state[1],
            fragment_map,
            frame_size_mm,
            parameters,
            budget,
            long_extent_px,
            short_extent_px,
        )
        solved[state] = hypothesis
        return hypothesis

    maximal_hypotheses: list[PhotoEdgePairHypothesis] = []
    while queue and not budget.exhausted:
        state = queue.pop(0)
        if state in visited:
            continue
        visited.add(state)
        hypothesis = solve(state)
        if (
            hypothesis is None
            or hypothesis.state == EvidenceState.CONTRADICTED
        ):
            continue
        top_ids, bottom_ids = state
        used = set(top_ids) | set(bottom_ids)
        additions = tuple(
            addition
            for fragment_id in sorted(fragment_map, key=str)
            if fragment_id not in used
            for addition in (
                (
                    tuple(sorted((*top_ids, fragment_id), key=str)),
                    bottom_ids,
                ),
                (
                    top_ids,
                    tuple(sorted((*bottom_ids, fragment_id), key=str)),
                ),
            )
        )
        feasible_additions = tuple(
            addition
            for addition in additions
            if (
                (preview := solve(addition)) is not None
                and preview.state != EvidenceState.CONTRADICTED
                and preview.geometry is not None
            )
        )
        if feasible_additions:
            queue.extend(feasible_additions)
        else:
            maximal_hypotheses.append(hypothesis)
    maximal = tuple(
        hypothesis
        for hypothesis in maximal_hypotheses
        if not any(
            hypothesis is not other
            and set(hypothesis.top_fragment_ids).issubset(
                other.top_fragment_ids
            )
            and set(hypothesis.bottom_fragment_ids).issubset(
                other.bottom_fragment_ids
            )
            and (
                set(hypothesis.top_fragment_ids)
                != set(other.top_fragment_ids)
                or set(hypothesis.bottom_fragment_ids)
                != set(other.bottom_fragment_ids)
            )
            for other in maximal_hypotheses
        )
    )
    canonical: dict[str, PhotoEdgePairHypothesis] = {}
    for hypothesis in maximal:
        assert hypothesis.geometry is not None
        signature = sha256(
            "|".join(
                cell.source_cell_signature
                for cell in hypothesis.geometry.cells
            ).encode("utf-8")
        ).hexdigest()
        canonical.setdefault(signature, hypothesis)
    retained = tuple(canonical[key] for key in sorted(canonical))
    summaries, audit = _audit_surfaces(
        fragments,
        retained,
        parameters.minimum_independent_observations,
    )
    return PhotoEdgeGeometryResult(
        hypotheses=retained,
        fragment_summaries=summaries,
        audit_observations=audit,
        attempted_hypothesis_count=budget.consumed_consensus_states,
        budget_exhausted=(
            budget.exhausted or budget.discovery_incomplete
        ),
        search_unavailable=bool(
            not groups
            and len(
                _minimum_support_witnesses(
                    tuple(
                        observation
                        for fragment in usable
                        for observation in fragment.observations
                        if not observation.censored
                    ),
                    parameters.minimum_independent_observations,
                )
            )
            >= parameters.minimum_independent_observations
        ),
    )


def _perpendicular_height_interval(
    cell: PhotoEdgeLineRegionCell,
    shared_slope: NumericInterval,
) -> NumericInterval:
    intercept_height = NumericInterval(
        cell.bottom_intercept_px.minimum
        - cell.top_intercept_px.maximum,
        cell.bottom_intercept_px.maximum
        - cell.top_intercept_px.minimum,
    )
    denominators = tuple(
        math.sqrt(1.0 + slope * slope)
        for slope in (shared_slope.minimum, shared_slope.maximum)
    )
    return NumericInterval(
        intercept_height.minimum / max(denominators),
        intercept_height.maximum / min(denominators),
    )


def _witness_perpendicular_height_interval(
    witness: PhotoEdgeLineWitness,
) -> NumericInterval | None:
    denominator = math.sqrt(1.0 + witness.pixel_slope**2)
    minimum = max(
        0.0,
        (
            witness.bottom_intercept_feasible_px.minimum
            - witness.top_intercept_feasible_px.maximum
        )
        / denominator,
    )
    maximum = (
        witness.bottom_intercept_feasible_px.maximum
        - witness.top_intercept_feasible_px.minimum
    ) / denominator
    if maximum <= _POLYGON_EPSILON or maximum < minimum:
        return None
    return NumericInterval(minimum, maximum)


def _joint_lane_top_intercept(
    witness: PhotoEdgeLineWitness,
    perpendicular_height_px: float,
) -> float | None:
    separation = perpendicular_height_px * math.sqrt(
        1.0 + witness.pixel_slope**2
    )
    translated_bottom = NumericInterval(
        witness.bottom_intercept_feasible_px.minimum - separation,
        witness.bottom_intercept_feasible_px.maximum - separation,
    )
    feasible = _intersect_numeric(
        witness.top_intercept_feasible_px,
        translated_bottom,
    )
    if feasible is None:
        return None
    top = feasible.midpoint
    bottom = top + separation
    if not (
        witness.bottom_intercept_feasible_px.minimum
        - _POLYGON_EPSILON
        <= bottom
        <= witness.bottom_intercept_feasible_px.maximum
        + _POLYGON_EPSILON
    ):
        return None
    return top


def _joint_witness(
    first: PhotoEdgeLineWitness,
    second: PhotoEdgeLineWitness,
) -> tuple[float, float, float, float] | None:
    if not math.isclose(
        first.pixel_slope,
        second.pixel_slope,
        rel_tol=0.0,
        abs_tol=_POLYGON_EPSILON,
    ):
        return None
    first_height = _witness_perpendicular_height_interval(first)
    second_height = _witness_perpendicular_height_interval(second)
    if first_height is None or second_height is None:
        return None
    shared_height = _intersect_numeric(first_height, second_height)
    if shared_height is None or shared_height.maximum <= _POLYGON_EPSILON:
        return None
    height = max(
        shared_height.midpoint,
        _POLYGON_EPSILON,
    )
    first_top = _joint_lane_top_intercept(first, height)
    second_top = _joint_lane_top_intercept(second, height)
    if first_top is None or second_top is None:
        return None
    return (
        0.5 * (first.pixel_slope + second.pixel_slope),
        height,
        first_top,
        second_top,
    )


def join_dual_lane_hypotheses(
    first: tuple[PhotoEdgePairHypothesis, ...],
    second: tuple[PhotoEdgePairHypothesis, ...],
) -> DualLanePhotoEdgeJointRegion:
    first_supported = tuple(
        hypothesis
        for hypothesis in first
        if hypothesis.state == EvidenceState.SUPPORTED
    )
    second_supported = tuple(
        hypothesis
        for hypothesis in second
        if hypothesis.state == EvidenceState.SUPPORTED
    )
    if len(first_supported) != 1 or len(second_supported) != 1:
        competing = (
            len(first_supported) > 1
            or len(second_supported) > 1
        )
        return DualLanePhotoEdgeJointRegion(
            cells=(),
            selected_pair_ids=None,
            state=EvidenceState.UNAVAILABLE,
            facts=(
                (
                    PhotoEdgeFact.COMPETING_PAIRS_UNRESOLVED
                    if competing
                    else PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE
                ),
            ),
            numerically_indeterminate=False,
        )
    first_hypothesis = first_supported[0]
    second_hypothesis = second_supported[0]
    assert first_hypothesis.geometry is not None
    assert second_hypothesis.geometry is not None
    joint_cells: list[DualLaneJointCell] = []
    outer_joint_possible = False
    for first_cell, second_cell in product(
        first_hypothesis.geometry.cells,
        second_hypothesis.geometry.cells,
    ):
        slope_minimum = max(
            first_cell.pixel_slope.minimum,
            second_cell.pixel_slope.minimum,
        )
        slope_maximum = min(
            first_cell.pixel_slope.maximum,
            second_cell.pixel_slope.maximum,
        )
        if slope_maximum < slope_minimum:
            continue
        slope = NumericInterval(slope_minimum, slope_maximum)
        first_height = _perpendicular_height_interval(
            first_cell,
            slope,
        )
        second_height = _perpendicular_height_interval(
            second_cell,
            slope,
        )
        height_minimum = max(
            0.0,
            first_height.minimum,
            second_height.minimum,
        )
        height_maximum = min(
            first_height.maximum,
            second_height.maximum,
        )
        if height_maximum < height_minimum:
            continue
        outer_joint_possible = True
        height = NumericInterval(height_minimum, height_maximum)
        verified = next(
            (
                joint
                for first_witness, second_witness in product(
                    first_cell.verified_witnesses,
                    second_cell.verified_witnesses,
                )
                if (
                    joint := _joint_witness(
                        first_witness,
                        second_witness,
                    )
                )
                is not None
            ),
            None,
        )
        if verified is None:
            continue
        (
            verified_slope,
            verified_height,
            first_top,
            second_top,
        ) = verified
        joint_cells.append(
            DualLaneJointCell(
                first_pair_id=first_hypothesis.observation_id,
                second_pair_id=second_hypothesis.observation_id,
                pixel_slope=slope,
                perpendicular_height_px=height,
                verified_pixel_slope=verified_slope,
                verified_perpendicular_height_px=verified_height,
                verified_first_top_intercept_px=first_top,
                verified_second_top_intercept_px=second_top,
                source_cell_signatures=(
                    first_cell.source_cell_signature,
                    second_cell.source_cell_signature,
                ),
            )
        )
    if joint_cells:
        selected = (
            first_hypothesis.observation_id,
            second_hypothesis.observation_id,
        )
        canonical = {
            (
                cell.source_cell_signatures,
                cell.verified_pixel_slope,
                cell.verified_perpendicular_height_px,
            ): cell
            for cell in joint_cells
        }
        return DualLanePhotoEdgeJointRegion(
            cells=tuple(canonical[key] for key in sorted(canonical)),
            selected_pair_ids=selected,
            state=EvidenceState.SUPPORTED,
            facts=(),
            numerically_indeterminate=False,
        )
    if outer_joint_possible:
        return DualLanePhotoEdgeJointRegion(
            cells=(),
            selected_pair_ids=None,
            state=EvidenceState.UNAVAILABLE,
            facts=(PhotoEdgeFact.PAIR_GEOMETRY_UNAVAILABLE,),
            numerically_indeterminate=True,
        )
    return DualLanePhotoEdgeJointRegion(
        cells=(),
        selected_pair_ids=None,
        state=EvidenceState.CONTRADICTED,
        facts=(PhotoEdgeFact.PAIR_GEOMETRY_CONTRADICTED,),
        numerically_indeterminate=False,
    )
