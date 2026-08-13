"""Condition one short-axis proposal into fixed-H frame positions."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import FiniteInterval
from .boundary_geometry import canonical_source_cross_axis_slope
from .boundary_projection import BoundRunProjection, project_profile_run
from .chain_proposals import CrossAxisProposal, LaneObservationInput
from .direction_proposals import conditional_fit_and_full
from .interval_math import add, hull, intersect, subtract
from .line_observations import PhotoBoundaryObservation
from .model import BoundaryRole
from .observation_types import ProfileRun
from .output_model import SharedStripDirection
from .source_geometry import SourceScanGeometry, centered_short_axis_authority_px


@dataclass(frozen=True)
class ConditionedCrossPlacement:
    lane_reference_trace_px: float
    observed_runs: dict[BoundaryRole, ProfileRun]
    observations_by_role: dict[BoundaryRole, PhotoBoundaryObservation]
    observation_directions_by_role: dict[
        BoundaryRole,
        tuple[FiniteInterval, float],
    ]
    lane_projections: dict[BoundaryRole, BoundRunProjection]
    top_canonical_positions_px: tuple[float, ...]
    bottom_canonical_positions_px: tuple[float, ...]


def _slope_displacement_interval(
    slope: FiniteInterval,
    trace_delta_px: float,
) -> FiniteInterval:
    values = (
        slope.minimum * trace_delta_px,
        slope.maximum * trace_delta_px,
    )
    return FiniteInterval(min(values), max(values))


def conditioned_observation_direction(
    observation,
    direction: SharedStripDirection,
) -> tuple[FiniteInterval, float]:
    """Condition one raw edge on the selected common lane direction.

    A local peak-centre regression is not allowed to rotate one frame edge
    independently.  Once cross and sequence evidence establish the lane
    direction, every top/bottom family uses that canonical direction whenever
    its complete measured interval admits it.  The retained interval still
    preserves local continuous bend for the selected placement's safety
    envelope.
    """

    retained = intersect(
        observation.angle_interval_degrees,
        direction.full_angle_interval_degrees,
    )
    if retained is None:
        raise ValueError("cross observation has no common lane direction")
    canonical = direction.canonical_angle_degrees
    if not retained.contains(canonical, epsilon=1.0e-9):
        canonical = retained.center
    return retained, canonical


def condition_cross_placement(
    lane: LaneObservationInput,
    cross_proposal: CrossAxisProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    frame_reference_traces_px: tuple[float, ...],
    frame_reference_intervals_px: tuple[FiniteInterval, ...],
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
) -> ConditionedCrossPlacement:
    if (
        not frame_reference_traces_px
        or len(frame_reference_traces_px) != len(frame_reference_intervals_px)
    ):
        raise ValueError("cross placement frame references are incomplete")
    # A partial strip may occupy any long-axis phase.  Transverse centring is
    # therefore anchored at the physical slot chain's own midpoint, not at
    # the raster/holder long-axis midpoint.  For equal-W frames the midpoint
    # of the first and last frame centres is exactly the placed strip extent
    # midpoint, including any real local advances between them.
    lane_reference = (
        frame_reference_traces_px[0] + frame_reference_traces_px[-1]
    ) / 2.0
    observed_runs = {
        run.role_hint: run
        for run in cross_proposal.observed_runs
    }
    observation_by_role = {
        observation.role: observation
        for observation in cross_proposal.raw_observations
    }
    observation_direction_by_role = {
        role: conditioned_observation_direction(observation, direction)
        for role, observation in observation_by_role.items()
    }
    lane_projections = {
        role: project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane_reference,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
            observed_direction_interval_degrees=(
                observation_direction_by_role[role][0]
            ),
            observed_canonical_direction_degrees=(
                observation_direction_by_role[role][1]
            ),
            projection_cache=projection_cache,
        )
        for role, run in observed_runs.items()
    }
    extent = geometry.height_state.extent_projection_px()
    shared_extent = extent
    _scale, normalized, _factor = geometry.height_state.canonical_state()
    canonical_extent_preference = (
        geometry.height_state.design_extent_mm * normalized
    )
    canonical_extent = (
        canonical_extent_preference
        if shared_extent.contains(canonical_extent_preference)
        else shared_extent.center
    )
    canonical_extent_interval = FiniteInterval.exact(canonical_extent)
    canonical_slope = canonical_source_cross_axis_slope(
        direction,
        lane.height_axis,
    )
    # R_format has one chosen lane direction.  The lane direction family is
    # transform/report authority, not a padding interval.  Direct top/bottom
    # lines are projected below with their own measured slope intervals.
    slope_interval = FiniteInterval.exact(canonical_slope)
    # The film centreline crosses the holder's short-axis centre at the placed
    # strip midpoint.  Its only transverse uncertainty comes from retained
    # physical geometry; there is no independent +/-mm centre allowance.
    centred_centerline_at_reference = centered_short_axis_authority_px(
        lane.height_authority_px,
        lane.height_scale_px_per_mm,
    )
    centred_phase = FiniteInterval(
        centred_centerline_at_reference.minimum - extent.maximum / 2.0,
        centred_centerline_at_reference.maximum - extent.minimum / 2.0,
    )
    phase_fit_constraints: list[FiniteInterval] = [centred_phase]
    phase_full_constraints: list[FiniteInterval] = [centred_phase]
    phase_preferences: list[float] = []
    for role, projected in lane_projections.items():
        if role == BoundaryRole.TOP:
            phase_fit_constraints.append(projected.fit_position_interval_px)
            phase_full_constraints.append(projected.full_position_interval_px)
            phase_preferences.append(projected.canonical_position_px)
        else:
            phase_fit_constraints.append(
                subtract(
                    projected.fit_position_interval_px,
                    shared_extent,
                )
            )
            phase_full_constraints.append(
                subtract(
                    projected.full_position_interval_px,
                    shared_extent,
                )
            )
            phase_preferences.append(
                projected.canonical_position_px - canonical_extent
            )
    phase_state = conditional_fit_and_full(
        tuple(phase_fit_constraints),
        tuple(phase_full_constraints),
    )
    if not cross_proposal.direct_height_span_validated:
        # A single visible side may be a photo edge, a holder edge, or the film
        # limit; the project deliberately treats them as equivalent safety
        # boundaries.  It therefore has no authority to translate the fixed-H
        # rectangle away from the independently known centred film axis.  The
        # observation remains direct outward safety evidence below.  Only a
        # physically compatible opposite-edge span may calibrate H/centreline.
        phase_state = (centred_phase, centred_phase)
        phase_preferences = [centred_phase.center]
    if phase_state is None or not phase_preferences:
        raise ValueError("cross evidence cannot place one centred fixed-H frame")
    phase_fit, phase_full = phase_state
    ordered_phase_preferences = sorted(phase_preferences)
    midpoint = len(ordered_phase_preferences) // 2
    canonical_phase_preference = (
        ordered_phase_preferences[midpoint]
        if len(ordered_phase_preferences) % 2
        else (
            ordered_phase_preferences[midpoint - 1]
            + ordered_phase_preferences[midpoint]
        )
        / 2.0
    )
    canonical_phase = (
        canonical_phase_preference
        if phase_fit.contains(canonical_phase_preference)
        else phase_fit.center
    )
    frame_states: list[
        tuple[
            dict[BoundaryRole, FiniteInterval],
            dict[BoundaryRole, FiniteInterval],
            float,
        ]
    ] = []
    for reference, reference_interval in zip(
        frame_reference_traces_px,
        frame_reference_intervals_px,
        strict=True,
    ):
        delta = reference - lane_reference
        canonical_shift = canonical_slope * delta
        shift = _slope_displacement_interval(slope_interval, delta)
        model_top_fit = add(phase_fit, shift)
        model_bottom_fit = add(model_top_fit, extent)
        full_shifts = tuple(
            _slope_displacement_interval(
                slope_interval,
                endpoint - lane_reference,
            )
            for endpoint in (
                reference_interval.minimum,
                reference_interval.maximum,
            )
        )
        model_top_full = add(phase_full, hull(full_shifts))
        model_bottom_full = add(model_top_full, extent)
        frame_fit = {
            BoundaryRole.TOP: model_top_fit,
            BoundaryRole.BOTTOM: model_bottom_fit,
        }
        frame_full = {
            BoundaryRole.TOP: model_top_full,
            BoundaryRole.BOTTOM: model_bottom_full,
        }
        if cross_proposal.direct_height_span_validated:
            for role, run in observed_runs.items():
                direct_values = tuple(
                    project_profile_run(
                        run,
                        transitions=lane.transition_by_id,
                        direction=direction,
                        boundary_axis=lane.height_axis,
                        source_width_axis=lane.width_axis,
                        reference_trace_px=endpoint,
                        boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                        observed_direction_interval_degrees=(
                            observation_direction_by_role[role][0]
                        ),
                        observed_canonical_direction_degrees=(
                            observation_direction_by_role[role][1]
                        ),
                        projection_cache=projection_cache,
                    )
                    for endpoint in (
                        reference,
                        reference_interval.minimum,
                        reference_interval.maximum,
                    )
                )
                frame_full[role] = hull(
                    (
                        frame_full[role],
                        hull(
                            tuple(
                                item.full_position_interval_px
                                for item in direct_values
                            )
                        ),
                    )
                )
        frame_states.append((frame_fit, frame_full, canonical_shift))

    top_canonical: list[float] = []
    bottom_canonical: list[float] = []
    for frame_fit, frame_full, canonical_shift in frame_states:
        frame_phase = conditional_fit_and_full(
            (
                frame_fit[BoundaryRole.TOP],
                subtract(
                    frame_fit[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
            (
                frame_full[BoundaryRole.TOP],
                subtract(
                    frame_full[BoundaryRole.BOTTOM],
                    canonical_extent_interval,
                ),
            ),
        )
        if frame_phase is None:
            raise ValueError("canonical source height is infeasible at frame")
        frame_phase_interval = frame_phase[0]
        predicted_phase = canonical_phase + canonical_shift
        # The lane is centred at its physical midpoint, but the film may have
        # a small continuous bend.  At another frame reference a directly
        # observed boundary may therefore move the local centreline within the
        # already retained physical interval.  This is not an independent
        # per-frame phase: the shared direction supplies the prediction and
        # evidence may only condition it locally.
        frame_phase = (
            predicted_phase
            if frame_phase_interval.contains(predicted_phase, epsilon=1.0e-8)
            else frame_phase_interval.center
        )
        canonical_top = frame_phase
        canonical_bottom = frame_phase + canonical_extent
        if canonical_top >= canonical_bottom:
            raise ValueError("canonical height placement is unordered")
        top_canonical.append(canonical_top)
        bottom_canonical.append(canonical_bottom)
    return ConditionedCrossPlacement(
        lane_reference_trace_px=lane_reference,
        observed_runs=observed_runs,
        observations_by_role=observation_by_role,
        observation_directions_by_role=observation_direction_by_role,
        lane_projections=lane_projections,
        top_canonical_positions_px=tuple(top_canonical),
        bottom_canonical_positions_px=tuple(bottom_canonical),
    )
