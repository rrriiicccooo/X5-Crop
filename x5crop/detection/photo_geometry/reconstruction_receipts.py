"""Reconstruction work receipts and typed unavailable states."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval
from ...run_local_identity import run_local_id
from ..gate_checks import GateGap, TypedAssessment
from ..output_geometry import OutputTransformAssessment, SharedStripDirectionResolution, output_transform_assessment
from ..source_core import SourceLaneEvidence
from .chain_record_model import CompleteChainRecord
from .chain_proposals import LanePhysicalProposals
from .chains import CompleteFormatChain
from .lane_preparation import PreparedLane
from .measurement_model import PhotoBoundaryMeasurementField
from .output_model import (
    OutputSlotIdentity,
    ResolvedOutputSlots,
    SharedStripDirection,
)
from .producer_receipts import (
    ChainProducerWorkReceipt,
    ProducerBoundsReceipt,
    ProducerPruneReason,
    ProducerPruneSummary,
)
from .source_selection_model import SourcePlacementSelection

def supported_assessment() -> TypedAssessment:
    return TypedAssessment(EvidenceState.SUPPORTED, None)


def unavailable_assessment(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.UNAVAILABLE, gap)


def contradicted_assessment(gap: GateGap) -> TypedAssessment:
    return TypedAssessment(EvidenceState.CONTRADICTED, gap)


def empty_output_transform(
    field: PhotoBoundaryMeasurementField,
    layout: str,
    gap: str,
) -> OutputTransformAssessment:
    return output_transform_assessment(
        SharedStripDirectionResolution(
            direction=None,
            state=EvidenceState.UNAVAILABLE,
            named_gap=gap,
        ),
        layout=layout,
        source_width=field.source_extent.width,
        source_height=field.source_extent.height,
    )


def source_direction_from_selected_chains(
    chains: tuple[CompleteFormatChain, ...],
) -> SharedStripDirection:
    if not chains:
        raise ValueError("source direction requires selected chains")
    directions = tuple(chain.lane_geometry.direction for chain in chains)
    observation_ids = tuple(
        sorted(
            {
                identity
                for direction in directions
                for identity in direction.selected_observation_ids
            },
            key=str,
        )
    )
    angle_interval = FiniteInterval(
        min(item.full_angle_interval_degrees.minimum for item in directions),
        max(item.full_angle_interval_degrees.maximum for item in directions),
    )
    canonical = sum(
        item.canonical_angle_degrees for item in directions
    ) / len(directions)
    return SharedStripDirection(
        direction_id=run_local_id(
            "selected-source-direction",
            *(chain.placement_id for chain in chains),
            *(str(identity) for identity in observation_ids),
        ),
        selected_observation_ids=observation_ids,
        full_angle_interval_degrees=angle_interval,
        canonical_angle_degrees=min(
            angle_interval.maximum,
            max(angle_interval.minimum, canonical),
        ),
    )


def output_slot_identities(
    lanes: tuple[SourceLaneEvidence, ...],
    resolved: ResolvedOutputSlots,
) -> tuple[OutputSlotIdentity, ...]:
    identities: list[OutputSlotIdentity] = []
    for lane, count in zip(lanes, resolved.lane_output_slot_counts, strict=True):
        for ordinal in range(1, count + 1):
            identities.append(
                OutputSlotIdentity(
                    global_output_ordinal=len(identities) + 1,
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                )
            )
    return tuple(identities)


def work_receipt(
    prepared: PreparedLane,
    placements: tuple[CompleteFormatChain, ...],
    *,
    proposal: LanePhysicalProposals | None = None,
) -> ChainProducerWorkReceipt:
    active_proposal = prepared.proposal if proposal is None else proposal
    active_sequence_profile = active_proposal.lane.sequence_profile
    grouping = tuple(
        frame_spec.grouping_work
        for frame_spec in active_proposal.frame_proposals
    )
    group_count = sum(
        len(frame_spec.sequence_groups)
        for frame_spec in active_proposal.frame_proposals
    )
    profile_query_ids = {
        prepared.transition_by_id[str(identity)].query_id
        for profile in (active_sequence_profile, prepared.cross_profile)
        for run in profile.runs
        for identity in run.transition_ids
    }
    completed_measurement_count = sum(
        item.coverage.complete for item in prepared.measurement_sets
    )
    receipt = ChainProducerWorkReceipt(
        measurement_query_count=len(prepared.measurement_sets),
        pixel_query_count=sum(
            item.coverage.pixel_query_count for item in prepared.measurement_sets
        ),
        basic_profile_coordinate_count=(
            active_sequence_profile.coordinate_count
            + prepared.cross_profile.coordinate_count
        ),
        basic_profile_run_count=(
            len(active_sequence_profile.runs)
            + len(prepared.cross_profile.runs)
        ),
        role_proposal_count=sum(
            len(frame_spec.role_proposals)
            for frame_spec in active_proposal.frame_proposals
        ),
        phase_hypothesis_count=sum(
            item.phase_seed_count for item in grouping
        ),
        sequence_group_count=group_count,
        ordinal_role_lookup_count=sum(
            item.ordinal_role_lookup_count for item in grouping
        ),
        ordinal_role_match_count=sum(
            item.ordinal_role_match_count for item in grouping
        ),
        local_relation_evaluation_count=(
            group_count * max(0, prepared.output_slot_count - 1)
        ),
        materialized_frame_geometry_count=sum(
            len(item.fixed_frames.frames) for item in placements
        ),
        shared_measurement_reuse_count=(
            completed_measurement_count + len(profile_query_ids)
        ),
        domain_pixels=(
            prepared.lane.domain.work_box.width
            * prepared.lane.domain.work_box.height
        ),
        peak_temporary_bytes=max(
            (item.coverage.peak_temporary_bytes for item in prepared.measurement_sets),
            default=0,
        ),
    )
    if active_proposal.frame_proposals:
        receipt.validate_bounds(
            ordered_role_count=prepared.output_slot_count * 2,
            slot_count=prepared.output_slot_count,
        )
    return receipt


def producer_bounds_receipt(
    prepared: PreparedLane,
    *,
    proposed_chain_count: int = 0,
    chains: tuple[CompleteChainRecord, ...] = (),
    physical_dominated_count: int = 0,
    sampling_invalid_count: int = 0,
) -> ProducerBoundsReceipt:
    bound_exceeded = any(
        item.proposed_count > item.materialized_count
        for item in prepared.corridor_edge_family_counts
    )
    pruned: dict[ProducerPruneReason, int] = {}
    if prepared.content_contradicted_separator_count:
        pruned[
            ProducerPruneReason.SEPARATOR_CONTENT_CONTRADICTION
        ] = prepared.content_contradicted_separator_count
    if sampling_invalid_count:
        pruned[ProducerPruneReason.SAMPLING_CONTAINMENT_INVALID] = (
            sampling_invalid_count
        )
    if physical_dominated_count:
        pruned[
            ProducerPruneReason.STRICTLY_DOMINATED_PHYSICAL_PLACEMENT
        ] = physical_dominated_count
    return ProducerBoundsReceipt(
        lane_id=prepared.lane.domain.lane_id,
        corridor_edge_families=prepared.corridor_edge_family_counts,
        proposed_complete_chain_count=proposed_chain_count,
        materialized_complete_chain_count=len(chains),
        chain_ledger_entry_count=sum(len(item.ledger) for item in chains),
        prune_summaries=tuple(
            ProducerPruneSummary(reason=reason, count=pruned[reason])
            for reason in ProducerPruneReason
            if reason in pruned
        ),
        bound_exceeded=bound_exceeded,
    )


def empty_source_placement_selection() -> SourcePlacementSelection:
    return SourcePlacementSelection(
        combinations=(),
        selected_combination_id=None,
        shared_scan_geometry=None,
        state=EvidenceState.UNAVAILABLE,
    )


def unresolved_facts(
    direction_gap: GateGap,
    *,
    source_lane_authority_available: bool = True,
) -> dict[str, TypedAssessment]:
    return {
        "scan_canvas_authority": supported_assessment(),
        "output_slot_count": supported_assessment(),
        "observation_completeness": supported_assessment(),
        "source_scan_geometry": unavailable_assessment(
            GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE
        ),
        "shared_strip_direction": unavailable_assessment(direction_gap),
        "complete_chain": unavailable_assessment(GateGap.COMPLETE_CHAIN_UNAVAILABLE),
        "producer_coverage": supported_assessment(),
        "sequence_authority": unavailable_assessment(
            GateGap.SEQUENCE_AUTHORITY_UNAVAILABLE
        ),
        "cross_authority": unavailable_assessment(
            GateGap.CROSS_AUTHORITY_UNAVAILABLE
        ),
        "shared_authority": unavailable_assessment(
            GateGap.SHARED_AUTHORITY_UNAVAILABLE
        ),
        "local_advance_authority": supported_assessment(),
        "content_protection": supported_assessment(),
        "selected_placement": unavailable_assessment(GateGap.PLACEMENT_UNRESOLVED),
        "slot_ordinal_assignment": unavailable_assessment(
            GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
        ),
        "source_lane_authority": (
            supported_assessment()
            if source_lane_authority_available
            else unavailable_assessment(GateGap.SOURCE_LANE_AUTHORITY_INVALID)
        ),
        "selected_only_envelope": unavailable_assessment(
            GateGap.SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE
        ),
        "direct_use_budget": unavailable_assessment(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE),
        "transform_sampling": unavailable_assessment(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE),
    }
