"""Materialize one complete fixed-format chain from joint axis evidence."""

from __future__ import annotations

from ...domain import FiniteInterval
from .boundary_projection import BoundRunProjection
from .chains import (
    CompleteFormatChain,
    CrossPlacement,
    BoundRoleEvidence,
    FixedFormatFrameSet,
    LaneGeometry,
)
from .chain_proposals import (
    CrossAxisProposal,
    FrameChainProposals,
    LanePhysicalProposals,
    SequenceChainProposal,
)
from .cross_placement import materialize_cross_placement
from .direction_proposals import (
    joint_chain_direction,
    physical_bound_direction_classes,
)
from .output_model import SharedStripDirection
from .physical_identity import physical_fact_id
from .sequence_evidence import (
    materialized_role_evidence,
    refine_source_geometry,
    refine_width_from_complete_sequence,
    refine_width_from_role_evidence,
)
from .sequence_placement import materialize_sequence_placement
from .sequence_materialization_cache import (
    SequenceMaterializationCache,
    rebind_cached_sequence,
    sequence_materialization_key,
)
from .source_geometry import SourceScanGeometry
from .fixed_frame_geometry import canonical_frames

def _sequence_intersects_authority(
    placement: SequencePlacement,
    authority: FiniteInterval,
) -> bool:
    """Require recoverable pixels, not containment of the physical frame."""

    return all(
        end >= authority.minimum - 1.0e-8
        and start <= authority.maximum + 1.0e-8
        for start, end in zip(
            placement.canonical_positions_px[0::2],
            placement.canonical_positions_px[1::2],
            strict=True,
        )
    )


def _cross_intersects_authority(
    placement: CrossPlacement,
    authority: FiniteInterval,
) -> bool:
    return all(
        bottom >= authority.minimum - 1.0e-8
        and top <= authority.maximum + 1.0e-8
        for top, bottom in zip(
            placement.top_canonical_positions_px,
            placement.bottom_canonical_positions_px,
            strict=True,
        )
    )


def materialize_frame_spec_seed(
    lane_proposal: LanePhysicalProposals,
    frame_proposal: FrameChainProposals,
    seed: SequenceChainProposal,
    direction: SharedStripDirection,
    source_geometry: SourceScanGeometry | None = None,
    projection_cache: dict[tuple[object, ...], BoundRunProjection] | None = None,
    evidence_cache: dict[tuple[str, str, int], BoundRoleEvidence] | None = None,
    sequence_cache: SequenceMaterializationCache | None = None,
    cross_candidates: tuple[CrossAxisProposal, ...] | None = None,
) -> tuple[CompleteFormatChain, ...]:
    """Materialize bounded sequence/cross combinations without axis mixing."""

    lane = lane_proposal.lane
    projection_cache = {} if projection_cache is None else projection_cache
    evidence_cache = {} if evidence_cache is None else evidence_cache
    sequence_cache = {} if sequence_cache is None else sequence_cache
    cross_candidates = (
        lane_proposal.cross_proposals
        if cross_candidates is None
        else cross_candidates
    )
    if not cross_candidates:
        return ()
    if (
        source_geometry is not None
        and source_geometry.frame_spec != frame_proposal.frame_spec
    ):
        raise ValueError("source geometry frame_spec disagrees")

    raw_direction_candidates = tuple(
        candidate
        for cross_proposal in cross_candidates
        for candidate in physical_bound_direction_classes((cross_proposal,))
        if set(candidate.selected_observation_ids).issubset(
            direction.selected_observation_ids
        )
    )
    if len(raw_direction_candidates) != 1:
        return ()
    try:
        joint_direction = joint_chain_direction(
            lane,
            seed,
            raw_direction_candidates[0],
        )
    except ValueError:
        return ()

    # Sequence placement consumes the cross-conditioned source geometry below.
    # Materializing the same seed against the pre-joint geometry first cannot
    # create evidence or authority and used to duplicate the same sequence
    # materialization work for every cross proposal.
    base_seed = seed
    results: list[CompleteFormatChain] = []
    for cross_proposal in cross_candidates:
        try:
            geometry = (
                source_geometry
                if source_geometry is not None
                else refine_source_geometry(
                    lane,
                    frame_proposal,
                    joint_direction,
                    (cross_proposal,),
                    projection_cache=projection_cache,
                )
            )
            joint_seed = base_seed
            geometry = refine_width_from_role_evidence(
                geometry,
                materialized_role_evidence(
                    lane,
                    joint_seed.local_advance_proposals,
                    joint_direction,
                    projection_cache,
                    evidence_cache,
                ),
                slot_count=lane.output_slot_count,
            )
            cache_key = sequence_materialization_key(
                frame_proposal,
                joint_seed,
                joint_direction,
                geometry,
                bind_all_compatible_bands=True,
            )
            cached_sequence = sequence_cache.get(cache_key)
            if cached_sequence is None and cache_key in sequence_cache:
                continue
            if cached_sequence is None:
                try:
                    sequence = materialize_sequence_placement(
                        lane,
                        frame_proposal,
                        joint_seed,
                        joint_direction,
                        geometry,
                        projection_cache,
                        evidence_cache,
                    )
                except ValueError:
                    sequence_cache[cache_key] = None
                    continue
                sequence_cache[cache_key] = sequence
            else:
                sequence = rebind_cached_sequence(
                    cached_sequence,
                    joint_seed,
                    joint_direction,
                    geometry,
                )
            if source_geometry is None:
                completed_geometry = refine_width_from_complete_sequence(
                    geometry,
                    sequence,
                )
                if completed_geometry != geometry:
                    geometry = completed_geometry
                    cache_key = sequence_materialization_key(
                        frame_proposal,
                        joint_seed,
                        joint_direction,
                        geometry,
                        bind_all_compatible_bands=True,
                    )
                    cached_sequence = sequence_cache.get(cache_key)
                    if cached_sequence is None and cache_key in sequence_cache:
                        continue
                    if cached_sequence is None:
                        try:
                            sequence = materialize_sequence_placement(
                                lane,
                                frame_proposal,
                                joint_seed,
                                joint_direction,
                                geometry,
                                projection_cache,
                                evidence_cache,
                            )
                        except ValueError:
                            sequence_cache[cache_key] = None
                            continue
                        sequence_cache[cache_key] = sequence
                    else:
                        sequence = rebind_cached_sequence(
                            cached_sequence,
                            joint_seed,
                            joint_direction,
                            geometry,
                        )
            if not _sequence_intersects_authority(
                sequence,
                lane.width_authority_px,
            ):
                continue
            frame_references = tuple(
                (
                    sequence.canonical_positions_px[index * 2]
                    + sequence.canonical_positions_px[index * 2 + 1]
                )
                / 2.0
                for index in range(lane.output_slot_count)
            )
            frame_reference_intervals = tuple(
                FiniteInterval(
                    (
                        sequence.full_positions_px[index * 2].minimum
                        + sequence.full_positions_px[index * 2 + 1].minimum
                    )
                    / 2.0,
                    (
                        sequence.full_positions_px[index * 2].maximum
                        + sequence.full_positions_px[index * 2 + 1].maximum
                    )
                    / 2.0,
                )
                for index in range(lane.output_slot_count)
            )
            cross = materialize_cross_placement(
                lane,
                cross_proposal,
                joint_direction,
                geometry,
                frame_references,
                frame_reference_intervals,
                projection_cache,
            )
            if not _cross_intersects_authority(
                cross,
                lane.height_authority_px,
            ):
                continue
        except ValueError:
            continue
        centerlines = tuple(
            FiniteInterval(
                (top.minimum + bottom.minimum) / 2.0,
                (top.maximum + bottom.maximum) / 2.0,
            )
            for top, bottom in zip(
                cross.top_full_positions_px,
                cross.bottom_full_positions_px,
                strict=True,
            )
        )
        lane_geometry = LaneGeometry(
            lane_geometry_id=physical_fact_id(
                "lane-geometry",
                lane.lane_id,
                joint_direction.direction_id,
                sequence.phase_full_interval_px.minimum,
                sequence.phase_full_interval_px.maximum,
                sequence.lane_gap_model.gap_model_id,
                *(value.minimum for value in centerlines),
                *(value.maximum for value in centerlines),
            ),
            lane_id=lane.lane_id,
            direction=joint_direction,
            nominal_centerline_px=lane.height_authority_px.center,
            centerline_intervals_px=centerlines,
            sequence_phase_interval_px=sequence.phase_full_interval_px,
            gap_model=sequence.lane_gap_model,
            width_authority_px=lane.width_authority_px,
            height_authority_px=lane.height_authority_px,
        )
        results.append(
            CompleteFormatChain(
                placement_id=physical_fact_id(
                    "complete-format-chain",
                    lane.lane_id,
                    frame_proposal.frame_spec.frame_spec_id,
                    joint_direction.direction_id,
                    geometry.geometry_id,
                    sequence.placement_id,
                    cross.placement_id,
                ),
                lane_id=lane.lane_id,
                frame_spec=frame_proposal.frame_spec,
                output_slot_count=lane.output_slot_count,
                source_scan_geometry=geometry,
                chain_proposal=joint_seed,
                cross_proposal=cross_proposal,
                lane_geometry=lane_geometry,
                sequence=sequence,
                cross=cross,
                fixed_frames=FixedFormatFrameSet(
                    fixed_frame_set_id=physical_fact_id(
                        "canonical-complete-format-chain",
                        sequence.placement_id,
                        cross.placement_id,
                    ),
                    sequence_placement_id=sequence.placement_id,
                    cross_placement_id=cross.placement_id,
                    frames=canonical_frames(
                        lane,
                        joint_direction,
                        sequence,
                        cross,
                        geometry.width_state.extent_projection_px(),
                    ),
                ),
            )
        )
    unique = {item.placement_id: item for item in results}
    return tuple(unique[key] for key in sorted(unique))


def materialize_complete_chain_at_source_geometry(
    lane_proposal: LanePhysicalProposals,
    chain: CompleteFormatChain,
    source_scan_geometry: SourceScanGeometry,
) -> CompleteFormatChain:
    """Materialize one candidate against an already shared source W/H state.

    Lane discovery may narrow the same source state from different physical
    strips.  This function therefore belongs to pre-selection dual-lane
    candidate construction.  Final output must use the exact chain inspected
    by selection and may never call this function.
    """

    frame_proposal = next(
        (
            item
            for item in lane_proposal.frame_proposals
            if item.frame_spec == chain.frame_spec
            and item.discovery_kind == chain.chain_proposal.discovery_kind
        ),
        None,
    )
    if frame_proposal is None:
        raise ValueError("selected chain has no frame proposal")
    candidates = materialize_frame_spec_seed(
        lane_proposal,
        frame_proposal,
        chain.chain_proposal,
        chain.lane_geometry.direction,
        source_geometry=source_scan_geometry,
        projection_cache={},
        cross_candidates=(chain.cross_proposal,),
    )
    matches = tuple(
        item
        for item in candidates
        if item.cross_proposal.cross_proposal_id
        == chain.cross_proposal.cross_proposal_id
    )
    if len(matches) != 1:
        raise ValueError("source-wide W/H state cannot materialize selected chain")
    return matches[0]
