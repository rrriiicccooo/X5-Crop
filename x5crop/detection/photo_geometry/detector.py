"""Orchestrate the bounded fixed-format template detector."""

from __future__ import annotations

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ...domain import EvidenceState
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from ..gate_checks import GateGap, failure_fact
from ..source_core import SourceLaneEvidence
from .content_topology import build_content_topology_index
from .content_veto import content_veto_assessment
from .lane_preparation import (
    lane_measurement_capacity,
    prepare_template_lane,
    resolve_output_slots,
)
from .measurement_model import PhotoBoundaryMeasurementField
from .output_model import OutputSlotIdentity
from .source_geometry import SourceScanGeometry
from .template_cross_model import CrossFit, CrossFitStatus
from .template_direction import lane_template_direction, shared_template_direction
from .template_gate import (
    build_template_gate,
    output_transform,
    supported,
    unavailable,
)
from .template_output import (
    safe_crop_envelope_from_template_placement,
    template_direct_use_budget_assessment,
)
from .template_precision import template_precision_ledger
from .template_phase_model import PhaseFitStatus
from .template_placement import FormatPlacement, compose_format_placement
from .template_runtime_model import (
    PhotoGeometryDetectionResult,
    PreparedTemplateLane,
    TemplateLaneReconstruction,
    TemplatePlacementCompetition,
    TemplatePlacementWorkReceipt,
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


def _fit_direction(lane: PreparedTemplateLane):
    phase = lane.phase_competition.best
    cross = lane.cross_competition.best
    if phase is None or cross is None:
        return None
    try:
        return lane_template_direction(phase, lane.sequence_edges, cross)
    except ValueError:
        return None


def _shared_direction(prepared: tuple[PreparedTemplateLane, ...]):
    values = tuple(
        _fit_direction(lane) for lane in prepared
    )
    if not values or any(item is None for item in values):
        return None
    try:
        return shared_template_direction(tuple(item for item in values if item is not None))
    except ValueError:
        return None


def _compose(
    prepared: PreparedTemplateLane,
    *,
    sequence_fit,
    cross_fit,
    source_geometry,
    direction,
) -> FormatPlacement | None:
    if sequence_fit is None or cross_fit is None or direction is None:
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
            direction=direction,
        )
    except ValueError:
        return None


def _placements(
    prepared: PreparedTemplateLane,
    *,
    source_geometry: SourceScanGeometry,
    direction,
) -> tuple[FormatPlacement | None, FormatPlacement | None]:
    phase = prepared.phase_competition
    cross = prepared.cross_competition
    best = _compose(
        prepared,
        sequence_fit=phase.best,
        cross_fit=cross.best,
        source_geometry=source_geometry,
        direction=direction,
    )
    runner = None
    if phase.runner_up is not None:
        runner = _compose(
            prepared,
            sequence_fit=phase.runner_up,
            cross_fit=cross.best,
            source_geometry=source_geometry,
            direction=direction,
        )
    elif cross.runner_up is not None:
        runner_direction = cross.runner_up.selected_direction or direction
        runner = _compose(
            prepared,
            sequence_fit=phase.best,
            cross_fit=cross.runner_up,
            source_geometry=source_geometry,
            direction=runner_direction,
        )
    if best is not None and runner is not None and best.placement_id == runner.placement_id:
        runner = None
    return best, runner


def _empty_result(
    field: PhotoBoundaryMeasurementField,
    *,
    layout: str,
    lanes_available: bool,
    output_slot_gap: GateGap = GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE,
) -> PhotoGeometryDetectionResult:
    selection = TemplateSourceSelection(
        (), (), None, None, EvidenceState.UNAVAILABLE,
        failure_fact(output_slot_gap),
    )
    transform = output_transform(field, layout, selection)
    facts = {
        "scan_canvas_authority": (
            supported()
            if lanes_available
            else unavailable(GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE)
        ),
        "output_slot_count": unavailable(output_slot_gap),
        "observation_completeness": unavailable(GateGap.PRODUCER_BOUND_EXCEEDED),
        "source_scan_geometry": unavailable(GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE),
        "shared_strip_direction": unavailable(GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE),
        "complete_placement": unavailable(GateGap.COMPLETE_PLACEMENT_UNAVAILABLE),
        "producer_coverage": unavailable(GateGap.PRODUCER_BOUND_EXCEEDED),
        "sequence_authority": unavailable(GateGap.SEQUENCE_AUTHORITY_UNAVAILABLE),
        "cross_authority": unavailable(GateGap.CROSS_AUTHORITY_UNAVAILABLE),
        "shared_authority": unavailable(GateGap.SHARED_AUTHORITY_UNAVAILABLE),
        "local_advance_authority": unavailable(GateGap.LOCAL_ADVANCE_UNRESOLVED),
        "content_protection": supported(),
        "selected_placement": unavailable(GateGap.PLACEMENT_UNRESOLVED),
        "slot_ordinal_assignment": unavailable(GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED),
        "source_lane_authority": (
            supported()
            if lanes_available
            else unavailable(GateGap.SOURCE_LANE_AUTHORITY_INVALID)
        ),
        "selected_only_envelope": unavailable(GateGap.SELECTED_PLACEMENT_CONTAINMENT_UNAVAILABLE),
        "direct_use_budget": unavailable(GateGap.DIRECT_USE_BUDGET_UNAVAILABLE),
        "transform_sampling": unavailable(GateGap.OUTPUT_TRANSFORM_UNAVAILABLE),
    }
    return PhotoGeometryDetectionResult(None, (), selection, (), transform, (), facts)


def reconstruct_photo_geometry(
    field: PhotoBoundaryMeasurementField,
    lanes: tuple[SourceLaneEvidence, ...],
    content_observations: tuple[ContentOccupancyObservationSet, ...],
    *,
    layout: str,
    configuration: DetectionConfiguration,
    resolved_slot_count: ResolvedSlotCount | None,
    development_detail: bool = False,
) -> PhotoGeometryDetectionResult:
    del development_detail
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
            field,
            layout=layout,
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
    shared_direction = _shared_direction(prepared)
    provisional: list[
        tuple[FormatPlacement | None, FormatPlacement | None, object, TemplatePlacementCompetition]
    ] = []
    for lane, content in zip(prepared, content_observations, strict=True):
        geometry = shared_geometry or lane.source_scan_geometry
        direction = shared_direction or _fit_direction(lane)
        best, runner = _placements(
            lane,
            source_geometry=geometry,
            direction=direction,
        )
        content_assessment = (
            None
            if (
                best is None
                or lane.phase_competition.status != PhaseFitStatus.RESOLVED
                or lane.cross_competition.status != CrossFitStatus.RESOLVED
            )
            else content_veto_assessment(
                best,
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
        provisional.append((best, runner, content_assessment, competition))

    source_selection = select_template_source(
        tuple(item[3] for item in provisional),
        lane_ids=lane_ids,
        shared_scan_geometry=shared_geometry,
        shared_direction=shared_direction,
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
            None,
            EvidenceState.UNAVAILABLE,
            failure,
            tuple(item.runner_up_placement_id for item in competitions),
        )
    else:
        competitions = tuple(item[3] for item in provisional)

    transform = output_transform(field, layout, source_selection)
    reconstructions: list[TemplateLaneReconstruction] = []
    lane_transforms = []
    for lane, source_lane, values, competition in zip(
        prepared, lanes, provisional, competitions, strict=True
    ):
        selected = (
            values[0]
            if source_selection.state == EvidenceState.SUPPORTED
            else None
        )
        lane_transform = transform
        envelopes = ()
        if selected is not None and lane_transform.transform is not None:
            try:
                envelopes = tuple(
                    safe_crop_envelope_from_template_placement(
                        selected,
                        lane=source_lane,
                        lane_ordinal=ordinal,
                        layout=layout,
                        transform=lane_transform.transform,
                    )
                    for ordinal in range(1, selected.output_slot_count + 1)
                )
            except ValueError:
                envelopes = ()
        budgets = tuple(
            template_direct_use_budget_assessment(
                selected, envelope, lane_transform.transform
            )
            for envelope in envelopes
            if selected is not None and lane_transform.transform is not None
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
                selected_placement=selected,
                safe_crop_envelopes=envelopes,
                direct_use_budget_assessments=budgets,
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
                precision_ledger=(
                    None
                    if selected is None
                    else template_precision_ledger(
                        selected,
                        lane.measurement_plan,
                    )
                ),
            )
        )
        lane_transforms.append(lane_transform)
    reconstructed = tuple(reconstructions)
    gate = build_template_gate(
        field,
        resolved,
        reconstructed,
        source_selection,
        tuple(lane_transforms),
        layout=layout,
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved,
        lane_reconstructions=reconstructed,
        source_placement_selection=source_selection,
        output_slot_identities=_output_identities(
            lanes, resolved.lane_output_slot_counts
        ),
        source_transform_assessment=gate.source_transform,
        lane_transform_assessments=tuple(lane_transforms),
        assessment_facts=gate.facts,
    )


__all__ = ["reconstruct_photo_geometry"]
