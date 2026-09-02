"""Orchestrate the bounded fixed-format template detector."""

from __future__ import annotations

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import EvidenceState
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from ..gate_checks import GateGap, failure_fact
from ..source_core import SourceLaneEvidence
from .content_topology import build_content_topology_index
from .content_veto import content_veto_assessment
from .content_veto_model import ContentVetoAssessment
from .corridors import source_lane_box
from .lane_preparation import (
    lane_measurement_capacity,
    prepare_template_lane,
    resolve_output_slots,
)
from .measurement_model import PhotoBoundaryMeasurementField
from .output_model import OutputFootprint, OutputSlotIdentity
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFitStatus
from .template_feasible_geometry import project_format_placement
from .template_enclosing_support_aperture import (
    not_applicable_enclosing_support_aperture_authority,
)
from .template_gate import (
    build_template_gate,
    supported,
    unavailable,
)
from .template_holder_fill import (
    LaneLongAxisAuthority,
    assess_holder_fill_state,
    photo_group_outer_from_selected_placement,
)
from .template_output import (
    output_footprint_from_template_placement,
    template_direct_use_budget_assessment,
)
from .template_nominal_grid_authority import (
    assess_calibrated_nominal_grid_authority,
)
from .template_phase_model import PhaseFitStatus
from .template_placement import FormatPlacement, compose_format_placement
from .template_runtime_model import (
    PhotoGeometryDetectionResult,
    PreparedTemplateLane,
    TemplateLaneReconstruction,
    TemplatePlacementCompetition,
    TemplatePlacementProposal,
    TemplatePlacementWorkReceipt,
    TemplateProposalState,
    TemplateSourceProposal,
    TemplateSourceSelection,
)
from .template_selection import (
    select_lane_template_placement,
    select_template_source,
    withhold_lane_winner,
)


def _output_identities(
    lanes: tuple[SourceLaneEvidence, ...],
    lane_counts: tuple[int, ...],
) -> tuple[OutputSlotIdentity, ...]:
    result: list[OutputSlotIdentity] = []
    for lane, count in zip(lanes, lane_counts, strict=True):
        for ordinal in range(1, count + 1):
            result.append(
                OutputSlotIdentity(
                    global_output_ordinal=len(result) + 1,
                    lane_id=lane.domain.lane_id,
                    lane_ordinal=ordinal,
                )
            )
    return tuple(result)


def _shared_geometry(
    prepared: tuple[PreparedTemplateLane, ...],
) -> SourceScanGeometry | None:
    if not prepared:
        return None
    result = prepared[0].source_scan_geometry
    try:
        for lane in prepared[1:]:
            result = result.intersect_source_state(lane.source_scan_geometry)
    except ValueError:
        return None
    return result


def _compose(
    prepared: PreparedTemplateLane,
    *,
    sequence_fit,
    cross_fit,
    source_geometry,
) -> FormatPlacement | None:
    if sequence_fit is None or cross_fit is None:
        return None
    try:
        return compose_format_placement(
            lane_id=prepared.lane.domain.lane_id,
            frame_spec=prepared.source_scan_geometry.frame_spec,
            source_scan_geometry=source_geometry,
            sequence_fit=sequence_fit,
            cross_fit=cross_fit,
            width_axis=prepared.width_axis,
            height_axis=prepared.height_axis,
            width_authority_px=prepared.width_authority_px,
            height_authority_px=prepared.height_authority_px,
            template=prepared.template_spec,
        )
    except ValueError:
        return None


def _placements(
    prepared: PreparedTemplateLane,
    *,
    source_geometry: SourceScanGeometry,
) -> tuple[FormatPlacement | None, FormatPlacement | None]:
    phase = prepared.phase_competition
    cross = prepared.cross_competition
    best = _compose(
        prepared,
        sequence_fit=phase.best,
        cross_fit=cross.best,
        source_geometry=source_geometry,
    )
    runner = None
    if phase.runner_up is not None:
        runner = _compose(
            prepared,
            sequence_fit=phase.runner_up,
            cross_fit=cross.best,
            source_geometry=source_geometry,
        )
    elif cross.runner_up is not None:
        runner = _compose(
            prepared,
            sequence_fit=phase.best,
            cross_fit=cross.runner_up,
            source_geometry=source_geometry,
        )
    if best is not None and runner is not None and best.placement_id == runner.placement_id:
        runner = None
    return best, runner


def _empty_result(
    *,
    lanes_available: bool,
    output_slot_gap: GateGap = GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE,
) -> PhotoGeometryDetectionResult:
    proposal_failure = failure_fact(output_slot_gap)
    proposal = TemplateSourceProposal(
        (), (), TemplateProposalState.UNAVAILABLE, proposal_failure
    )
    selection = TemplateSourceSelection(
        (), (), None, EvidenceState.UNAVAILABLE, proposal_failure
    )
    facts = {
        "scan_canvas_authority": (
            supported()
            if lanes_available
            else unavailable(GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE)
        ),
        "output_slot_count": unavailable(output_slot_gap),
        "observation_completeness": unavailable(GateGap.PRODUCER_BOUND_EXCEEDED),
        "source_scan_geometry": unavailable(GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE),
        "complete_placement": unavailable(GateGap.COMPLETE_PLACEMENT_UNAVAILABLE),
        "producer_coverage": unavailable(GateGap.PRODUCER_BOUND_EXCEEDED),
        "adjacency_relation_authority": unavailable(
            GateGap.ADJACENCY_RELATION_UNRESOLVED
        ),
        "content_protection": supported(),
        "selected_placement": unavailable(GateGap.PLACEMENT_UNRESOLVED),
        "dual_lane_fill": unavailable(GateGap.DUAL_LANE_FILL_UNRESOLVED),
        "source_lane_authority": (
            supported()
            if lanes_available
            else unavailable(GateGap.SOURCE_LANE_AUTHORITY_INVALID)
        ),
        "selected_output_footprint": unavailable(GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE),
        "calibrated_nominal_grid_authority": unavailable(
            GateGap.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE
        ),
        "enclosing_support_aperture_consistency": supported(),
        "direct_use_budget": unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE),
    }
    return PhotoGeometryDetectionResult(None, (), proposal, selection, (), facts)


def reconstruct_photo_geometry(
    field: PhotoBoundaryMeasurementField,
    lanes: tuple[SourceLaneEvidence, ...],
    content_observations: tuple[ContentOccupancyObservationSet, ...],
    *,
    layout: str,
    configuration: DetectionConfiguration,
    resolved_slot_count: ResolvedSlotCount | None,
) -> PhotoGeometryDetectionResult:
    lane_ids = tuple(lane.domain.lane_id for lane in lanes)
    if tuple(item.lane_id for item in content_observations) != lane_ids:
        raise ValueError("content observations must cover source lanes")
    resolved = resolve_output_slots(configuration, lanes, resolved_slot_count)
    if resolved is None:
        unsupported_dual_count = (
            configuration.physical_spec.layout.kind == "dual_lane"
            and resolved_slot_count is not None
            and resolved_slot_count.output_count
            != resolved_slot_count.holder_full_count
        )
        return _empty_result(
            lanes_available=bool(lanes),
            output_slot_gap=(
                GateGap.UNSUPPORTED_DUAL_COUNT
                if unsupported_dual_count
                else GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE
            ),
        )

    prepared = tuple(
        prepare_template_lane(
            field,
            lane,
            layout=layout,
            output_slot_count=count,
            measurement_slot_count=lane_measurement_capacity(
                configuration, lanes, lane
            ),
            configuration=configuration,
        )
        for lane, count in zip(
            lanes, resolved.lane_output_slot_counts, strict=True
        )
    )
    shared_geometry = _shared_geometry(prepared)
    provisional: list[
        tuple[
            FormatPlacement | None,
            FormatPlacement | None,
            ContentVetoAssessment | None,
            TemplatePlacementCompetition,
            TemplatePlacementProposal,
        ]
    ] = []
    for lane, content in zip(
        prepared,
        content_observations,
        strict=True,
    ):
        geometry = shared_geometry or lane.source_scan_geometry
        best, runner = _placements(
            lane,
            source_geometry=geometry,
        )
        best_outputs = ()
        proposal_failure = None
        if best is not None:
            try:
                projection = project_format_placement(best)
                best_outputs = tuple(
                    output_footprint_from_template_placement(
                        best,
                        projection,
                        lane=lane.lane,
                        lane_ordinal=ordinal,
                        layout=layout,
                    )
                    for ordinal in range(1, best.output_slot_count + 1)
                )
            except ValueError as error:
                best_outputs = ()
                proposal_failure = failure_fact(
                    GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE,
                    detail=str(error),
                )
        content_assessment = (
            None
            if (
                best is None
                or len(best_outputs) != best.output_slot_count
                or lane.phase_competition.status != PhaseFitStatus.RESOLVED
                or lane.cross_competition.status != CrossFitStatus.RESOLVED
            )
            else content_veto_assessment(
                best,
                tuple(item.required_source_footprint for item in best_outputs),
                build_content_topology_index(content, layout=layout),
            )
        )
        competition = select_lane_template_placement(
            lane_id=lane.lane.domain.lane_id,
            best=best,
            runner_up=runner,
            phase=lane.phase_competition,
            cross=lane.cross_competition,
            content_assessment=content_assessment,
        )
        proposal = TemplatePlacementProposal(
            lane_id=lane.lane.domain.lane_id,
            state=(
                TemplateProposalState.GENERATED
                if best is not None
                and len(best_outputs) == best.output_slot_count
                else TemplateProposalState.UNAVAILABLE
            ),
            placement_id=None if best is None else best.placement_id,
            output_footprints=best_outputs,
            failure=(
                None
                if best is not None
                and len(best_outputs) == best.output_slot_count
                else proposal_failure
                or competition.failure
                or failure_fact(GateGap.COMPLETE_PLACEMENT_UNAVAILABLE)
            ),
        )
        provisional.append(
            (best, runner, content_assessment, competition, proposal)
        )

    lane_proposals = tuple(item[4] for item in provisional)
    source_proposal_failure = next(
        (
            item.failure
            for item in lane_proposals
            if item.state != TemplateProposalState.GENERATED
        ),
        None,
    )
    source_proposal = TemplateSourceProposal(
        lane_ids=lane_ids,
        placement_ids=tuple(
            item.placement_id
            if item.state == TemplateProposalState.GENERATED
            else None
            for item in lane_proposals
        ),
        state=(
            TemplateProposalState.GENERATED
            if source_proposal_failure is None and shared_geometry is not None
            else TemplateProposalState.UNAVAILABLE
        ),
        failure=(
            None
            if source_proposal_failure is None and shared_geometry is not None
            else source_proposal_failure
            or failure_fact(GateGap.SHARED_AUTHORITY_UNAVAILABLE)
        ),
    )

    source_selection = select_template_source(
        tuple(item[3] for item in provisional),
        lane_ids=lane_ids,
        shared_scan_geometry=shared_geometry,
    )
    if source_selection.state != EvidenceState.SUPPORTED:
        failure = source_selection.failure
        if failure is None:
            raise ValueError("unresolved source selection requires a typed failure")
        competitions = tuple(
            withhold_lane_winner(item[3], failure=failure)
            for item in provisional
        )
        source_selection = TemplateSourceSelection(
            lane_ids,
            tuple(None for _lane in lanes),
            None,
            EvidenceState.UNAVAILABLE,
            failure,
            tuple(item.runner_up_placement_id for item in competitions),
        )
    else:
        competitions = tuple(item[3] for item in provisional)

    reconstructions: list[TemplateLaneReconstruction] = []
    for lane, source_lane, values, competition in zip(
        prepared, lanes, provisional, competitions, strict=True
    ):
        selected = (
            values[0]
            if source_selection.state == EvidenceState.SUPPORTED
            else None
        )
        output_footprints = ()
        if selected is not None:
            output_footprints = values[4].output_footprints
        budgets = tuple(
            template_direct_use_budget_assessment(
                selected, output
            )
            for output in output_footprints
            if selected is not None
        )
        nominal_grid_authority = assess_calibrated_nominal_grid_authority(
            lane.phase_competition.calibrated_nominal_grid_evidence,
            placement_id=(
                None if selected is None else selected.placement_id
            ),
            output_geometry_ids=tuple(
                item.geometry_id for item in output_footprints
            ),
        )
        enclosing_support_aperture_authority = (
            not_applicable_enclosing_support_aperture_authority()
            if selected is None
            else selected.enclosing_support_aperture_authority
        )
        holder_fill = (
            None
            if selected is None
            else assess_holder_fill_state(
                photo_group_outer_from_selected_placement(selected),
                LaneLongAxisAuthority.from_box(
                    selected.lane_id,
                    selected.width_axis,
                    source_lane_box(source_lane, layout),
                ),
            )
        )
        phase_receipt = lane.phase_competition.receipt
        bound_exceeded = (
            lane.phase_competition.status == PhaseFitStatus.BOUND_EXCEEDED
            or lane.cross_competition.status == CrossFitStatus.BOUND_EXCEEDED
        )
        content_assessment = values[2]
        reconstructions.append(
            TemplateLaneReconstruction(
                lane_id=lane.lane.domain.lane_id,
                prepared=lane,
                placement_competition=competition,
                placement_proposal=values[4],
                selected_placement=selected,
                output_footprints=output_footprints,
                calibrated_nominal_grid_authority=nominal_grid_authority,
                enclosing_support_aperture_authority=(
                    enclosing_support_aperture_authority
                ),
                direct_use_budget_assessments=budgets,
                holder_fill_assessment=holder_fill,
                content_veto_facts=(
                    () if content_assessment is None else content_assessment.facts
                ),
                work=TemplatePlacementWorkReceipt(
                    placement_evaluation_count=len(competition.placements),
                    boundary_evaluation_count=sum(
                        4 * len(item.frames) for item in competition.placements
                    ),
                    content_evaluation_count=int(content_assessment is not None),
                    peak_temporary_bytes=max(
                        lane.measurement_work.peak_temporary_bytes,
                        phase_receipt.peak_temporary_bytes,
                    ),
                    bound_exceeded=bound_exceeded,
                ),
            )
        )
    reconstructed = tuple(reconstructions)
    gate = build_template_gate(
        resolved,
        reconstructed,
        source_selection,
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved,
        lane_reconstructions=reconstructed,
        source_placement_proposal=source_proposal,
        source_placement_selection=source_selection,
        output_slot_identities=_output_identities(
            lanes, resolved.lane_output_slot_counts
        ),
        assessment_facts=gate,
    )
