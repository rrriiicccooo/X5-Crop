"""Role evidence and source geometry refinement for sequence chains."""

from __future__ import annotations

from ...domain import FiniteInterval, ObservationId
from .boundary_projection import BoundRunProjection, project_profile_run
from .chains import (
    BoundRoleEvidence,
    SequencePlacement,
)
from .chain_proposals import (
    CrossAxisProposal,
    FrameChainProposals,
    LaneObservationInput,
)
from .interval_math import common, hull, intersect, subtract
from .model import BoundaryRole
from .output_model import SharedStripDirection
from .observation_types import SequenceRoleProposal
from .source_geometry import SourceScanGeometry

def materialized_role_evidence(
    lane: LaneObservationInput,
    proposals: tuple[SequenceRoleProposal, ...],
    direction: SharedStripDirection,
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
    evidence_cache: dict[tuple[str, str, int], BoundRoleEvidence] | None = None,
) -> tuple[BoundRoleEvidence, ...]:
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    edge_by_run = {edge.run_id: edge for edge in lane.sequence_edges}
    values: list[BoundRoleEvidence] = []
    for proposal in proposals:
        cache_key = (
            direction.direction_id,
            proposal.proposal_id,
            proposal.role.role_index,
        )
        if evidence_cache is not None and cache_key in evidence_cache:
            values.append(evidence_cache[cache_key])
            continue
        run = run_by_id[proposal.run_id]
        edge = edge_by_run.get(run.run_id)
        if edge is None:
            raise ValueError(
                "sequence role proposal has no boundary edge observation"
            )
        if (
            proposal.separator_band_observation_id is None
            and edge.fit_direction_interval_degrees is not None
        ):
            # An isolated start/end must belong to the shared perpendicular
            # direction family, not merely be a peak at a convenient
            # coordinate.  A complete separator band is different: its two
            # material-bound sides and cross-axis continuity already establish
            # the adjacency.  Real camera advance can leave that divider
            # slightly non-orthogonal to the film edge, so its local fitted
            # angle cannot veto the band.  Projection through the selected
            # lane direction retains the resulting positional uncertainty,
            # which the selected-only envelope and direct-use budget inspect.
            outer_role = proposal.role.role_index in {
                0,
                lane.output_slot_count * 2 - 1,
            }
            direction_authority = (
                edge.full_direction_interval_degrees
                if outer_role
                else edge.fit_direction_interval_degrees
            )
            if (
                direction_authority is not None
                and intersect(
                    direction_authority,
                    direction.full_angle_interval_degrees,
                )
                is None
            ):
                continue
        projection = project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
            observed_direction_interval_degrees=(
                edge.fit_direction_interval_degrees
            ),
            observed_canonical_direction_degrees=(
                edge.canonical_direction_degrees
            ),
            preserve_transition_extent=(
                proposal.separator_band_observation_id is None
                and proposal.role.role_index
                in {0, lane.output_slot_count * 2 - 1}
            ),
            projection_cache=projection_cache,
        )
        safety_projection = (
            project_profile_run(
                run,
                transitions=lane.transition_by_id,
                direction=direction,
                boundary_axis=lane.width_axis,
                source_width_axis=lane.width_axis,
                reference_trace_px=lane.height_authority_px.center,
                boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
                observed_direction_interval_degrees=(
                    edge.fit_direction_interval_degrees
                ),
                observed_canonical_direction_degrees=(
                    edge.canonical_direction_degrees
                ),
                preserve_transition_extent=True,
                projection_cache=projection_cache,
            )
            if proposal.separator_band_observation_id is not None
            else projection
        )
        evidence = BoundRoleEvidence(
                role=proposal.role,
                run_id=run.run_id,
                observation_id=(
                    edge.observation_id
                ),
                canonical_position_px=projection.canonical_position_px,
                fit_position_interval_px=projection.fit_position_interval_px,
                full_position_interval_px=projection.full_position_interval_px,
                safety_position_interval_px=(
                    safety_projection.full_position_interval_px
                ),
                transition_ids=run.transition_ids,
                support_fraction=run.support_fraction,
                continuous_support_fraction=run.continuous_support_fraction,
                fit_residual_px=run.fit_residual_px,
                fit_direction_interval_degrees=(
                    direction.full_angle_interval_degrees
                    if edge.fit_direction_interval_degrees is None
                    else edge.fit_direction_interval_degrees
                ),
                full_direction_interval_degrees=(
                    direction.full_angle_interval_degrees
                    if edge.full_direction_interval_degrees is None
                    else edge.full_direction_interval_degrees
                ),
            )
        if evidence_cache is not None:
            evidence_cache[cache_key] = evidence
        values.append(evidence)
    return tuple(
        sorted(values, key=lambda item: (item.role.role_index, item.run_id))
    )


def role_evidence_intervals(
    observations: tuple[BoundRoleEvidence, ...],
) -> dict[int, tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]]]:
    by_role: dict[int, list[BoundRoleEvidence]] = {}
    for observation in observations:
        by_role.setdefault(observation.role.role_index, []).append(observation)
    result = {}
    for role_index, values in by_role.items():
        fit = common(tuple(item.fit_position_interval_px for item in values))
        full = common(tuple(item.full_position_interval_px for item in values))
        if fit is None or full is None:
            continue
        result[role_index] = (
            fit,
            hull((fit, full)),
            tuple(
                ObservationId(identity)
                for identity in sorted(
                    {
                        str(transition_id)
                        for item in values
                        for transition_id in item.transition_ids
                    }
                )
            ),
        )
    return result


def common_extent_constraint(
    constraints: tuple[tuple[FiniteInterval, tuple[ObservationId, ...]], ...],
) -> tuple[FiniteInterval, tuple[ObservationId, ...]] | None:
    if not constraints:
        return None
    common_constraint = common(tuple(item[0] for item in constraints))
    if common_constraint is None:
        return None
    identities = tuple(
        ObservationId(value)
        for value in sorted(
            {
                str(identity)
                for _interval, values in constraints
                for identity in values
            }
        )
    )
    return common_constraint, identities


def refine_width_from_role_evidence(
    geometry: SourceScanGeometry,
    observations: tuple[BoundRoleEvidence, ...],
    *,
    slot_count: int,
) -> SourceScanGeometry:
    """Tighten the source-shared W from directly bounded complete frames."""

    by_role = role_evidence_intervals(observations)
    internal_ordinals = tuple(range(2, slot_count))
    measured_ordinals = internal_ordinals or tuple(range(1, slot_count + 1))
    constraints: list[tuple[FiniteInterval, tuple[ObservationId, ...]]] = []
    for ordinal in measured_ordinals:
        start = by_role.get((ordinal - 1) * 2)
        end = by_role.get((ordinal - 1) * 2 + 1)
        if start is None or end is None:
            continue
        constraints.append(
            (
                # W is a physical opposite-edge span.  Peak-localization
                # centres on the two material transitions can both sit toward
                # the photo interior and would systematically shrink the
                # source-wide width.  The complete measured position
                # intervals already carry the boundary uncertainty needed for
                # this validation.
                subtract(end[1], start[1]),
                tuple(
                    ObservationId(value)
                    for value in sorted(
                        {
                            *(str(identity) for identity in start[2]),
                            *(str(identity) for identity in end[2]),
                        }
                    )
                ),
            )
        )
    if not constraints:
        return geometry
    common = common_extent_constraint(tuple(constraints))
    if common is None:
        raise ValueError("direct complete-frame widths disagree")
    width_state = geometry.width_state.intersect_observed_extent(
        common[0],
        observation_ids=common[1],
    )
    return SourceScanGeometry.from_axis_states(
        geometry.frame_spec,
        width_state,
        geometry.height_state,
    )


def refine_width_from_complete_sequence(
    geometry: SourceScanGeometry,
    sequence: SequencePlacement,
) -> SourceScanGeometry:
    return refine_width_from_role_evidence(
        geometry,
        sequence.observations,
        slot_count=len(sequence.roles) // 2,
    )


def refine_source_geometry(
    lane: LaneObservationInput,
    proposal: FrameChainProposals,
    direction: SharedStripDirection,
    compatible_cross_proposals: tuple[CrossAxisProposal, ...],
    *,
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
) -> SourceScanGeometry:
    geometry = proposal.initial_source_scan_geometry
    width_state = geometry.width_state
    # Sequence proposals have not yet established a complete fixed-frame
    # chain.  Refining W from one provisional role pair here made the result
    # order-dependent and let an early internal line poison every later seed.
    # W is validated once, after complete-chain role binding, by
    # ``refine_width_from_complete_sequence``.
    height_state = geometry.height_state
    for cross_proposal in compatible_cross_proposals:
        run_by_role = {
            run.role_hint: run
            for run in cross_proposal.observed_runs
            if run.role_hint in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        }
        observation_by_role = {
            observation.role: observation
            for observation in cross_proposal.raw_observations
        }
        if not cross_proposal.direct_height_span_validated:
            # A single directly observed side localizes the fixed-H rectangle
            # through the centred search prior.  Two visible safety limits may
            # also protect both sides without measuring one camera-aperture H.
            # Only an authorized opposite-edge span can recalibrate height.
            continue
        support = intersect(
            observation_by_role[BoundaryRole.TOP].line.support_projection_px,
            observation_by_role[BoundaryRole.BOTTOM].line.support_projection_px,
        )
        if support is None:
            continue
        reference_trace = support.center
        try:
            projected = {
                role: project_profile_run(
                    run_by_role[role],
                    transitions=lane.transition_by_id,
                    direction=direction,
                    boundary_axis=lane.height_axis,
                    source_width_axis=lane.width_axis,
                    reference_trace_px=reference_trace,
                    boundary_scale_px_per_mm=lane.height_scale_px_per_mm,
                    projection_cache=projection_cache,
                )
                for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM)
            }
            observed_extent = subtract(
                projected[BoundaryRole.BOTTOM].fit_position_interval_px,
                projected[BoundaryRole.TOP].fit_position_interval_px,
            )
            observation_ids = tuple(
                ObservationId(value)
                for value in sorted(
                    {
                        *(
                            str(identity)
                            for identity in run_by_role[
                                BoundaryRole.TOP
                            ].transition_ids
                        ),
                        *(
                            str(identity)
                            for identity in run_by_role[
                                BoundaryRole.BOTTOM
                            ].transition_ids
                        ),
                    }
                )
            )
            candidate = height_state.intersect_observed_extent(
                observed_extent,
                observation_ids=observation_ids,
            )
        except ValueError:
            # A holder/film edge can be a safe visible boundary without being
            # the photo edge.  Such an incompatible line may not recalibrate
            # H, but it remains available to the selected safety envelope.
            continue
        try:
            # Both W_px and H_px are source-level states.  The constructor
            # verifies their common holder origin without allowing one observed
            # photo dimension to recalibrate the other.
            SourceScanGeometry.from_axis_states(
                proposal.frame_spec,
                width_state,
                candidate,
            )
        except ValueError:
            continue
        height_state = candidate

    return SourceScanGeometry.from_axis_states(
        proposal.frame_spec,
        width_state,
        height_state,
    )
