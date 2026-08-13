"""Orchestrate current fixed-format physical-chain reconstruction."""

from __future__ import annotations

from ...configuration.model import DetectionConfiguration, ResolvedSlotCount
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from ..gate_checks import GateGap
from ..source_core import SourceLaneEvidence
from .lane_preparation import (
    lane_measurement_capacity,
    prepare_lane,
    resolve_output_slots,
)
from .lane_reconstruction import build_lane_candidate_reconstructions
from .measurement_model import PhotoBoundaryMeasurementField
from .reconstruction_gate_facts import build_reconstruction_gate_facts
from .reconstruction_model import PhotoGeometryDetectionResult
from .reconstruction_receipts import (
    empty_output_transform,
    empty_source_placement_selection,
    output_slot_identities,
    supported_assessment,
    unavailable_assessment,
    unresolved_facts,
)
from .selected_source_output import resolve_selected_source_output
from .shared_source_geometry import bind_shared_source_geometry_before_selection
from .source_chain_materialization import materialize_source_placements


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
    if tuple(item.lane_id for item in content_observations) != tuple(
        lane.domain.lane_id for lane in lanes
    ):
        raise ValueError("content observations must cover source lanes")
    resolved = resolve_output_slots(configuration, lanes, resolved_slot_count)
    if resolved is None:
        transform = empty_output_transform(
            field,
            layout,
            "output_slot_count_unavailable",
        )
        facts = unresolved_facts(
            GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE,
            source_lane_authority_available=bool(lanes),
        )
        facts["scan_canvas_authority"] = (
            supported_assessment()
            if lanes
            else unavailable_assessment(
                GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE
            )
        )
        facts["output_slot_count"] = unavailable_assessment(
            GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE
        )
        return PhotoGeometryDetectionResult(
            None,
            (),
            empty_source_placement_selection(),
            (),
            transform,
            (),
            facts,
        )

    prepared = tuple(
        prepare_lane(
            field,
            lane,
            layout=layout,
            output_slot_count=count,
            measurement_slot_count=lane_measurement_capacity(
                configuration,
                lanes,
                lane,
            ),
            holder_layout_authority=resolved_slot_count.holder_layout_authority,
            configuration=configuration,
            content_observation=content_observation,
        )
        for lane, count, content_observation in zip(
            lanes,
            resolved.lane_output_slot_counts,
            content_observations,
            strict=True,
        )
    )
    materialization = materialize_source_placements(
        tuple(item.proposal for item in prepared),
    )
    materialization = bind_shared_source_geometry_before_selection(
        materialization
    )
    candidates = build_lane_candidate_reconstructions(
        field,
        prepared,
        materialization,
        content_observations,
        layout=layout,
        development_detail=development_detail,
    )
    selected = resolve_selected_source_output(
        field,
        prepared,
        candidates,
        layout=layout,
    )
    gate = build_reconstruction_gate_facts(
        field,
        resolved,
        selected.reconstructions,
        selected.selection,
        selected.lane_transforms,
        selected.budgets,
        layout=layout,
    )
    return PhotoGeometryDetectionResult(
        resolved_output_slots=resolved,
        lane_reconstructions=selected.reconstructions,
        source_placement_selection=selected.selection,
        output_slot_identities=output_slot_identities(lanes, resolved),
        source_transform_assessment=gate.source_transform,
        lane_transform_assessments=selected.lane_transforms,
        assessment_facts=gate.assessments,
    )
