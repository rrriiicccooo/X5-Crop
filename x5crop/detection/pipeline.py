from __future__ import annotations

from dataclasses import dataclass

from ..configuration.model import DetectionConfiguration
from ..domain import EvidenceState
from .candidate.assessment.candidate_gate import candidate_gate_assessment
from .candidate.assessment.model import CandidateGateAssessment
from .photo_geometry.detector import (
    PhotoGeometryDetectionResult,
    reconstruct_photo_geometry,
)
from .photo_geometry.model import (
    OutputSlotIdentity,
    ResolvedOutputGeometry,
    ResolvedOutputSlots,
)
from .source_core import SourceCoreEvidence
from .workspace import DetectionWorkspace


@dataclass(frozen=True)
class PhotoGeometryCandidate:
    source_core: SourceCoreEvidence
    geometry: PhotoGeometryDetectionResult
    gate: CandidateGateAssessment

    def __post_init__(self) -> None:
        if (
            self.gate.passed
            and (
                self.geometry.resolved_output_slots is None
                or len(self.geometry.resolved_output_geometries)
                != self.geometry.resolved_output_slots.output_slot_count
            )
        ):
            raise ValueError(
                "passing photo-geometry candidate requires every output slot"
            )

    @property
    def resolved_output_slots(self) -> ResolvedOutputSlots | None:
        return self.geometry.resolved_output_slots

    @property
    def output_slot_identities(self) -> tuple[OutputSlotIdentity, ...]:
        return self.geometry.output_slot_identities

    @property
    def resolved_output_geometries(
        self,
    ) -> tuple[ResolvedOutputGeometry, ...]:
        return self.geometry.resolved_output_geometries

    @property
    def transform_assessment(self):
        return self.geometry.transform_assessment

    @property
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )


def _content_support_is_covered(
    workspace: DetectionWorkspace,
    geometry: PhotoGeometryDetectionResult,
) -> bool:
    layout = workspace.boundary_measurement_field.layout
    lane_by_id = {
        lane.domain.lane_id: lane
        for lane in workspace.source_core.lanes
    }
    for lane in geometry.lane_reconstructions:
        solution = lane.solution
        if solution is None:
            continue
        envelope_by_ordinal = {
            item.lane_ordinal: item.source_protected_box
            for item in lane.resolved_output_geometries
        }
        source_lane = lane_by_id[lane.lane_id]
        component_by_id = {
            item.component_id: item
            for item in source_lane.content.components
        }
        for state in solution.selected_states:
            photo = state.photo_geometry
            if photo is None:
                continue
            envelope = envelope_by_ordinal.get(state.lane_ordinal)
            if envelope is None:
                return False
            for component_id in photo.content_component_ids:
                component = component_by_id.get(component_id)
                if component is None:
                    return False
                footprint = component.footprint
                work_x = (footprint.left + footprint.right) / 2.0
                work_y = (footprint.top + footprint.bottom) / 2.0
                source_x, source_y = (
                    (work_x, work_y)
                    if layout == "horizontal"
                    else (work_y, work_x)
                )
                if (
                    source_x < envelope.left
                    or source_y < envelope.top
                    or source_x >= envelope.right
                    or source_y >= envelope.bottom
                ):
                    return False
    return True


def _has_code(
    result: PhotoGeometryDetectionResult,
    *tokens: str,
) -> bool:
    return any(
        any(token in code for token in tokens)
        for code in result.unresolved_codes
    )


def choose_detection(
    workspace: DetectionWorkspace,
    configuration: DetectionConfiguration,
    lane_configuration: DetectionConfiguration | None,
) -> PhotoGeometryCandidate:
    geometry = reconstruct_photo_geometry(
        workspace.boundary_measurement_field,
        workspace.source_core.lanes,
        layout=workspace.boundary_measurement_field.layout,
        configuration=configuration,
        lane_configuration=lane_configuration,
    )
    resolved = geometry.resolved_output_slots
    output_count_supported = (
        resolved is not None
        and len(geometry.output_slot_identities)
        == resolved.output_slot_count
    )
    output_geometry_complete = (
        output_count_supported
        and len(geometry.resolved_output_geometries)
        == resolved.output_slot_count
    )
    ordinal_risk = _has_code(
        geometry,
        "sequence_translation_unresolved",
        "sequence_aperture_or_phase_unresolved",
        "sequence_geometry_competition_unresolved",
        "complete_sequence_state_count_exceeds_two",
        "grid_slot_translation_unresolved",
    )
    ownership_risk = _has_code(
        geometry,
        "ownership",
        "frame_geometry_competition_unresolved",
    )
    source_geometry_risk = _has_code(
        geometry,
        "measurement_unavailable",
        "photo_geometry_unavailable",
        "observed_non_dominated_count_exceeds_two",
    )
    containment_risk = _has_code(
        geometry,
        "known_content",
    )
    containment_supported = (
        output_geometry_complete
        and not containment_risk
        and _content_support_is_covered(workspace, geometry)
    )
    gate = candidate_gate_assessment(
        scan_canvas_state=workspace.source_core.scan_canvas_state,
        source_content_state=workspace.source_core.content_state,
        # Grid ordering covers every pre-registered tile.  Pixel query
        # failures are mapped to the geometry/containment facts they affect.
        grid_search_coverage_state=(
            EvidenceState.SUPPORTED
            if geometry.lane_reconstructions
            else EvidenceState.UNAVAILABLE
        ),
        output_slot_count_state=(
            EvidenceState.SUPPORTED
            if output_count_supported
            else EvidenceState.CONTRADICTED
        ),
        slot_ordinal_state=(
            EvidenceState.CONTRADICTED
            if ordinal_risk
            else EvidenceState.SUPPORTED
            if output_count_supported
            else EvidenceState.UNAVAILABLE
        ),
        slot_ownership_state=(
            EvidenceState.CONTRADICTED
            if ownership_risk
            else EvidenceState.SUPPORTED
            if output_geometry_complete
            else EvidenceState.UNAVAILABLE
        ),
        known_content_containment_state=(
            EvidenceState.SUPPORTED
            if containment_supported
            else EvidenceState.CONTRADICTED
            if workspace.source_core.content_state
            == EvidenceState.SUPPORTED
            else EvidenceState.UNAVAILABLE
        ),
        source_lane_geometry_state=(
            EvidenceState.CONTRADICTED
            if source_geometry_risk
            else EvidenceState.SUPPORTED
            if output_geometry_complete
            else EvidenceState.UNAVAILABLE
        ),
        output_protection_state=(
            EvidenceState.SUPPORTED
            if output_geometry_complete
            else EvidenceState.CONTRADICTED
        ),
        output_transform_state=geometry.transform_assessment.state,
    )
    return PhotoGeometryCandidate(
        source_core=workspace.source_core,
        geometry=geometry,
        gate=gate,
    )
