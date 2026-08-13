"""Materialize one fixed-format short-axis placement."""

from __future__ import annotations

from ...domain import FiniteInterval
from .boundary_projection import BoundRunProjection, project_profile_run
from .chain_proposals import CrossAxisProposal, LaneObservationInput
from .chains import CrossPlacement, CrossRoleEvidence
from .cross_conditioning import condition_cross_placement
from .interval_math import hull, intersect
from .model import BoundaryRole, PHOTO_BOUNDARY_MEASUREMENT_SPEC
from .observation_types import ProfileRun
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .trace_support import (
    PIXEL_CENTER_HALF_EXTENT_PX,
    continuous_trace_support_fraction,
)


def materialize_cross_placement(
    lane: LaneObservationInput,
    cross_proposal: CrossAxisProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    frame_reference_traces_px: tuple[float, ...],
    frame_reference_intervals_px: tuple[FiniteInterval, ...],
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
) -> CrossPlacement:
    state = condition_cross_placement(
        lane,
        cross_proposal,
        direction,
        geometry,
        frame_reference_traces_px,
        frame_reference_intervals_px,
        projection_cache,
    )
    lane_reference = state.lane_reference_trace_px
    observed_runs = state.observed_runs
    observation_by_role = state.observations_by_role
    observation_direction_by_role = state.observation_directions_by_role
    lane_projections = state.lane_projections
    top_canonical = list(state.top_canonical_positions_px)
    bottom_canonical = list(state.bottom_canonical_positions_px)
    # Source height feasibility selects one fixed H rectangle.  Compatibility
    # ranges validate that placement but are not themselves crop padding.  A
    # selected direct holder/film/photo edge may extend the same minimum safe
    # range outward.
    frame_width = geometry.width_state.extent_projection_px()
    frame_supports = tuple(
        FiniteInterval(
            max(
                lane.width_authority_px.minimum,
                reference.minimum - frame_width.maximum / 2.0,
            ),
            min(
                lane.width_authority_px.maximum,
                reference.maximum + frame_width.maximum / 2.0,
            ),
        )
        for reference in frame_reference_intervals_px
    )
    # A top/bottom family becomes lane-level authority through repeated,
    # spatially independent trace support when the observation is built.  Its
    # directly measured segments do not also need to overlap two different
    # photo slots.  Requiring that second condition rejects a valid continuous
    # film edge merely because both observed segments happen to lie over one
    # frame; outside local support the same fitted family remains inferred
    # safety evidence, never an additional direct vote.
    measurement_by_role = {
        BoundaryRole.TOP: lane.top_measurement_set,
        BoundaryRole.BOTTOM: lane.bottom_measurement_set,
    }

    def local_cross_projection(
        run: ProfileRun,
        role: BoundaryRole,
        support: FiniteInterval,
        reference: float,
        observed_direction_interval_degrees: FiniteInterval,
        observed_canonical_direction_degrees: float,
    ) -> BoundRunProjection | None:
        measurement = measurement_by_role[role]
        queried = tuple(
            trace
            for trace in measurement.query.trace_positions_px
            if support.contains(
                float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
            )
        )
        owned = {str(identity) for identity in run.transition_ids}
        local_transitions = tuple(
            transition
            for transition in measurement.transitions
            if str(transition.transition_id) in owned
            and support.contains(
                float(transition.trace_coordinate_px),
                epsilon=PIXEL_CENTER_HALF_EXTENT_PX,
            )
        )
        traces = tuple(
            sorted({item.trace_coordinate_px for item in local_transitions})
        )
        if not queried or not local_transitions:
            return None
        local_run = ProfileRun(
            run_id=physical_fact_id(
                "slot-local-cross-run",
                run.run_id,
                support.minimum,
                support.maximum,
                *(str(item.transition_id) for item in local_transitions),
            ),
            coordinate_interval_px=run.coordinate_interval_px,
            transition_ids=tuple(
                item.transition_id for item in local_transitions
            ),
            trace_coordinates_px=traces,
            role_hint=role,
            qualified_anchor_roles=(role,),
            support_fraction=len(traces) / len(queried),
            continuous_support_fraction=continuous_trace_support_fraction(
                queried,
                traces,
                spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            ),
            fit_residual_px=run.fit_residual_px,
            evidence_strength=run.evidence_strength,
            pair_qualified=True,
        )
        return project_profile_run(
            local_run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.height_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=reference,
            boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
            observed_direction_interval_degrees=(
                observed_direction_interval_degrees
            ),
            observed_canonical_direction_degrees=(
                observed_canonical_direction_degrees
            ),
            projection_cache=projection_cache,
        )

    selected_top: list[FiniteInterval] = []
    selected_bottom: list[FiniteInterval] = []
    top_boundary_safety: list[FiniteInterval] = []
    bottom_boundary_safety: list[FiniteInterval] = []

    for index, (reference, support) in enumerate(
        zip(frame_reference_traces_px, frame_supports, strict=True)
    ):
        top_safe = FiniteInterval.exact(top_canonical[index])
        bottom_safe = FiniteInterval.exact(bottom_canonical[index])
        top_safety_values = [FiniteInterval.exact(top_canonical[index])]
        bottom_safety_values = [FiniteInterval.exact(bottom_canonical[index])]
        top_direct = False
        bottom_direct = False
        if (run := observed_runs.get(BoundaryRole.TOP)) is not None:
            observation = observation_by_role[BoundaryRole.TOP]
            projected_family = project_profile_run(
                run,
                transitions=lane.transition_by_id,
                direction=direction,
                boundary_axis=lane.height_axis,
                source_width_axis=lane.width_axis,
                reference_trace_px=reference,
                boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                observed_direction_interval_degrees=(
                    observation_direction_by_role[BoundaryRole.TOP][0]
                ),
                observed_canonical_direction_degrees=(
                    observation_direction_by_role[BoundaryRole.TOP][1]
                ),
                projection_cache=projection_cache,
            )
            # Once repeated regions establish a source-level edge family, its
            # projected line remains inferred safety evidence outside the
            # locally observed support.  Only local support grants a direct
            # role or phase authority.  Safety consumes the measurement's
            # physical interval, not only its fitted centre: otherwise a
            # precise fit of a wide observed transition can still cut the
            # transition itself.
            top_direct = intersect(
                support,
                observation.line.support_projection_px,
            ) is not None
            if top_direct:
                top_safe = hull(
                    (top_safe, projected_family.fit_position_interval_px)
                )
            projected = local_cross_projection(
                run,
                BoundaryRole.TOP,
                support,
                reference,
                observation_direction_by_role[BoundaryRole.TOP][0],
                observation_direction_by_role[BoundaryRole.TOP][1],
            )
            top_safety_values.append(
                (
                    projected.full_position_interval_px
                    if projected is not None
                    else projected_family.full_position_interval_px
                )
            )
        if (run := observed_runs.get(BoundaryRole.BOTTOM)) is not None:
            observation = observation_by_role[BoundaryRole.BOTTOM]
            projected_family = project_profile_run(
                run,
                transitions=lane.transition_by_id,
                direction=direction,
                boundary_axis=lane.height_axis,
                source_width_axis=lane.width_axis,
                reference_trace_px=reference,
                boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                observed_direction_interval_degrees=(
                    observation_direction_by_role[BoundaryRole.BOTTOM][0]
                ),
                observed_canonical_direction_degrees=(
                    observation_direction_by_role[BoundaryRole.BOTTOM][1]
                ),
                projection_cache=projection_cache,
            )
            bottom_direct = intersect(
                support,
                observation.line.support_projection_px,
            ) is not None
            if bottom_direct:
                bottom_safe = hull(
                    (bottom_safe, projected_family.fit_position_interval_px)
                )
            projected = local_cross_projection(
                run,
                BoundaryRole.BOTTOM,
                support,
                reference,
                observation_direction_by_role[BoundaryRole.BOTTOM][0],
                observation_direction_by_role[BoundaryRole.BOTTOM][1],
            )
            bottom_safety_values.append(
                (
                    projected.full_position_interval_px
                    if projected is not None
                    else projected_family.full_position_interval_px
                )
            )
        selected_top.append(top_safe)
        selected_bottom.append(bottom_safe)
        top_boundary_safety.append(hull(tuple(top_safety_values)))
        bottom_boundary_safety.append(hull(tuple(bottom_safety_values)))

    selected_top = [
        hull((placement, boundary))
        for placement, boundary in zip(
            selected_top,
            top_boundary_safety,
            strict=True,
        )
    ]
    selected_bottom = [
        hull((placement, boundary))
        for placement, boundary in zip(
            selected_bottom,
            bottom_boundary_safety,
            strict=True,
        )
    ]
    top_fit = list(selected_top)
    top_full = list(selected_top)
    bottom_fit = list(selected_bottom)
    bottom_full = list(selected_bottom)
    return CrossPlacement(
        placement_id=physical_fact_id(
            "cross-placement",
            cross_proposal.cross_proposal_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        cross_proposal_id=cross_proposal.cross_proposal_id,
        source_scan_geometry_id=geometry.geometry_id,
        lane_reference_trace_px=lane_reference,
        frame_reference_traces_px=frame_reference_traces_px,
        top_canonical_positions_px=tuple(top_canonical),
        bottom_canonical_positions_px=tuple(bottom_canonical),
        top_fit_positions_px=tuple(top_fit),
        bottom_fit_positions_px=tuple(bottom_fit),
        top_full_positions_px=tuple(top_full),
        bottom_full_positions_px=tuple(bottom_full),
        evidence=tuple(
            CrossRoleEvidence(
                role=role,
                run_id=run.run_id,
                observation=observation_by_role[role],
                canonical_position_at_lane_reference_px=(
                    lane_projections[role].canonical_position_px
                ),
                fit_position_at_lane_reference_px=(
                    lane_projections[role].fit_position_interval_px
                ),
                full_position_at_lane_reference_px=(
                    lane_projections[role].full_position_interval_px
                ),
            )
            for role, run in observed_runs.items()
        ),
        direct_height_span_validated=(
            cross_proposal.direct_height_span_validated
        ),
    )
