"""Bind finite first/last outer-edge alternatives to sequence seeds."""

from __future__ import annotations

from dataclasses import replace

from .boundary_projection import BoundRunProjection, project_profile_run
from .chain_proposals import (
    FrameChainProposals,
    LanePhysicalProposals,
    SequenceChainProposal,
)
from .interval_math import intersect, subtract
from .model import BoundaryRole
from .observation_types import ProfileRun, SequenceRoleProposal
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id
from .sequence_role_proposals import (
    role_canonical_relative,
    role_relative_projection,
)


def outer_edge_seed_variants(
    proposal: LanePhysicalProposals,
    frame_spec: FrameChainProposals,
    direction: SharedStripDirection,
    seeds: tuple[SequenceChainProposal, ...],
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
) -> tuple[SequenceChainProposal, ...]:
    """Materialize every fixed-W-compatible first/last edge alternative."""

    lane = proposal.lane
    run_by_id = {run.run_id: run for run in lane.sequence_profile.runs}
    edge_by_run = {edge.run_id: edge for edge in lane.sequence_edges}
    width = (
        frame_spec.initial_source_scan_geometry
        .width_state.extent_projection_px()
    )
    local_projections: dict[str, BoundRunProjection] = {}

    def projection(run: ProfileRun) -> BoundRunProjection:
        cached = local_projections.get(run.run_id)
        if cached is not None:
            return cached
        edge = edge_by_run.get(run.run_id)
        value = project_profile_run(
            run,
            transitions=lane.transition_by_id,
            direction=direction,
            boundary_axis=lane.width_axis,
            source_width_axis=lane.width_axis,
            reference_trace_px=lane.height_authority_px.center,
            boundary_scale_px_per_mm=lane.width_scale_px_per_mm,
            observed_direction_interval_degrees=(
                None if edge is None else edge.fit_direction_interval_degrees
            ),
            observed_canonical_direction_degrees=(
                None if edge is None else edge.canonical_direction_degrees
            ),
            projection_cache=projection_cache,
        )
        local_projections[run.run_id] = value
        return value

    variants: list[SequenceChainProposal] = []
    outer_roles = (
        (frame_spec.roles[0], 1),
        (frame_spec.roles[-1], len(frame_spec.roles) - 2),
    )
    for seed in seeds:
        used_run_ids = {item.run_id for item in seed.local_advance_proposals}
        choices: list[tuple[SequenceRoleProposal | None, ...]] = []
        for role, opposite_role_index in outer_roles:
            if any(
                item.role.role_index == role.role_index
                for item in seed.local_advance_proposals
            ):
                choices.append((None,))
                continue
            opposite_runs = tuple(
                run_by_id[item.run_id]
                for item in seed.local_advance_proposals
                if item.role.role_index == opposite_role_index
            )
            opposite_intervals = tuple(
                projection(run).fit_position_interval_px
                for run in opposite_runs
            )
            compatible: list[SequenceRoleProposal] = []
            for run in lane.sequence_profile.runs:
                if not run.pair_qualified or run.run_id in used_run_ids:
                    continue
                projected = projection(run).fit_position_interval_px
                if not any(
                    intersect(
                        (
                            subtract(opposite, projected)
                            if role.role == BoundaryRole.START
                            else subtract(projected, opposite)
                        ),
                        width,
                    )
                    is not None
                    for opposite in opposite_intervals
                ):
                    continue
                relative = role_relative_projection(
                    role,
                    frame_spec.frame_spec,
                    frame_spec.initial_source_scan_geometry.width_state,
                )
                outer_phase = subtract(projected, relative)
                compatible.append(
                    SequenceRoleProposal(
                        proposal_id=physical_fact_id(
                            "outer-opposite-edge-role",
                            run.run_id,
                            role.role_index,
                            direction.direction_id,
                            outer_phase,
                        ),
                        run_id=run.run_id,
                        role=role,
                        phase_interval_px=outer_phase,
                        transition_ids=run.transition_ids,
                        role_coordinate_px=role_canonical_relative(
                            role,
                            frame_spec.frame_spec,
                            frame_spec.initial_source_scan_geometry.width_state,
                        ),
                    )
                )
            unique = {item.proposal_id: item for item in compatible}
            choices.append(
                (None, *(unique[key] for key in sorted(unique)))
            )
        for start in choices[0]:
            for end in choices[1]:
                additions = tuple(
                    item for item in (start, end) if item is not None
                )
                variants.append(
                    replace(
                        seed,
                        chain_proposal_id=physical_fact_id(
                            "outer-edge-bound-sequence-chain-proposal",
                            seed.chain_proposal_id,
                            *(item.proposal_id for item in additions),
                        ),
                        local_advance_proposals=tuple(
                            sorted(
                                (*seed.local_advance_proposals, *additions),
                                key=lambda item: (
                                    item.role.role_index,
                                    item.proposal_id,
                                ),
                            )
                        ),
                    )
                )
    unique_variants = {item.chain_proposal_id: item for item in variants}
    return tuple(unique_variants[key] for key in sorted(unique_variants))
