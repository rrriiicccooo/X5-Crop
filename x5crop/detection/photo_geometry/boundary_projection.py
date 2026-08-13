"""Projection of observed runs into a shared direction class."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval, PositiveInterval
from .boundary_geometry import (
    canonical_source_cross_axis_slope,
    canonical_source_sequence_axis_slope,
)
from .interval_math import hull
from .transition_tracking import median_canonical_location
from .model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
)
from .measurement_model import PhotoBoundaryTransition
from .output_model import SharedStripDirection
from .observation_types import ProfileRun

@dataclass(frozen=True)
class BoundRunProjection:
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-8,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-8,
            )
        ):
            raise ValueError("bound run projection is invalid")


def project_profile_run(
    run: ProfileRun,
    *,
    transitions: dict[str, PhotoBoundaryTransition],
    direction: SharedStripDirection,
    boundary_axis: BoundaryAxis,
    source_width_axis: BoundaryAxis,
    reference_trace_px: float,
    boundary_scale_px_per_mm: PositiveInterval,
    observed_direction_interval_degrees: FiniteInterval | None = None,
    observed_canonical_direction_degrees: float | None = None,
    preserve_transition_extent: bool = False,
    projection_cache: dict[tuple[object, ...], BoundRunProjection] | None = None,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> BoundRunProjection:
    projection_direction_key: object = (
        direction.direction_id
        if observed_canonical_direction_degrees is None
        else (
            "observed-edge-direction",
            observed_canonical_direction_degrees,
            observed_direction_interval_degrees,
        )
    )
    cache_key = (
        run.run_id,
        projection_direction_key,
        boundary_axis.value,
        source_width_axis.value,
        reference_trace_px.hex(),
        boundary_scale_px_per_mm.minimum.hex(),
        boundary_scale_px_per_mm.maximum.hex(),
        None
        if observed_direction_interval_degrees is None
        else observed_direction_interval_degrees.minimum.hex(),
        None
        if observed_direction_interval_degrees is None
        else observed_direction_interval_degrees.maximum.hex(),
        None
        if observed_canonical_direction_degrees is None
        else observed_canonical_direction_degrees.hex(),
        preserve_transition_extent,
        spec,
    )
    if projection_cache is not None and cache_key in projection_cache:
        return projection_cache[cache_key]
    try:
        bound = tuple(transitions[str(identity)] for identity in run.transition_ids)
    except KeyError as exc:
        raise ValueError("profile run transition is unavailable") from exc
    if not bound:
        raise ValueError("profile run has no transition evidence")
    if boundary_axis == source_width_axis:
        canonical_slope = canonical_source_sequence_axis_slope(
            direction,
            source_width_axis,
        )
    else:
        canonical_slope = canonical_source_cross_axis_slope(
            direction,
            boundary_axis,
        )
    if observed_direction_interval_degrees is not None:
        if (
            observed_canonical_direction_degrees is None
            or not observed_direction_interval_degrees.contains(
                observed_canonical_direction_degrees,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("observed line direction is incomplete")
        canonical_slope = math.tan(
            math.radians(observed_canonical_direction_degrees)
        )
        if boundary_axis == source_width_axis:
            canonical_slope = -canonical_slope
    centers = tuple(
        transition.coordinate_px
        + canonical_slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition in bound
    )
    canonical = median_canonical_location(centers)
    residuals = tuple(value - canonical for value in centers)
    center = sorted(residuals)[len(residuals) // 2]
    absolute = sorted(abs(value - center) for value in residuals)
    mad = absolute[len(absolute) // 2]
    numeric = spec.transition_coordinate_sampling_uncertainty_px
    fit_uncertainty = mad / math.sqrt(len(bound)) + numeric
    # Position and direction are separate physical quantities.  The complete
    # chain later joins the retained direction proposal with sequence evidence;
    # converting the direction interval into position padding here would count
    # the same uncertainty twice and can manufacture a wide crop envelope.
    fit = FiniteInterval(
        canonical - fit_uncertainty,
        canonical + fit_uncertainty,
    )
    # The peak-localization interval owns boundary position.  A wider
    # contiguous change region helps discover and group the same physical
    # edge, but treating the whole gradient ramp as crop uncertainty turns
    # image tone into padding.  Only an explicitly selected outer edge asks to
    # preserve the complete transition extent; reliable two-dimensional
    # content crossing a localized boundary is handled by the negative-only
    # content layer.
    position_intervals = tuple(
        (
            transition.physical_position_interval_px
            if preserve_transition_extent
            else transition.localization_interval_px
        )
        for transition in bound
    )
    projected = tuple(
        coordinate
        + slope
        * (reference_trace_px - float(transition.trace_coordinate_px))
        for transition, position_interval in zip(
            bound,
            position_intervals,
            strict=True,
        )
        for coordinate in (
            position_interval.minimum,
            position_interval.maximum,
        )
        for slope in (canonical_slope,)
    )
    comparison_blind_radius = (
        float(spec.transition_gap_px(boundary_scale_px_per_mm.maximum))
        if boundary_axis != source_width_axis
        else 0.0
    )
    # The projected intervals already contain every observed local departure
    # from the shared line.  The only additional term is the registered
    # measurement operator's unobserved central comparison gap.  Sequence
    # separator sides preserve their complete material-transition extent
    # above, so adding the comparison gap there would count the same support
    # twice.
    full = FiniteInterval(
        min(projected) - numeric - comparison_blind_radius,
        max(projected) + numeric + comparison_blind_radius,
    )
    if not full.contains(canonical, epsilon=1.0e-8):
        raise ValueError("canonical run position escaped exact projection")
    full = hull((full, fit))
    result = BoundRunProjection(canonical, fit, full)
    if projection_cache is not None:
        projection_cache[cache_key] = result
    return result
