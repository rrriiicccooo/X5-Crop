"""Derive CandidateGate facts from bounded template reconstruction."""

from __future__ import annotations

from dataclasses import dataclass

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
from .template_model import LocalAdvanceKind
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


@dataclass(frozen=True)
class TemplateGateResult:
    facts: dict[str, TypedAssessment]


def build_template_gate(
    resolved: ResolvedOutputSlots,
    reconstructions: tuple[TemplateLaneReconstruction, ...],
    source_selection: TemplateSourceSelection,
) -> TemplateGateResult:
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
            == PhaseFailureKind.LOCAL_ADVANCE_AMBIGUOUS
        ),
        None,
    )
    local_advance_unresolved = local_phase_failure is not None or any(
        lane.prepared.phase_competition.best is not None
        and any(
            relation.kind
            in {
                LocalAdvanceKind.CONTACT,
                LocalAdvanceKind.OVERLAP,
                LocalAdvanceKind.UNRESOLVED,
            }
            for relation in lane.prepared.phase_competition.best.local_advance_relations
        )
        for lane in reconstructions
    )
    local_advance_failure = (
        None
        if local_phase_failure is None
        else failure_fact(
            GateGap.LOCAL_ADVANCE_UNRESOLVED,
            detail=(
                local_phase_failure.ambiguity_reason
                or GateGap.LOCAL_ADVANCE_UNRESOLVED.value
            ),
        )
    )
    output_count = sum(len(lane.output_footprints) for lane in reconstructions)
    output_complete = selected and output_count == resolved.output_slot_count
    output_safe = output_complete and all(
        not output.saturation_facts
        for lane in reconstructions
        for output in lane.output_footprints
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
        "sequence_authority": (
            supported()
            if selected
            else unavailable(selection_gap, selection_failure)
        ),
        "cross_authority": (
            supported() if selected else unavailable(GateGap.CROSS_AUTHORITY_UNAVAILABLE)
        ),
        "shared_authority": (
            supported() if selected else unavailable(GateGap.SHARED_AUTHORITY_UNAVAILABLE)
        ),
        "local_advance_authority": (
            unavailable(
                GateGap.LOCAL_ADVANCE_UNRESOLVED,
                local_advance_failure,
            )
            if local_advance_unresolved
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
        "slot_ordinal_assignment": (
            supported()
            if complete
            else unavailable(GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED)
        ),
        "source_lane_authority": supported(),
        "selected_output_footprint": (
            supported()
            if output_safe
            else contradicted(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE)
            if output_complete
            else unavailable(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE)
        ),
        "direct_use_budget": budget_fact,
    }
    return TemplateGateResult(facts)


__all__ = [
    "TemplateGateResult",
    "build_template_gate",
    "supported",
    "unavailable",
]
