"""Assemble finite sequence materialization seeds."""

from __future__ import annotations

from dataclasses import replace

from ...domain import FiniteInterval
from .boundary_projection import BoundRunProjection, project_profile_run
from .chain_proposals import (
    FrameChainProposals,
    LanePhysicalProposals,
    SequenceChainProposal,
)
from .interval_math import add, common, intersect, subtract
from .sequence_chain_builder import build_sequence_chain_proposals
from .observation_types import (
    SeparatorBandRoleProposal,
    SequenceRoleProposal,
)
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id
from .sequence_grouping import (
    build_separator_band_groups,
    group_support_exclusion_authorized,
)
from .sequence_outer_seeds import outer_edge_seed_variants
from .sequence_role_proposals import role_relative_projection
from .sequence_separator_seeds import direct_separator_groups
from .sequence_models import SequenceDiscoveryKind


def visible_normal_phase_authority(
    *,
    width_authority_px: FiniteInterval,
    width_interval_px: FiniteInterval,
    pitch_interval_px: FiniteInterval,
    output_slot_count: int,
) -> FiniteInterval | None:
    """Return the phase range whose normal chain can intersect lane authority."""

    if output_slot_count <= 0:
        raise ValueError("visible phase authority requires a positive slot count")
    minimum = width_authority_px.minimum - width_interval_px.maximum
    maximum = (
        width_authority_px.maximum
        - (output_slot_count - 1) * pitch_interval_px.minimum
    )
    return None if maximum < minimum else FiniteInterval(minimum, maximum)


def frame_spec_materialization_seeds(
    proposal: LanePhysicalProposals,
    frame_spec: FrameChainProposals,
    direction: SharedStripDirection,
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
) -> tuple[SequenceChainProposal, ...]:
    run_by_id = {
        run.run_id: run for run in proposal.lane.sequence_profile.runs
    }
    edge_by_run = {
        edge.run_id: edge for edge in proposal.lane.sequence_edges
    }
    if frame_spec.separator_band_proposals:
        compatible_bands: list[SeparatorBandRoleProposal] = []
        fit_position_by_run: dict[str, FiniteInterval] = {}
        for band in frame_spec.separator_band_proposals:
            roles: list[SequenceRoleProposal] = []
            for role_index, role in enumerate(
                (
                    band.left_role_proposal,
                    band.right_role_proposal,
                )
            ):
                run = run_by_id[role.run_id]
                edge = edge_by_run.get(run.run_id)
                projection = project_profile_run(
                    run,
                    transitions=proposal.lane.transition_by_id,
                    direction=direction,
                    boundary_axis=proposal.lane.width_axis,
                    source_width_axis=proposal.lane.width_axis,
                    reference_trace_px=proposal.lane.height_authority_px.center,
                    boundary_scale_px_per_mm=(
                        proposal.lane.width_scale_px_per_mm
                    ),
                    observed_direction_interval_degrees=(
                        None
                        if edge is None
                        else edge.fit_direction_interval_degrees
                    ),
                    observed_canonical_direction_degrees=(
                        None
                        if edge is None
                        else edge.canonical_direction_degrees
                    ),
                    projection_cache=projection_cache,
                )
                fit_position_by_run[run.run_id] = (
                    projection.fit_position_interval_px
                )
                relative = role_relative_projection(
                    role.role,
                    frame_spec.frame_spec,
                    frame_spec.initial_source_scan_geometry.width_state,
                )
                if role_index == 1:
                    relative = add(relative, band.gap_interval_px)
                roles.append(
                    replace(
                        role,
                        phase_interval_px=subtract(
                            projection.fit_position_interval_px,
                            relative,
                        ),
                    )
                )
            phase = intersect(
                roles[0].phase_interval_px,
                roles[1].phase_interval_px,
            )
            if phase is None:
                continue
            compatible_bands.append(
                replace(
                    band,
                    phase_interval_px=phase,
                    left_role_proposal=roles[0],
                    right_role_proposal=roles[1],
                )
            )
        compatible_band_values = tuple(compatible_bands)
        if frame_spec.discovery_kind == SequenceDiscoveryKind.DIRECT_EXCEPTION:
            direct_groups = direct_separator_groups(
                compatible_band_values,
                relation_count=proposal.lane.output_slot_count - 1,
                width_interval_px=(
                    frame_spec.initial_source_scan_geometry
                    .width_state.extent_projection_px()
                ),
                canonical_width_px=(
                    frame_spec.initial_source_scan_geometry
                    .width_state.canonical_state()[1]
                ),
                fit_position_by_run=fit_position_by_run,
            )
            direct_seeds = (
                tuple(
                    replace(
                        seed,
                        chain_proposal_id=physical_fact_id(
                            "direct-separator-chain-proposal",
                            seed.chain_proposal_id,
                            direction.direction_id,
                            seed.base_phase_interval_px,
                        ),
                    )
                    for seed in build_sequence_chain_proposals(
                        replace(
                            frame_spec,
                            role_proposals=tuple(
                                role
                                for group in direct_groups
                                for role in group.role_proposals
                            ),
                            separator_band_proposals=tuple(
                                band
                                for group in direct_groups
                                for band in group.separator_band_proposals
                            ),
                            sequence_groups=direct_groups,
                        )
                    )
                )
                if direct_groups
                else ()
            )
            unique = {
                seed.chain_proposal_id: seed for seed in direct_seeds
            }
            # A complete separator path already fixes every adjacency and the
            # absolute phase.  Creating first/last-edge variants here would
            # multiply one physical path by unrelated optional observations
            # before the chain has been selected.  Outer edges remain ordinary
            # observations and may constrain safety later; they do not create
            # alternate direct-separator chains.
            return tuple(unique[key] for key in sorted(unique))

        groups, _work = build_separator_band_groups(
            compatible_band_values,
            relation_count=proposal.lane.output_slot_count - 1,
        )
        width = (
            frame_spec.initial_source_scan_geometry
            .width_state.extent_projection_px()
        )
        minimum_direct_bands = min(
            2,
            proposal.lane.output_slot_count - 1,
        )
        visible_groups = []
        for group in groups:
            if len(group.separator_band_proposals) < minimum_direct_bands:
                continue
            # This bound is placement authority only because every retained
            # group carries the directly observed separator gap(s) used below.
            # G_format never participates.  For count=2 the sole band already
            # fixes both frames; for larger counts two compatible bands are the
            # minimum evidence that establishes the group's normal gap.
            observed_gap = common(
                tuple(
                    band.gap_interval_px
                    for band in group.separator_band_proposals
                )
            )
            if observed_gap is None:
                continue
            pitch = add(width, observed_gap)
            visible_phase = visible_normal_phase_authority(
                width_authority_px=proposal.lane.width_authority_px,
                width_interval_px=width,
                pitch_interval_px=pitch,
                output_slot_count=proposal.lane.output_slot_count,
            )
            if visible_phase is None:
                continue
            phase = intersect(group.phase_interval_px, visible_phase)
            if phase is not None:
                visible_groups.append(
                    replace(group, phase_interval_px=phase)
                )
        groups = tuple(visible_groups)
        if not groups:
            return ()
        seeds = tuple(
            replace(
                seed,
                chain_proposal_id=physical_fact_id(
                    "separator-chain-proposal",
                    seed.chain_proposal_id,
                    direction.direction_id,
                    seed.base_phase_interval_px,
                ),
            )
            for seed in build_sequence_chain_proposals(
                replace(
                    frame_spec,
                    separator_band_proposals=compatible_band_values,
                    role_proposals=tuple(
                        role
                        for band in compatible_band_values
                        for role in (
                            band.left_role_proposal,
                            band.right_role_proposal,
                        )
                    ),
                    sequence_groups=groups,
                )
            )
        )
        # Two compatible role-bound bands establish G_source and phase.  A
        # merely compatible outer line did not participate in that solve and
        # must not multiply the chain or gain a direct vote after the fact.
        # It remains in the observation index for explicit accounting.
        return seeds

    values: list[SequenceChainProposal] = []
    frame_width_lower = (
        frame_spec.initial_source_scan_geometry
        .width_state.extent_projection_px().minimum
    )
    for seed in build_sequence_chain_proposals(frame_spec):
        compatible = seed.local_advance_proposals
        if not compatible:
            continue
        by_run: dict[str, list[SequenceRoleProposal]] = {}
        by_role: dict[int, list[SequenceRoleProposal]] = {}
        for item in compatible:
            by_run.setdefault(item.run_id, []).append(item)
            by_role.setdefault(item.role.role_index, []).append(item)
        # One raw edge cannot own two roles and one role cannot silently pick
        # one of several competing edges.  The previous nearest-phase choice
        # converted the group's provisional center into placement authority.
        # Ambiguous groups remain unresolved here; a separate physical group
        # must establish each alternative before materialization.
        if any(len(items) != 1 for items in (*by_run.values(), *by_role.values())):
            continue
        phase = common(tuple(item.phase_interval_px for item in compatible))
        if phase is None:
            continue
        exclusion = group_support_exclusion_authorized(
            role_coordinates_px=tuple(
                item.role_coordinate_px for item in compatible
            ),
            role_identities=tuple(
                (item.role.lane_ordinal, item.role.role)
                for item in compatible
            ),
            transition_id_sets=tuple(
                item.transition_ids for item in compatible
            ),
            frame_width_lower_px=frame_width_lower,
        )
        if not exclusion:
            continue
        values.append(
            replace(
                seed,
                chain_proposal_id=physical_fact_id(
                    "sequence-chain-proposal",
                    seed.chain_proposal_id,
                    direction.direction_id,
                    *(item.proposal_id for item in compatible),
                    phase,
                ),
                base_phase_interval_px=phase,
                role_proposals=compatible,
                local_advance_proposals=compatible,
                exclusion_authorized=True,
            )
        )
    unique = {item.chain_proposal_id: item for item in values}
    return outer_edge_seed_variants(
        proposal,
        frame_spec,
        direction,
        tuple(unique[key] for key in sorted(unique)),
        projection_cache,
    )
