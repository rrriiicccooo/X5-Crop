"""Select already fitted template placements without creating candidates."""

from __future__ import annotations

from ...domain import EvidenceState
from ..gate_checks import DetectionFailureFact, GateGap, failure_fact
from .content_veto_model import ContentVetoAssessment
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFitCompetition, CrossFitStatus
from .template_aspect_ratio_model import ApertureAspectRatioFailureKind
from .template_phase_model import PhaseFailureKind, PhaseFitResult, PhaseFitStatus
from .template_placement import FormatPlacement
from .template_runtime_model import (
    TemplatePlacementCompetition,
    TemplateSourceSelection,
)


def select_lane_template_placement(
    *,
    lane_id: str,
    best: FormatPlacement | None,
    runner_up: FormatPlacement | None,
    phase: PhaseFitResult,
    cross: CrossFitCompetition,
    content_assessment: ContentVetoAssessment | None,
) -> TemplatePlacementCompetition:
    """Publish the fit owners' winner while retaining one bounded runner."""

    if not lane_id:
        raise ValueError("template placement selection requires a lane identity")
    if not isinstance(phase, PhaseFitResult) or not isinstance(
        cross, CrossFitCompetition
    ):
        raise TypeError("template selection requires canonical fit competitions")
    placements = tuple(item for item in (best, runner_up) if item is not None)
    if any(not isinstance(item, FormatPlacement) for item in placements):
        raise TypeError("template selection requires format placements")
    if any(item.lane_id != lane_id for item in placements):
        raise ValueError("template placement crosses lane authority")
    if len({item.placement_id for item in placements}) != len(placements):
        raise ValueError("template winner and runner identities must differ")
    if content_assessment is not None and (
        not isinstance(content_assessment, ContentVetoAssessment)
        or best is None
        or content_assessment.placement_id != best.placement_id
        or phase.status != PhaseFitStatus.RESOLVED
        or cross.status != CrossFitStatus.RESOLVED
    ):
        raise ValueError("content veto requires the unique fitted placement")
    try:
        phase.receipt.validate_bounds(slot_count=phase.template.count)
        cross.receipt.validate_bounds()
    except ValueError:
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.CONTRADICTED,
            failure_fact(GateGap.PRODUCER_BOUND_EXCEEDED),
        )
    if phase.status == PhaseFitStatus.BOUND_EXCEEDED or cross.status == CrossFitStatus.BOUND_EXCEEDED:
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.CONTRADICTED,
            failure_fact(GateGap.PRODUCER_BOUND_EXCEEDED),
        )
    if phase.status != PhaseFitStatus.RESOLVED or phase.best is None:
        phase_gap = {
            PhaseFailureKind.DIRECT_PHASE_ANCHOR_UNAVAILABLE: (
                GateGap.PHASE_ANCHOR_UNAVAILABLE
            ),
            PhaseFailureKind.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE: (
                GateGap.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE
            ),
            PhaseFailureKind.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE: (
                GateGap.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE
            ),
            PhaseFailureKind.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE: (
                GateGap.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE
            ),
            PhaseFailureKind.SEPARATOR_MATERIAL_CONFLICT: (
                GateGap.SEPARATOR_MATERIAL_CONFLICT
            ),
            PhaseFailureKind.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE: (
                GateGap.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE
            ),
            PhaseFailureKind.FIXED_TEMPLATE_MISMATCH: (
                GateGap.PHASE_TEMPLATE_MISMATCH
            ),
            PhaseFailureKind.DISCRETE_PHASE_AMBIGUOUS: (
                GateGap.PHASE_PLACEMENT_AMBIGUOUS
            ),
            PhaseFailureKind.LOCAL_ADVANCE_AMBIGUOUS: (
                GateGap.LOCAL_ADVANCE_UNRESOLVED
            ),
        }.get(phase.failure_kind, GateGap.PHASE_TEMPLATE_MISMATCH)
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.UNAVAILABLE,
            failure_fact(
                phase_gap,
                detail=phase.ambiguity_reason,
            ),
        )
    if cross.status != CrossFitStatus.RESOLVED or cross.best is None:
        aspect = cross.aperture_aspect_ratio_authority
        aspect_gap = (
            {
                ApertureAspectRatioFailureKind.AUTHORITY_UNAVAILABLE: (
                    GateGap.APERTURE_ASPECT_RATIO_AUTHORITY_UNAVAILABLE
                ),
                ApertureAspectRatioFailureKind.PHYSICAL_PRIOR_CONFLICT: (
                    GateGap.APERTURE_ASPECT_RATIO_PHYSICAL_PRIOR_CONFLICT
                ),
                ApertureAspectRatioFailureKind.DIRECT_CONFLICT: (
                    GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT
                ),
                ApertureAspectRatioFailureKind.BUDGET_EXHAUSTED: (
                    GateGap.APERTURE_ASPECT_RATIO_BUDGET_EXHAUSTED
                ),
            }.get(aspect.failure_kind)
            if aspect.blocks_cross_resolution
            else None
        )
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.UNAVAILABLE,
            failure_fact(
                aspect_gap
                or (
                    GateGap.PLACEMENT_UNRESOLVED
                    if cross.runner_up is not None
                    else GateGap.CROSS_AUTHORITY_UNAVAILABLE
                ),
                detail=(
                    aspect.failure_detail
                    if aspect_gap is not None
                    else cross.reason
                ),
            ),
        )
    if best is None:
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.UNAVAILABLE,
            failure_fact(GateGap.COMPLETE_PLACEMENT_UNAVAILABLE),
        )
    if best.sequence_fit != phase.best or best.cross_fit != cross.best:
        raise ValueError("template placement does not use the selected fits")
    if content_assessment is not None and content_assessment.vetoed:
        return TemplatePlacementCompetition(
            placements, None,
            None if runner_up is None else runner_up.placement_id,
            EvidenceState.CONTRADICTED,
            failure_fact(GateGap.CONTENT_VETO_REJECTED),
        )
    return TemplatePlacementCompetition(
        placements,
        best.placement_id,
        None if runner_up is None else runner_up.placement_id,
        EvidenceState.SUPPORTED,
        None,
    )


def withhold_lane_winner(
    competition: TemplatePlacementCompetition,
    *,
    failure: DetectionFailureFact,
) -> TemplatePlacementCompetition:
    """Remove a lane-local winner when the source-level join is unresolved."""

    if not isinstance(failure, DetectionFailureFact):
        raise TypeError("withheld template winner requires a typed failure")
    return TemplatePlacementCompetition(
        placements=competition.placements,
        selected_placement_id=None,
        runner_up_placement_id=competition.runner_up_placement_id,
        state=EvidenceState.UNAVAILABLE,
        failure=failure,
    )


def select_template_source(
    competitions: tuple[TemplatePlacementCompetition, ...],
    *,
    lane_ids: tuple[str, ...],
    shared_scan_geometry: SourceScanGeometry | None,
) -> TemplateSourceSelection:
    """Join one winner per lane under the shared source W/H state."""

    if not competitions or len(competitions) != len(lane_ids):
        raise ValueError("source selection requires every lane competition")
    if len(set(lane_ids)) != len(lane_ids) or any(not value for value in lane_ids):
        raise ValueError("source selection lane identities must be unique")
    if any(item.state != EvidenceState.SUPPORTED for item in competitions):
        failure = next(
            item.failure
            for item in competitions
            if item.state != EvidenceState.SUPPORTED
        )
        assert failure is not None
        return TemplateSourceSelection(
            lane_ids,
            tuple(None for _item in competitions),
            None,
            EvidenceState.UNAVAILABLE,
            failure,
            tuple(item.runner_up_placement_id for item in competitions),
        )
    if shared_scan_geometry is None:
        return TemplateSourceSelection(
            lane_ids,
            tuple(None for _item in competitions),
            None,
            EvidenceState.UNAVAILABLE,
            failure_fact(GateGap.SHARED_AUTHORITY_UNAVAILABLE),
            tuple(item.runner_up_placement_id for item in competitions),
        )
    selected = tuple(
        next(
            placement
            for placement in item.placements
            if placement.placement_id == item.selected_placement_id
        )
        for item in competitions
    )
    if any(
        placement.source_scan_geometry != shared_scan_geometry
        for placement in selected
    ):
        raise ValueError("selected placements do not retain shared source authority")
    return TemplateSourceSelection(
        lane_ids,
        tuple(item.placement_id for item in selected),
        shared_scan_geometry,
        EvidenceState.SUPPORTED,
        None,
        tuple(item.runner_up_placement_id for item in competitions),
    )
