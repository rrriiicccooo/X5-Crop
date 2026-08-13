"""Project and condition measured short-axis edge observations."""

from __future__ import annotations

from ...domain import FiniteInterval
from .chain_proposals import LaneObservationInput
from .interval_math import add, intersect, subtract
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    independent_spatial_support_count,
)
from .measurement_model import (
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .line_observations import PhotoBoundaryObservation
from .observation_types import ProfileRun
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .trace_support import (
    PIXEL_CENTER_HALF_EXTENT_PX,
    continuous_trace_support_fraction,
)


def line_boundary_coordinate(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> float:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        if abs(line.normal_y) <= 1.0e-12:
            raise ValueError("cross-boundary line cannot project y")
        return (
            line.offset_px - line.normal_x * trace_coordinate_px
        ) / line.normal_y
    if abs(line.normal_x) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project x")
    return (
        line.offset_px - line.normal_y * trace_coordinate_px
    ) / line.normal_x


def observation_coordinate_interval(
    observation: PhotoBoundaryObservation,
    *,
    boundary_axis: BoundaryAxis,
    trace_coordinate_px: float,
) -> FiniteInterval:
    line = observation.line
    if boundary_axis == BoundaryAxis.Y:
        normal = line.normal_y
        other = line.normal_x
    else:
        normal = line.normal_x
        other = line.normal_y
    if abs(normal) <= 1.0e-12:
        raise ValueError("cross-boundary line cannot project coordinate")
    values = tuple(
        (offset - other * trace_coordinate_px) / normal
        for offset in (
            observation.offset_interval_px.minimum,
            observation.offset_interval_px.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def inlier_profile_run(
    lane: LaneObservationInput,
    run: ProfileRun,
    observation: PhotoBoundaryObservation,
    measurement_set: PhotoBoundaryMeasurementSet,
    support_interval_px: FiniteInterval | None = None,
) -> ProfileRun:
    selected = tuple(
        transition
        for transition in measurement_set.transitions
        if transition.transition_id in set(observation.transition_ids)
    )
    traces = tuple(
        sorted({transition.trace_coordinate_px for transition in selected})
    )
    queried = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(
            float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
        )
    )
    return ProfileRun(
        run_id=physical_fact_id(
            "inlier-profile-run",
            run.run_id,
            observation.observation_id,
        ),
        coordinate_interval_px=observation_coordinate_interval(
            observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=lane.width_authority_px.center,
        ),
        transition_ids=observation.transition_ids,
        trace_coordinates_px=traces,
        role_hint=run.role_hint,
        qualified_anchor_roles=run.qualified_anchor_roles,
        support_fraction=observation.trace_support_count / len(queried),
        continuous_support_fraction=observation.continuous_support_fraction,
        fit_residual_px=observation.fit_residual_px,
        evidence_strength=sum(
            transition.gradient_z
            + max(transition.tone_z, transition.texture_z)
            for transition in selected
        )
        / len(selected),
        pair_qualified=run.pair_qualified,
    )


def format_bound_opposite_run(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    known_observation: PhotoBoundaryObservation,
    known_role: BoundaryRole,
    support_interval_px: FiniteInterval | None = None,
    *,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> ProfileRun | None:
    """Bind existing opposite-edge transitions through one edge and fixed H."""

    if known_role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        raise ValueError("fixed-H refinement requires top or bottom evidence")
    target_role = (
        BoundaryRole.BOTTOM
        if known_role == BoundaryRole.TOP
        else BoundaryRole.TOP
    )
    target_measurement = (
        lane.bottom_measurement_set
        if target_role == BoundaryRole.BOTTOM
        else lane.top_measurement_set
    )

    height = geometry.height_state.extent_projection_px()
    by_trace: dict[int, list[PhotoBoundaryTransition]] = {}
    for transition in target_measurement.transitions:
        if (
            support_interval_px is not None
            and not support_interval_px.contains(
                float(transition.trace_coordinate_px),
                epsilon=PIXEL_CENTER_HALF_EXTENT_PX,
            )
        ):
            continue
        known_coordinate = line_boundary_coordinate(
            known_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        implied = (
            subtract(
                transition.localization_interval_px,
                FiniteInterval.exact(known_coordinate),
            )
            if known_role == BoundaryRole.TOP
            else subtract(
                FiniteInterval.exact(known_coordinate),
                transition.localization_interval_px,
            )
        )
        if intersect(implied, height) is not None:
            by_trace.setdefault(transition.trace_coordinate_px, []).append(
                transition
            )

    selected: list[PhotoBoundaryTransition] = []
    for trace in target_measurement.query.trace_positions_px:
        values = by_trace.get(trace, ())
        # The fixed-H corridor authorizes a local query, not a nearest-line
        # winner.  If more than one measured transition remains physically
        # feasible on the same trace, that trace is ambiguous and lends no
        # point to this refined family.
        if len(values) != 1:
            continue
        selected.append(values[0])

    queried = tuple(
        trace
        for trace in target_measurement.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(
            float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
        )
    )
    if (
        len(selected) < 2
        or independent_spatial_support_count(
            queried,
            tuple(item.trace_coordinate_px for item in selected),
        )
        < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
    ):
        return None
    reference = lane.width_authority_px.center
    known_reference = line_boundary_coordinate(
        known_observation,
        boundary_axis=lane.height_axis,
        trace_coordinate_px=reference,
    )
    projected: list[FiniteInterval] = []
    for transition in selected:
        known_at_trace = line_boundary_coordinate(
            known_observation,
            boundary_axis=lane.height_axis,
            trace_coordinate_px=float(transition.trace_coordinate_px),
        )
        projected.append(
            add(
                transition.localization_interval_px,
                FiniteInterval.exact(known_reference - known_at_trace),
            )
        )
    centers = sorted(value.center for value in projected)
    center = centers[len(centers) // 2]
    deviations = sorted(abs(value - center) for value in centers)
    mad = deviations[len(deviations) // 2]
    half_width = max(value.width / 2.0 for value in projected)
    interval = FiniteInterval(
        center
        - spec.inlier_mad_multiplier * mad
        - half_width,
        center
        + spec.inlier_mad_multiplier * mad
        + half_width,
    )
    traces = tuple(sorted(item.trace_coordinate_px for item in selected))
    return ProfileRun(
        run_id=physical_fact_id(
            "cross_proposal-bound-opposite-run",
            geometry.frame_spec.frame_spec_id,
            known_role.value,
            target_role.value,
            known_observation.observation_id,
            *(str(item.transition_id) for item in selected),
        ),
        coordinate_interval_px=interval,
        transition_ids=tuple(
            sorted((item.transition_id for item in selected), key=str)
        ),
        trace_coordinates_px=traces,
        role_hint=target_role,
        qualified_anchor_roles=(),
        support_fraction=len(selected) / len(queried),
        continuous_support_fraction=continuous_trace_support_fraction(
            queried,
            traces,
            spec=spec,
        ),
        fit_residual_px=mad,
        evidence_strength=sum(
            item.gradient_z + max(item.tone_z, item.texture_z)
            for item in selected
        )
        / len(selected),
        pair_qualified=True,
    )
