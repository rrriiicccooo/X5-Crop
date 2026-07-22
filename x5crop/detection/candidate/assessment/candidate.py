from __future__ import annotations

from ...context import DetectionContext
from ...evidence.content.frame_content import frame_content_evidence
from ...evidence.content.internal_frame_boundaries import (
    internal_frame_boundary_preservation_evidence,
    measure_internal_boundary_content_continuity,
)
from ...evidence.separator_sequence import separator_sequence_evidence
from ...evidence.holder_boundary import holder_boundary_evidence
from ...evidence.frame_coverage import frame_coverage_evidence
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.content.external_frame_boundaries import (
    external_frame_preservation_evidence,
)
from ...evidence.partial_edge import partial_edge_safety_evidence
from ...evidence.frame_scale import frame_scale_observations
from ...evidence.frame_slot_topology import frame_slot_topology_evidence
from ...physical.model import FrameSequenceSolution
from ...physical.frame_dimensions import frame_dimension_evidence
from ....domain import EvidenceState
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    sequence_proof_paths_for_geometry,
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
    if not isinstance(candidate.geometry, FrameSequenceSolution):
        raise ValueError("standard CandidateGate requires sequence geometry")
    return candidate_gate_assessment(
        CandidateGateInput(
            frame_slot_topology=evidence.frame_slot_topology.state,
            content_preservation=evidence.content_preservation_state,
            frame_dimensions=evidence.frame_dimensions.state,
            evidence_independence=evidence.independence.state,
            proof_paths=sequence_proof_paths_for_geometry(
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
    if not isinstance(geometry, FrameSequenceSolution):
        raise ValueError("standard candidate assessment requires sequence geometry")
    frame_dimensions = frame_dimension_evidence(geometry)
    coverage = frame_coverage_evidence(
        geometry,
        context.workspace.measurement_cache,
        context.configuration.content,
    )
    content = frame_content_evidence(
        geometry,
        context.workspace.measurement_cache,
        context.configuration.content,
    )
    content_continuity = measure_internal_boundary_content_continuity(
        geometry.frame_slots,
        content,
        coverage,
        context.workspace.measurement_cache.content_evidence_float_work,
        context.workspace.measurement_cache.gray_work,
        context.workspace.measurement_cache.image_statistics,
        context.configuration.content.evidence,
    )
    internal_boundaries = internal_frame_boundary_preservation_evidence(
        geometry.frame_slots,
        geometry.inter_frame_spacings,
        content_continuity,
    )
    holder_boundary = holder_boundary_evidence(
        geometry,
        context.workspace.measurement_cache.image_statistics.edge_texture_limit,
    )
    candidate_scale = frame_scale_observations(geometry)
    external_preservation = external_frame_preservation_evidence(
        geometry,
        context.workspace.measurement_cache,
        context.configuration.content.evidence,
        coverage,
    )
    separator_sequence = separator_sequence_evidence(geometry)
    occupancy = holder_occupancy_evidence(
        count=geometry.count,
        holder_safety=geometry.holder_safety,
        frame_slots=geometry.frame_slots,
        separator_assignments=geometry.separator_assignments,
        physical_spec=physical_spec,
        content_support_available=content.support_available,
        frame_coverage=coverage,
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
        frame_slot_topology=frame_slot_topology_evidence(geometry),
        frame_coverage=coverage,
        separator_sequence=separator_sequence,
        frame_dimensions=frame_dimensions,
        frame_content=content,
        internal_frame_boundary_preservation=internal_boundaries,
        holder_boundary=holder_boundary,
        frame_scale_observations=candidate_scale,
        external_frame_preservation=external_preservation,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    diagnostics = list(candidate.build_diagnostics)
    diagnostics.extend(partial_edge.diagnostics)
    if content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("frame_content_unavailable")
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
