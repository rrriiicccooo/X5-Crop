from __future__ import annotations

from dataclasses import dataclass

from ..configuration.model import DetectionConfiguration
from ..domain import EvidenceState
from .candidate.assessment.candidate_gate import candidate_gate_assessment
from .candidate.assessment.model import CandidateGateAssessment
from .gate_checks import GateGap, TypedAssessment
from .photo_geometry.detector import reconstruct_photo_geometry
from .photo_geometry.template_runtime_model import PhotoGeometryDetectionResult
from .photo_geometry.output_model import (
    OutputFootprint,
    OutputSlotIdentity,
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
        if self.gate.passed and (
            self.geometry.resolved_output_slots is None
            or len(self.geometry.output_footprints)
            != self.geometry.resolved_output_slots.output_slot_count
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
    def output_footprints(self) -> tuple[OutputFootprint, ...]:
        return self.geometry.output_footprints

    @property
    def source_transform_assessment(self):
        return self.geometry.source_transform_assessment

    @property
    def output_transforms(self):
        return self.geometry.output_transforms

    @property
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )


def choose_detection(
    workspace: DetectionWorkspace,
    configuration: DetectionConfiguration,
) -> PhotoGeometryCandidate:
    geometry = reconstruct_photo_geometry(
        workspace.boundary_measurement_field,
        workspace.source_core.lanes,
        workspace.source_core.content_occupancy,
        layout=workspace.boundary_measurement_field.layout,
        configuration=configuration,
        resolved_slot_count=workspace.source_core.resolved_slot_count,
    )
    facts = dict(geometry.assessment_facts)
    if workspace.source_core.scan_canvas_state != EvidenceState.SUPPORTED:
        canvas_gap = GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE
        if "holder_full_count_unresolved" in workspace.source_core.incomplete_reasons:
            canvas_gap = GateGap.HOLDER_FULL_COUNT_UNRESOLVED
        elif "holder_identity_unresolved" in workspace.source_core.incomplete_reasons:
            canvas_gap = GateGap.HOLDER_IDENTITY_UNRESOLVED
        facts["scan_canvas_authority"] = TypedAssessment(
            workspace.source_core.scan_canvas_state,
            canvas_gap,
        )
    gate = candidate_gate_assessment(facts)
    return PhotoGeometryCandidate(
        source_core=workspace.source_core,
        geometry=geometry,
        gate=gate,
    )
