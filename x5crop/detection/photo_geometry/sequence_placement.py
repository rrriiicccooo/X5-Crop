"""Materialize one fixed-format long-axis sequence placement."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval
from .boundary_projection import BoundRunProjection
from .chains import (
    BoundRoleEvidence,
    BoundSeparatorBand,
    SequencePlacement,
)
from .chain_proposals import (
    FrameChainProposals,
    LaneObservationInput,
    SequenceChainProposal,
)
from .interval_math import hull, intersect, subtract
from .holder_layout_authority import long_axis_fill_authority
from .model import BoundaryRole
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id
from .sequence_conditioning import condition_sequence_evidence
from .source_geometry import SourceScanGeometry
from .sequence_models import LocalAdvanceKind

def materialize_sequence_placement(
    lane: LaneObservationInput,
    proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    geometry: SourceScanGeometry,
    projection_cache: dict[tuple[object, ...], BoundRunProjection],
    evidence_cache: dict[tuple[str, str, int], BoundRoleEvidence] | None = None,
    *,
    bind_all_compatible_bands: bool = True,
) -> SequencePlacement:
    state = condition_sequence_evidence(
        lane,
        proposal,
        seed,
        direction,
        geometry,
        projection_cache,
        evidence_cache,
    )
    observations = state.observations
    gap_model = state.gap_model
    relations = state.relations
    phase_fit = state.phase_fit
    phase_full = state.phase_full
    by_role = state.by_role
    role_fit_direction_intervals = state.role_fit_direction_intervals
    role_full_direction_intervals = state.role_full_direction_intervals
    role_direction_displacements_px = state.role_direction_displacements_px
    conditioned_full = state.conditioned_full_positions_px

    # A seed is construction authority, not an exhaustive evidence ledger.
    # Attach every directly observed separator whose two physical sides are
    # compatible with the completed placement.  Otherwise the same real band
    # can count for one seed but be mislabeled as an internal line for an
    # equivalent seed, making selection depend on proposal construction order.
    sequence_edges_by_id = {
        edge.observation_id: edge for edge in lane.sequence_edges
    }
    observations_by_role_and_id = {
        (item.role.role_index, item.observation_id)
        for item in observations
        if item.observation_id is not None
    }
    compatible_bound_bands = tuple(
        (
            band,
            ordinal,
            left_index,
            right_index,
        )
        for band in lane.separator_bands
        for ordinal in range(1, lane.output_slot_count)
        for left_index, right_index in (
            ((ordinal - 1) * 2 + 1, ordinal * 2),
        )
        for left_edge, right_edge in (
            (
                sequence_edges_by_id[band.left_edge_observation_id],
                sequence_edges_by_id[band.right_edge_observation_id],
            ),
        )
        if intersect(
            left_edge.coordinate_interval_px,
            conditioned_full[left_index],
        )
        is not None
        and intersect(
            right_edge.coordinate_interval_px,
            conditioned_full[right_index],
        )
        is not None
        and (
            left_index,
            band.left_edge_observation_id,
        )
        in observations_by_role_and_id
        and (
            right_index,
            band.right_edge_observation_id,
        )
        in observations_by_role_and_id
    )
    seed_band_ids = {
        item.separator_band_observation_id
        for item in seed.local_advance_proposals
        if item.separator_band_observation_id is not None
    }

    bound_separator_bands_list: list[BoundSeparatorBand] = []
    for ordinal in range(1, lane.output_slot_count):
        candidates = tuple(
            item for item in compatible_bound_bands if item[1] == ordinal
        )
        seeded = tuple(
            item for item in candidates if item[0].observation_id in seed_band_ids
        )
        selected = (
            seeded
            if seeded
            else candidates
            if len(candidates) == 1
            else ()
        )
        if len(selected) > 1:
            raise ValueError(
                "one adjacency cannot bind multiple separator bands"
            )
        bound_separator_bands_list.extend(
            BoundSeparatorBand(
                observation=band,
                relation_ordinal=relation_ordinal,
                left_role_index=left_index,
                right_role_index=right_index,
            )
            for band, relation_ordinal, left_index, right_index in selected
        )
    bound_separator_bands = tuple(bound_separator_bands_list)
    if bind_all_compatible_bands:
        bound_keys = {
            (item.observation.observation_id, item.relation_ordinal)
            for item in bound_separator_bands
        }
        existing_ids = {
            item.proposal_id for item in seed.local_advance_proposals
        }
        additional = tuple(
            role
            for band in proposal.separator_band_proposals
            if (band.band_observation_id, band.relation_ordinal) in bound_keys
            for role in (
                band.left_role_proposal,
                band.right_role_proposal,
            )
            if role.proposal_id not in existing_ids
        )
        if additional:
            augmented = replace(
                seed,
                local_advance_proposals=tuple(
                    sorted(
                        (*seed.local_advance_proposals, *additional),
                        key=lambda item: (
                            item.role.role_index,
                            item.proposal_id,
                        ),
                    )
                ),
            )
            return materialize_sequence_placement(
                lane,
                proposal,
                augmented,
                direction,
                geometry,
                projection_cache,
                evidence_cache,
                bind_all_compatible_bands=False,
            )
    if seed_band_ids - {
        item.observation.observation_id for item in bound_separator_bands
    }:
        raise ValueError(
            "direct separator seed did not bind both physical edge roles"
        )
    # Every bound band side has already passed through
    # ``materialized_role_evidence`` (including bands attached by the bounded
    # recursive pass above).  Keep that direction-conditioned physical range.
    # Replacing it with the raw one-dimensional peak interval would erase the
    # observed divider's local non-orthogonality and could cut a corner after
    # deskew.
    # Reconstruct the selected rectangle chain from one shared W.  Direct
    # separator gaps may show the small natural variation of a normal advance;
    # an unobserved relation uses G_source, and an authorized local anomaly is
    # applied once at that adjacency.  Direct edges constrain the common phase
    # but may never resize individual frames.
    # W and H consume the one jointly refined source scan state.  Reusing the
    # pre-joint long-axis scale here would silently restore two independent
    # px/mm systems even though the feasibility geometry is source-shared.
    _scale, normalized_width, _factor = geometry.width_state.canonical_state()
    canonical_width = geometry.width_state.design_extent_mm * normalized_width
    canonical_gap = (
        max(
            -canonical_width,
            gap_model.canonical_placement_pitch_px - canonical_width,
        )
        if gap_model.canonical_placement_pitch_px is not None
        else 0.0
    )
    canonical_by_role: dict[int, float] = {}
    for role_index in range(len(proposal.roles)):
        values = sorted(
            item.canonical_position_px
            for item in observations
            if item.role.role_index == role_index
        )
        if values:
            canonical_by_role[role_index] = values[len(values) // 2]
    relation_gaps = [
        canonical_gap + relation.canonical_delta_px
        for relation in relations
    ]
    for band in bound_separator_bands:
        left = canonical_by_role.get(band.left_role_index)
        right = canonical_by_role.get(band.right_role_index)
        if left is not None and right is not None:
            relation_gaps[band.relation_ordinal - 1] = right - left
    relative_positions: list[float] = []
    current_start = 0.0
    for ordinal in range(1, lane.output_slot_count + 1):
        relative_positions.extend(
            (current_start, current_start + canonical_width)
        )
        if ordinal < lane.output_slot_count:
            current_start += canonical_width + relation_gaps[ordinal - 1]
    # A proven local advance divides the strip into normal-phase segments.
    # Fitting one global median phase would spread that one physical jump over
    # every frame.  Each segment instead consumes its own direct anchors; the
    # difference between adjacent segment phases is written back to the one
    # authorized relation and clipped only by that relation's evidence.
    directly_bound_relation_ordinals = {
        item.relation_ordinal for item in bound_separator_bands
    }
    segment_by_ordinal: dict[int, int] = {}
    segment_index = 0
    for ordinal in range(1, lane.output_slot_count + 1):
        if (
            ordinal > 1
            and relations[ordinal - 2].kind != LocalAdvanceKind.NOMINAL
            and ordinal - 1 not in directly_bound_relation_ordinals
        ):
            segment_index += 1
        segment_by_ordinal[ordinal] = segment_index
    segment_count = segment_index + 1
    phase_preferences_by_segment: list[list[float]] = [
        [] for _index in range(segment_count)
    ]
    for item in observations:
        phase_preferences_by_segment[
            segment_by_ordinal[item.role.lane_ordinal]
        ].append(
            item.canonical_position_px
            - relative_positions[item.role.role_index]
        )
    if not any(phase_preferences_by_segment):
        raise ValueError("selected sequence has no direct phase evidence")
    preferred_segment_phases_list: list[float] = []
    for current_segment, values in enumerate(
        phase_preferences_by_segment
    ):
        outward_start_terms: list[float] = []
        outward_end_terms: list[float] = []
        for role_index, role in enumerate(proposal.roles):
            if (
                segment_by_ordinal[role.lane_ordinal]
                != current_segment
            ):
                continue
            observed = by_role.get(role_index)
            if observed is None:
                continue
            if role.role == BoundaryRole.START:
                outward_start_terms.append(
                    relative_positions[role_index] - observed[1].minimum
                )
            else:
                outward_end_terms.append(
                    observed[1].maximum - relative_positions[role_index]
                )
        if outward_start_terms and outward_end_terms:
            # min max(max(start_offset + phase),
            #         max(end_offset - phase))
            # has this exact unweighted solution.  It places the fixed-format
            # chain inside the smallest evidence-required outer envelope;
            # direct-use percentages do not participate.
            preferred = (
                max(outward_end_terms) - max(outward_start_terms)
            ) / 2.0
        elif values:
            preferred = sorted(values)[len(values) // 2]
        else:
            # A local anomaly splits the chain into independent phase
            # segments.  Evidence from another segment cannot choose this
            # segment's absolute position: doing so would move an unobserved
            # separator without local geometry.  Keep the chain unresolved.
            raise ValueError("local phase segment has no direct anchor")
        preferred_segment_phases_list.append(preferred)
    preferred_segment_phases = tuple(preferred_segment_phases_list)
    selected_segment_phases = [preferred_segment_phases[0]]
    adjusted_relations = list(relations)
    for relation_index, relation in enumerate(relations):
        if (
            relation.kind == LocalAdvanceKind.NOMINAL
            or relation.relation_ordinal in directly_bound_relation_ordinals
        ):
            continue
        previous_segment = segment_by_ordinal[relation.relation_ordinal]
        next_segment = segment_by_ordinal[relation.relation_ordinal + 1]
        previous_phase = selected_segment_phases[previous_segment]
        while len(selected_segment_phases) <= next_segment:
            selected_segment_phases.append(previous_phase)
        desired_difference = (
            preferred_segment_phases[next_segment] - previous_phase
        )
        minimum_difference = (
            relation.delta_interval_px.minimum
            - relation.canonical_delta_px
        )
        maximum_difference = (
            relation.delta_interval_px.maximum
            - relation.canonical_delta_px
        )
        selected_difference = min(
            maximum_difference,
            max(minimum_difference, desired_difference),
        )
        selected_segment_phases[next_segment] = (
            previous_phase + selected_difference
        )
        adjusted_delta = relation.canonical_delta_px + selected_difference
        adjusted_relations[relation_index] = replace(
            relation,
            canonical_delta_px=adjusted_delta,
        )
    relations = tuple(adjusted_relations)
    relation_gaps = [
        canonical_gap + relation.canonical_delta_px
        for relation in relations
    ]
    for band in bound_separator_bands:
        left = canonical_by_role.get(band.left_role_index)
        right = canonical_by_role.get(band.right_role_index)
        if left is not None and right is not None:
            relation_gaps[band.relation_ordinal - 1] = right - left
    relative_positions = []
    current_start = 0.0
    for ordinal in range(1, lane.output_slot_count + 1):
        relative_positions.extend(
            (current_start, current_start + canonical_width)
        )
        if ordinal < lane.output_slot_count:
            current_start += canonical_width + relation_gaps[ordinal - 1]
    fill_authority = long_axis_fill_authority(
        lane,
        geometry,
        gap_model,
        relations,
    )
    selected_phase = selected_segment_phases[0]
    if fill_authority.state == EvidenceState.SUPPORTED:
        # A filled holder supplies a *centred interval*, not a mathematically
        # exact midpoint.  Holder moulds and scan extents vary slightly, while
        # direct frame evidence owns the actual phase.  Keep the directly
        # preferred phase whenever it lies in the filled-layout authority and
        # otherwise clamp it to their common feasible interval.  Full may
        # resolve a weak phase; it may never overwrite compatible pixels with
        # the raster centre.
        relative_midpoint = (
            relative_positions[0] + relative_positions[-1]
        ) / 2.0
        centered_phase_authority = subtract(
            fill_authority.centered_midpoint_authority_px,
            FiniteInterval.exact(relative_midpoint),
        )
        legal_phase = intersect(phase_full, centered_phase_authority)
        if legal_phase is None:
            raise ValueError("centred holder phase contradicts direct sequence evidence")
        selected_phase = min(
            legal_phase.maximum,
            max(legal_phase.minimum, selected_phase),
        )
    conditioned_canonical = [
        selected_phase + relative for relative in relative_positions
    ]

    # The conditioned intervals above are the selected chain's own physical
    # uncertainty.  They have already consumed every shared W, phase, gap and
    # direct-edge constraint bidirectionally, so retaining one inferred side
    # does not reintroduce the old cumulative independent-extrema widening.
    # This is not padding: for example, ``start = observed_end - shared_W``
    # remains uncertain whenever the source-shared W interval is uncertain.
    selected_safe_positions: list[FiniteInterval] = []
    for role_index, canonical in enumerate(conditioned_canonical):
        observed = by_role.get(role_index)
        if observed is not None:
            displacement = role_direction_displacements_px[role_index]
            direction_conditioned = FiniteInterval(
                observed[1].minimum - displacement,
                observed[1].maximum + displacement,
            )
            safe = hull((FiniteInterval.exact(canonical), direction_conditioned))
        else:
            safe = hull(
                (
                    FiniteInterval.exact(canonical),
                    conditioned_full[role_index],
                )
            )
        selected_safe_positions.append(safe)

    return SequencePlacement(
        placement_id=physical_fact_id(
            "sequence-placement",
            proposal.frame_spec.frame_spec_id,
            seed.chain_proposal_id,
            direction.direction_id,
            geometry.geometry_id,
        ),
        chain_proposal_id=seed.chain_proposal_id,
        sequence_group_ids=seed.sequence_group_ids,
        source_scan_geometry_id=geometry.geometry_id,
        roles=proposal.roles,
        phase_fit_interval_px=phase_fit,
        phase_full_interval_px=phase_full,
        lane_gap_model=gap_model,
        local_advance_relations=relations,
        canonical_positions_px=tuple(conditioned_canonical),
        fit_positions_px=tuple(selected_safe_positions),
        full_positions_px=tuple(selected_safe_positions),
        role_fit_direction_intervals_degrees=tuple(
            role_fit_direction_intervals
        ),
        role_full_direction_intervals_degrees=tuple(
            role_full_direction_intervals
        ),
        observations=observations,
        separator_bands=bound_separator_bands,
        exclusion_authorized=seed.exclusion_authorized,
        long_axis_fill_authority=fill_authority,
    )
