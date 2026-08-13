"""Derive source-level transform and typed Gate facts after selection."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState
from ..gate_checks import GateGap, TypedAssessment
from ..output_geometry import (
    OutputTransformAssessment,
    SharedStripDirectionResolution,
    output_transform_assessment,
)
from .measurement_model import PhotoBoundaryMeasurementField
from .output_model import DirectUseBudgetAssessment, ResolvedOutputSlots
from .reconstruction_model import LaneFormatPlacementReconstruction
from .reconstruction_receipts import (
    contradicted_assessment,
    empty_output_transform,
    source_direction_from_selected_chains,
    supported_assessment,
    unavailable_assessment,
)
from .source_selection_model import SourcePlacementSelection


@dataclass(frozen=True)
class ReconstructionGateFacts:
    source_transform: OutputTransformAssessment
    assessments: dict[str, TypedAssessment]


def build_reconstruction_gate_facts(
    field: PhotoBoundaryMeasurementField,
    resolved: ResolvedOutputSlots,
    reconstructions: tuple[LaneFormatPlacementReconstruction, ...],
    source_selection: SourcePlacementSelection,
    lane_transforms: tuple[OutputTransformAssessment, ...],
    budgets: tuple[DirectUseBudgetAssessment, ...],
    *,
    layout: str,
) -> ReconstructionGateFacts:
    selected_chains = tuple(
        item.selected_placement
        for item in reconstructions
        if item.selected_placement is not None
    )
    transform = (
        output_transform_assessment(
            SharedStripDirectionResolution(
                direction=source_direction_from_selected_chains(selected_chains),
                state=EvidenceState.SUPPORTED,
                named_gap=None,
            ),
            layout=layout,
            source_width=field.source_extent.width,
            source_height=field.source_extent.height,
        )
        if len(selected_chains) == len(reconstructions) and selected_chains
        else empty_output_transform(
            field,
            layout,
            GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE.value,
        )
    )
    lane_chains_complete = bool(reconstructions) and all(
        item.materialized_chains for item in reconstructions
    )
    source_legal = bool(source_selection.combinations)
    complete = lane_chains_complete and source_legal
    selection_complete = complete and all(
        item.placement_selection.state == EvidenceState.SUPPORTED
        for item in reconstructions
    )
    selected_combination = next(
        (
            item
            for item in source_selection.combinations
            if item.combination_id == source_selection.selected_combination_id
        ),
        None,
    )
    lane_count = len(reconstructions)
    sequence_authority_complete = bool(
        selection_complete
        and selected_combination is not None
        and selected_combination.sequence_authority.normal_completion_authorized_count
        == lane_count
        and selected_combination.sequence_authority.local_advance_authorized_count
        == lane_count
    )
    cross_authority_complete = bool(
        selection_complete
        and selected_combination is not None
        and selected_combination.cross_authority.fixed_height_placement_authorized_count
        == lane_count
        and selected_combination.cross_authority.direct_boundary_family_count
        >= lane_count
    )
    shared_authority_complete = bool(
        selection_complete
        and selected_combination is not None
        and selected_combination.shared_authority.source_scale_compatible
        and selected_combination.shared_authority.direction_bound_lane_count
        == lane_count
        and selected_combination.shared_authority.source_lane_authority_bound_count
        == lane_count
        and selected_combination.shared_authority.content_veto_passed_lane_count
        == lane_count
    )
    producer_bounds_valid = all(
        not item.producer_bounds.bound_exceeded for item in reconstructions
    )
    output_geometry_complete = (
        selection_complete
        and producer_bounds_valid
        and sum(len(item.safe_crop_envelopes) for item in reconstructions)
        == resolved.output_slot_count
    )
    budget_state = (
        contradicted_assessment(GateGap.DIRECT_USE_BUDGET_EXCEEDED)
        if any(item.state == EvidenceState.CONTRADICTED for item in budgets)
        else supported_assessment()
        if (
            output_geometry_complete
            and len(budgets) == resolved.output_slot_count
            and all(item.state == EvidenceState.SUPPORTED for item in budgets)
        )
        else unavailable_assessment(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE)
    )
    all_clusters_vetoed = any(
        item.placement_selection.clusters
        and all(
            assessment.vetoed
            for assessment in item.placement_selection.content_veto_assessments
        )
        for item in reconstructions
    )
    local_advance_unresolved = (
        not source_legal
        and any(
            item.local_advance_unresolved_count > 0
            for item in reconstructions
        )
    )
    facts = {
        "scan_canvas_authority": supported_assessment(),
        "output_slot_count": supported_assessment(),
        "observation_completeness": (
            supported_assessment()
            if producer_bounds_valid
            else contradicted_assessment(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "source_scan_geometry": supported_assessment(),
        "shared_strip_direction": (
            supported_assessment()
            if selection_complete
            else unavailable_assessment(
                GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE
                if any(item.materialized_chains for item in reconstructions)
                else GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE
            )
        ),
        "complete_chain": (
            supported_assessment()
            if complete
            else unavailable_assessment(GateGap.COMPLETE_CHAIN_UNAVAILABLE)
        ),
        "producer_coverage": (
            supported_assessment()
            if producer_bounds_valid
            else contradicted_assessment(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "sequence_authority": (
            supported_assessment()
            if sequence_authority_complete
            else unavailable_assessment(GateGap.SEQUENCE_AUTHORITY_UNAVAILABLE)
        ),
        "cross_authority": (
            supported_assessment()
            if cross_authority_complete
            else unavailable_assessment(GateGap.CROSS_AUTHORITY_UNAVAILABLE)
        ),
        "shared_authority": (
            supported_assessment()
            if shared_authority_complete
            else unavailable_assessment(GateGap.SHARED_AUTHORITY_UNAVAILABLE)
        ),
        "local_advance_authority": (
            unavailable_assessment(GateGap.LOCAL_ADVANCE_UNRESOLVED)
            if local_advance_unresolved
            else supported_assessment()
        ),
        "content_protection": (
            contradicted_assessment(GateGap.CONTENT_VETO_REJECTED)
            if all_clusters_vetoed
            else supported_assessment()
        ),
        "selected_placement": (
            supported_assessment()
            if selection_complete
            else unavailable_assessment(
                GateGap.CONTENT_VETO_REJECTED
                if all_clusters_vetoed
                else GateGap.PLACEMENT_UNRESOLVED
                if source_legal
                else GateGap.COMPLETE_CHAIN_UNAVAILABLE
            )
        ),
        "slot_ordinal_assignment": (
            supported_assessment()
            if lane_chains_complete
            else unavailable_assessment(
                GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
            )
        ),
        "source_lane_authority": supported_assessment(),
        "selected_only_envelope": (
            supported_assessment()
            if output_geometry_complete
            else unavailable_assessment(
                GateGap.SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE
            )
        ),
        "direct_use_budget": budget_state,
        "transform_sampling": (
            supported_assessment()
            if transform.state == EvidenceState.SUPPORTED
            and all(item.state == EvidenceState.SUPPORTED for item in lane_transforms)
            else unavailable_assessment(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE)
        ),
    }
    return ReconstructionGateFacts(transform, facts)
