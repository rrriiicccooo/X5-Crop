"""Derive CandidateGate facts from bounded template reconstruction."""

from __future__ import annotations

from ...domain import EvidenceState
from ..gate_checks import (
    DetectionFailureFact,
    GateGap,
    TypedAssessment,
    failure_fact,
)
from .output_model import ResolvedOutputSlots
from .template_cross_model import CrossFitStatus
from .template_holder_fill import HolderFillState
from .template_phase_model import PhaseFailureKind, PhaseFitStatus
from .template_runtime_model import TemplateLaneReconstruction, TemplateSourceSelection


def supported() -> TypedAssessment:
    return TypedAssessment(EvidenceState.SUPPORTED, None)


def unavailable(
    gap: GateGap,
    failure: DetectionFailureFact | None = None,
) -> TypedAssessment:
    return TypedAssessment(EvidenceState.UNAVAILABLE, gap, failure)


def contradicted(
    gap: GateGap,
    failure: DetectionFailureFact | None = None,
) -> TypedAssessment:
    return TypedAssessment(EvidenceState.CONTRADICTED, gap, failure)


def build_template_gate(
    resolved: ResolvedOutputSlots,
    reconstructions: tuple[TemplateLaneReconstruction, ...],
    source_selection: TemplateSourceSelection,
) -> dict[str, TypedAssessment]:
    if not reconstructions:
        raise ValueError("template gate requires every reconstructed lane")
    measurement_complete = all(
        lane.prepared.measurement_work.completed_query_count
        == lane.prepared.measurement_work.measurement_query_count
        for lane in reconstructions
    )
    bounds_valid = all(
        not lane.work.bound_exceeded
        and lane.prepared.phase_competition.status
        != PhaseFitStatus.BOUND_EXCEEDED
        and lane.prepared.cross_competition.status
        != CrossFitStatus.BOUND_EXCEEDED
        for lane in reconstructions
    )
    complete = all(lane.placement_competition.placements for lane in reconstructions)
    content_rejected = any(lane.content_veto_facts for lane in reconstructions)
    selected = source_selection.state == EvidenceState.SUPPORTED
    fill_states = tuple(
        lane.holder_fill_assessment.state
        for lane in reconstructions
        if lane.holder_fill_assessment is not None
    )
    if not selected or len(fill_states) != len(reconstructions):
        dual_fill_fact = unavailable(GateGap.DUAL_LANE_FILL_UNRESOLVED)
    elif len(reconstructions) == 1:
        dual_fill_fact = supported()
    elif any(state == HolderFillState.NOT_FILLED for state in fill_states):
        dual_fill_fact = contradicted(GateGap.DUAL_LANE_NOT_FILLED)
    elif any(state == HolderFillState.UNRESOLVED for state in fill_states):
        dual_fill_fact = unavailable(GateGap.DUAL_LANE_FILL_UNRESOLVED)
    else:
        dual_fill_fact = supported()
    local_phase_failure = next(
        (
            lane.prepared.phase_competition
            for lane in reconstructions
            if lane.prepared.phase_competition.failure_kind
            in {
                PhaseFailureKind.ADJACENCY_RELATION_AMBIGUOUS,
                PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED,
                PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
                PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
            }
        ),
        None,
    )
    adjacency_relation_unresolved = local_phase_failure is not None
    adjacency_relation_failure = (
        None
        if local_phase_failure is None
        else failure_fact(
            (
                GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED
                if local_phase_failure.failure_kind
                in {
                    PhaseFailureKind.ADJACENCY_TOPOLOGY_AMBIGUOUS,
                    PhaseFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED,
                }
                else GateGap.ADJACENCY_CONTINUITY_UNRESOLVED
                if local_phase_failure.failure_kind
                == PhaseFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                else GateGap.ADJACENCY_RELATION_UNRESOLVED
            ),
            detail=(
                local_phase_failure.ambiguity_reason
                or local_phase_failure.failure_kind.value
            ),
        )
    )
    output_count = sum(len(lane.output_footprints) for lane in reconstructions)
    output_complete = selected and output_count == resolved.output_slot_count
    unsafe_saturations = tuple(
        fact
        for lane in reconstructions
        for output in lane.output_footprints
        for fact in output.saturation_facts
        if not fact.source_boundary
    )
    output_safe = output_complete and all(
        output.source_authority_supported
        for lane in reconstructions
        for output in lane.output_footprints
    )
    output_failure = (
        None
        if not unsafe_saturations
        else failure_fact(
            GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE,
            detail=";".join(
                f"{fact.authority_side.value}:{fact.kind.value}"
                for fact in unsafe_saturations
            ),
        )
    )
    budgets = tuple(
        item
        for lane in reconstructions
        for item in lane.direct_use_budget_assessments
    )
    budget_fact = (
        contradicted(GateGap.DIRECT_USE_BUDGET_EXCEEDED)
        if any(item.state == EvidenceState.CONTRADICTED for item in budgets)
        else supported()
        if output_complete
        and len(budgets) == resolved.output_slot_count
        and all(item.state == EvidenceState.SUPPORTED for item in budgets)
        else unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE)
    )
    nominal_authorities = tuple(
        lane.calibrated_nominal_grid_authority for lane in reconstructions
    )
    nominal_grid_fact = (
        contradicted(GateGap.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE)
        if any(
            item.state == EvidenceState.CONTRADICTED
            for item in nominal_authorities
        )
        else unavailable(GateGap.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE)
        if any(
            item.state == EvidenceState.UNAVAILABLE
            for item in nominal_authorities
        )
        else supported()
    )
    selection_failure = source_selection.failure
    selection_gap = (
        selection_failure.gap
        if selection_failure is not None
        else GateGap.PLACEMENT_UNRESOLVED
        if complete
        else GateGap.COMPLETE_PLACEMENT_UNAVAILABLE
    )
    facts = {
        "scan_canvas_authority": supported(),
        "output_slot_count": supported(),
        "observation_completeness": (
            supported()
            if measurement_complete and bounds_valid
            else contradicted(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "source_scan_geometry": supported(),
        "complete_placement": (
            supported()
            if complete
            else unavailable(
                selection_gap,
                selection_failure,
            )
        ),
        "producer_coverage": (
            supported()
            if bounds_valid
            else contradicted(GateGap.PRODUCER_BOUND_EXCEEDED)
        ),
        "adjacency_relation_authority": (
            unavailable(
                adjacency_relation_failure.gap,
                adjacency_relation_failure,
            )
            if adjacency_relation_unresolved
            else supported()
        ),
        "content_protection": (
            contradicted(GateGap.CONTENT_VETO_REJECTED)
            if content_rejected
            else supported()
        ),
        "selected_placement": (
            supported()
            if selected
            else unavailable(selection_gap, selection_failure)
        ),
        "dual_lane_fill": dual_fill_fact,
        "source_lane_authority": supported(),
        "selected_output_footprint": (
            supported()
            if output_safe
            else contradicted(
                GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE,
                output_failure,
            )
            if output_complete
            else unavailable(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE)
        ),
        "calibrated_nominal_grid_authority": nominal_grid_fact,
        "direct_use_budget": budget_fact,
    }
    return facts
