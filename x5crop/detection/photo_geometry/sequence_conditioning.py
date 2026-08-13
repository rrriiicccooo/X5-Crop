"""Condition one sequence seed on every directly measured role."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval, ObservationId
from .boundary_geometry import canonical_source_sequence_axis_slope
from .boundary_projection import BoundRunProjection
from .chain_proposals import (
    FrameChainProposals,
    LaneObservationInput,
    SequenceChainProposal,
)
from .chains import BoundRoleEvidence
from .interval_math import add, common, hull, intersect, multiply, subtract
from .local_advance import (
    gap_model_from_bound_roles,
    local_advance_relations,
    merge_local_advance_relations,
)
from .model import BoundaryRole
from .output_model import SharedStripDirection
from .sequence_evidence import (
    materialized_role_evidence,
    role_evidence_intervals,
)
from .sequence_models import LocalAdvanceRelation
from .sequence_role_proposals import role_relative_projection
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry


RoleEvidenceIntervals = dict[
    int,
    tuple[FiniteInterval, FiniteInterval, tuple[ObservationId, ...]],
]


@dataclass(frozen=True)
class ConditionedSequenceEvidence:
    observations: tuple[BoundRoleEvidence, ...]
    gap_model: LaneGapModel
    relations: tuple[LocalAdvanceRelation, ...]
    phase_fit: FiniteInterval
    phase_full: FiniteInterval
    by_role: RoleEvidenceIntervals
    role_fit_direction_intervals: tuple[FiniteInterval, ...]
    role_full_direction_intervals: tuple[FiniteInterval, ...]
    role_direction_displacements_px: tuple[float, ...]
    conditioned_full_positions_px: tuple[FiniteInterval, ...]


def condition_sequence_evidence(
    lane: LaneObservationInput,
    proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
    evidence_cache: dict[tuple[str, str, int], BoundRoleEvidence] | None,
) -> ConditionedSequenceEvidence:
    anchor_observations = materialized_role_evidence(
        lane,
        seed.role_proposals,
        direction,
        projection_cache,
        evidence_cache,
    )
    if not anchor_observations:
        raise ValueError("sequence placement has no absolute pixel anchor")
    observations = tuple(
        sorted(
            materialized_role_evidence(
                lane,
                seed.local_advance_proposals,
                direction,
                projection_cache,
                evidence_cache,
            ),
            key=lambda item: (item.role.role_index, item.run_id),
        )
    )
    gap_model = gap_model_from_bound_roles(
        proposal,
        geometry,
        lane.lane_id,
        observations,
        seed.local_advance_proposals,
    )
    relations = merge_local_advance_relations(
        seed.local_advance_relations,
        local_advance_relations(
            proposal,
            geometry,
            gap_model,
            observations,
            seed.local_advance_proposals,
        ),
    )
    prefix_intervals = [FiniteInterval.exact(0.0)]
    for relation in relations:
        prefix_intervals.append(
            add(prefix_intervals[-1], relation.delta_interval_px)
        )

    fit_phases: list[FiniteInterval] = []
    full_phases: list[FiniteInterval] = []
    for observation in anchor_observations:
        relative = role_relative_projection(
            observation.role,
            proposal.frame_spec,
            geometry.width_state,
            gap_model,
        )
        prefix = prefix_intervals[observation.role.lane_ordinal - 1]
        fit_phases.append(
            subtract(
                subtract(observation.fit_position_interval_px, relative),
                prefix,
            )
        )
        full_phases.append(
            subtract(
                subtract(observation.full_position_interval_px, relative),
                prefix,
            )
        )
    phase_fit = common(tuple(fit_phases))
    phase_full = common(tuple(full_phases))
    if phase_fit is None or phase_full is None:
        raise ValueError("cross_proposal-bound observations disagree on phase")
    phase_full = hull((phase_full, phase_fit))

    by_role = role_evidence_intervals(observations)
    edge_by_run_id = {edge.run_id: edge for edge in lane.sequence_edges}
    full_positions: list[FiniteInterval] = []
    role_fit_directions: list[FiniteInterval] = []
    role_full_directions: list[FiniteInterval] = []
    role_direction_displacements: list[float] = []
    canonical_sequence_slope = canonical_source_sequence_axis_slope(
        direction,
        lane.width_axis,
    )
    transverse_radius = max(
        abs(lane.height_authority_px.minimum - lane.height_authority_px.center),
        abs(lane.height_authority_px.maximum - lane.height_authority_px.center),
    )
    for role in proposal.roles:
        prefix = prefix_intervals[role.lane_ordinal - 1]
        relative = role_relative_projection(
            role,
            proposal.frame_spec,
            geometry.width_state,
            gap_model,
        )
        fit = add(add(phase_fit, relative), prefix)
        full = add(add(phase_full, relative), prefix)
        observed = by_role.get(role.role_index)
        if observed is not None:
            fit_intersection = intersect(fit, observed[0])
            full_intersection = intersect(full, observed[1])
            if full_intersection is None:
                raise ValueError(
                    "observed role contradicts propagated chain"
                )
            fit = fit_intersection or full_intersection
            full = hull((fit, full_intersection))
        role_observations = tuple(
            item
            for item in observations
            if item.role.role_index == role.role_index
        )
        observed_canonical_slopes = tuple(
            -math.tan(math.radians(edge.canonical_direction_degrees))
            for item in role_observations
            for edge in (edge_by_run_id.get(item.run_id),)
            if edge is not None
            and edge.canonical_direction_degrees is not None
        )
        direction_displacement = max(
            (
                abs(value - canonical_sequence_slope)
                for value in observed_canonical_slopes
            ),
            default=0.0,
        ) * transverse_radius
        role_direction_displacements.append(direction_displacement)
        full_positions.append(
            hull(
                (
                    fit,
                    FiniteInterval(
                        full.minimum - direction_displacement,
                        full.maximum + direction_displacement,
                    ),
                )
            )
        )
        direction_interval = direction.full_angle_interval_degrees
        role_fit_directions.append(
            hull(
                tuple(
                    item.fit_direction_interval_degrees
                    for item in role_observations
                )
            )
            if role_observations
            else direction_interval
        )
        role_full_directions.append(
            hull(
                tuple(
                    item.full_direction_interval_degrees
                    for item in role_observations
                )
            )
            if role_observations
            else direction_interval
        )

    width_interval = geometry.width_state.extent_projection_px()
    pitch_interval = (
        gap_model.placement_pitch_interval_px
        if gap_model.placement_pitch_interval_px is not None
        else width_interval
    )
    conditioned_full: list[FiniteInterval] = []
    for role_index, target_role in enumerate(proposal.roles):
        target_prefix = prefix_intervals[target_role.lane_ordinal - 1]
        constraints = [full_positions[role_index]]
        for observation in observations:
            anchor_prefix = prefix_intervals[
                observation.role.lane_ordinal - 1
            ]
            ordinal_delta = (
                target_role.lane_ordinal
                - observation.role.lane_ordinal
            )
            width_coefficient = int(
                target_role.role == BoundaryRole.END
            ) - int(observation.role.role == BoundaryRole.END)
            constraints.append(
                add(
                    add(
                        add(
                            observation.full_position_interval_px,
                            multiply(pitch_interval, ordinal_delta),
                        ),
                        multiply(width_interval, width_coefficient),
                    ),
                    subtract(target_prefix, anchor_prefix),
                )
            )
        common_constraint = common(tuple(constraints))
        if common_constraint is None:
            raise ValueError(
                "direct sequence anchors have no common placement"
            )
        conditioned_full.append(common_constraint)

    return ConditionedSequenceEvidence(
        observations=observations,
        gap_model=gap_model,
        relations=relations,
        phase_fit=phase_fit,
        phase_full=phase_full,
        by_role=by_role,
        role_fit_direction_intervals=tuple(role_fit_directions),
        role_full_direction_intervals=tuple(role_full_directions),
        role_direction_displacements_px=tuple(role_direction_displacements),
        conditioned_full_positions_px=tuple(conditioned_full),
    )
