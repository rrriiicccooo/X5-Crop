from __future__ import annotations

from ...context import DetectionContext
from ...evidence.content.photo_content import photo_content_evidence
from ...evidence.content.internal_boundaries import (
    inter_photo_boundary_preservation_evidence,
)
from ...evidence.separator_sequence import separator_sequence_evidence
from ...evidence.holder_boundary import holder_boundary_evidence
from ...evidence.photo_aperture_coverage import photo_aperture_coverage_evidence
from ...evidence.aperture_sequence import sequence_conservation_for_geometry
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.content.external_boundaries import (
    external_aperture_preservation_evidence,
)
from ...evidence.partial_edge import partial_edge_safety_evidence
from ...evidence.physical_scale import physical_scale_observations
from ...physical.model import PhotoSequenceSolution
from ...physical.photo_size import frame_dimension_evidence
from ....domain import EvidenceState
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    boundary_proof_paths_for_geometry,
)
from .candidate_gate import candidate_gate_assessment
from .model import (
    CandidateGateAssessment,
    CandidateGateInput,
)
from .evidence_independence import evidence_independence_evidence


def candidate_gate_for_evidence(
    candidate: BuiltCandidate,
    evidence: CandidateEvidence,
    diagnostics: tuple[str, ...] = (),
) -> CandidateGateAssessment:
    if not isinstance(candidate.geometry, PhotoSequenceSolution):
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
    if not isinstance(geometry, PhotoSequenceSolution):
        raise ValueError("standard candidate assessment requires sequence geometry")
    sequence_conservation = sequence_conservation_for_geometry(geometry)
    frame_dimensions = frame_dimension_evidence(
        geometry,
        context.scan_calibration,
    )
    coverage = photo_aperture_coverage_evidence(
        geometry,
        context.measurement_cache,
        context.configuration.content,
    )
    content = photo_content_evidence(
        geometry,
        context.measurement_cache,
        context.configuration.content,
    )
    internal_boundaries = inter_photo_boundary_preservation_evidence(
        geometry.count,
        geometry.photo_apertures,
        geometry.inter_photo_spacings,
        content,
    )
    holder_boundary = holder_boundary_evidence(
        geometry,
        context.measurement_cache.image_statistics.edge_texture_limit,
    )
    candidate_scale = physical_scale_observations(
        geometry,
        holder_boundary,
    )
    external_preservation = external_aperture_preservation_evidence(
        geometry,
        context.measurement_cache,
        context.configuration.content.evidence,
    )
    separator_sequence = separator_sequence_evidence(geometry)
    occupancy = holder_occupancy_evidence(
        count=geometry.count,
        holder_span=geometry.holder_span,
        photo_apertures=geometry.photo_apertures,
        separator_assignments=geometry.separator_assignments,
        physical_spec=physical_spec,
        content_support_available=content.support_available,
        photo_aperture_coverage=coverage,
        frame_dimensions=frame_dimensions,
    )
    partial_edge = partial_edge_safety_evidence(
        geometry,
        coverage,
        frame_dimensions,
        content,
    )
    independence = evidence_independence_evidence(geometry)
    evidence = CandidateEvidence(
        photo_aperture_coverage=coverage,
        sequence_conservation=sequence_conservation,
        separator_sequence=separator_sequence,
        frame_dimensions=frame_dimensions,
        photo_content=content,
        inter_photo_boundary_preservation=internal_boundaries,
        holder_boundary=holder_boundary,
        physical_scale_observations=candidate_scale,
        external_aperture_preservation=external_preservation,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    diagnostics = list(candidate.build_diagnostics)
    diagnostics.extend(partial_edge.diagnostics)
    if content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("photo_content_unavailable")
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
