from __future__ import annotations

from ...context import DetectionContext
from ...evidence.content.frame_support import frame_content_evidence
from ...evidence.content.holder_texture import holder_texture_evidence
from ...evidence.frame_coverage import frame_coverage_evidence
from ...evidence.frame_sequence import sequence_conservation_for_geometry
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.sequence_content_alignment import sequence_content_alignment_evidence
from ...evidence.partial_edge import partial_edge_safety_evidence
from ...physical.model import SequenceSolution
from ...physical.photo_size import frame_dimension_evidence
from ....domain import EvidenceState
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    boundary_proof_paths_for_geometry,
)
from .candidate_gate import (
    CandidateGateAssessment,
    CandidateGateInput,
    candidate_gate_assessment,
)
from .evidence_independence import evidence_independence_evidence
from .separator_support import separator_sequence_evidence


def candidate_gate_for_evidence(
    candidate: BuiltCandidate,
    evidence: CandidateEvidence,
    diagnostics: tuple[str, ...] = (),
) -> CandidateGateAssessment:
    if not isinstance(candidate.geometry, SequenceSolution):
        raise ValueError("standard CandidateGate requires sequence geometry")
    return candidate_gate_assessment(
        CandidateGateInput(
            content_preservation=evidence.content_preservation_state,
            photo_geometry=evidence.frame_dimensions.state,
            sequence_conservation=evidence.sequence_conservation.state,
            evidence_independence=evidence.independence.state,
            proof_paths=boundary_proof_paths_for_geometry(
                candidate.geometry,
                evidence,
            ),
            diagnostics=diagnostics,
        )
    )


def assess_candidate(
    candidate: BuiltCandidate,
    context: DetectionContext,
) -> AssessedCandidate:
    physical_spec = context.configuration.physical_spec
    if candidate.geometry.format_id != physical_spec.format_id:
        raise ValueError("candidate and detection context format do not match")
    geometry = candidate.geometry
    if not isinstance(geometry, SequenceSolution):
        raise ValueError("standard candidate assessment requires sequence geometry")
    sequence_conservation = sequence_conservation_for_geometry(geometry)
    frame_dimensions = frame_dimension_evidence(
        geometry,
        context.scan_calibration,
    )
    coverage = frame_coverage_evidence(
        geometry.holder_span,
        geometry.visible_sequence_span,
        geometry.frames,
        context.measurement_cache,
        context.configuration.content,
    )
    content = frame_content_evidence(
        geometry,
        context.measurement_cache,
        context.configuration.content,
    )
    holder_texture = holder_texture_evidence(
        geometry,
        context.measurement_cache,
        content,
    )
    alignment = sequence_content_alignment_evidence(
        geometry,
        context.measurement_cache,
        context.configuration.content.evidence,
    )
    sequence = separator_sequence_evidence(geometry)
    occupancy = holder_occupancy_evidence(
        layout=geometry.layout,
        count=geometry.count,
        holder_span=geometry.holder_span,
        visible_sequence_span=geometry.visible_sequence_span,
        frames=geometry.frames,
        frame_boundaries=geometry.frame_boundaries,
        separator_assignments=geometry.separator_assignments,
        physical_spec=physical_spec,
        content_support_available=content.support_available,
        frame_coverage=coverage,
        frame_dimensions=frame_dimensions,
        calibration=context.scan_calibration,
    )
    partial_edge = partial_edge_safety_evidence(
        geometry,
        coverage,
        frame_dimensions,
        content,
    )
    independence = evidence_independence_evidence(geometry)
    evidence = CandidateEvidence(
        frame_coverage=coverage,
        sequence_conservation=sequence_conservation,
        separator_sequence=sequence,
        frame_dimensions=frame_dimensions,
        frame_content=content,
        holder_texture=holder_texture,
        sequence_content_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    diagnostics = list(candidate.build_diagnostics)
    diagnostics.extend(partial_edge.diagnostics)
    if alignment.overcontains_long_axis or alignment.overcontains_short_axis:
        diagnostics.append("sequence_span_overcontains_holder_area")
    if content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("frame_content_unavailable")
    if holder_texture.state == EvidenceState.CONTRADICTED:
        diagnostics.append("content_like_signal_in_holder_slack")
    gate = candidate_gate_for_evidence(
        candidate,
        evidence,
        tuple(diagnostics),
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=gate,
        ),
    )
