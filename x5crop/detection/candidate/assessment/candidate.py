from __future__ import annotations

from ...context import DetectionContext
from ...evidence.content.frame_support import frame_content_evidence
from ...evidence.content.holder_texture import holder_texture_evidence
from ...evidence.content.preservation import content_preservation_evidence
from ...evidence.frame_coverage import frame_coverage_evidence
from ...evidence.frame_sequence import frame_sequence_evidence
from ...evidence.frame_topology import frame_topology_evidence
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.sequence_content_alignment import sequence_content_alignment_evidence
from ...evidence.partial_edge import partial_edge_safety_evidence
from ...physical.model import SequenceSolution
from ...physical.photo_size import frame_dimension_evidence
from ....domain import EvidenceState, MeasurementIdentity
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from .candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from .evidence_independence import evidence_independence_evidence
from .separator_support import separator_sequence_evidence


def _boundary_proof_paths(
    candidate: BuiltCandidate,
    evidence: CandidateEvidence,
) -> tuple[BoundaryProofPath, ...]:
    geometry = candidate.geometry
    boundary_by_side = {
        observation.side: observation
        for observation in geometry.boundary_observations
    }
    sequence_boundary_supported = bool(
        geometry.sequence_provenance.root_measurement
        not in {
            MeasurementIdentity.HOLDER_CANVAS,
            MeasurementIdentity.SAFETY_GEOMETRY_MODEL,
            MeasurementIdentity.REVIEW_ONLY_MODE,
        }
        and all(
            side in boundary_by_side
            and boundary_by_side[side].kind != "canvas_clip"
            for side in ("leading", "trailing")
        )
    )
    content_not_contradicted = bool(
        evidence.frame_coverage.state != EvidenceState.CONTRADICTED
        and evidence.content_preservation.state != EvidenceState.CONTRADICTED
    )
    common = bool(
        sequence_boundary_supported
        and evidence.frame_topology.state == EvidenceState.SUPPORTED
        and content_not_contradicted
        and evidence.frame_sequence.conservation.state
        != EvidenceState.CONTRADICTED
        and evidence.independence.state
        in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
    )
    separator_led = bool(
        geometry.count > 1
        and common
        and evidence.separator_sequence.state == EvidenceState.SUPPORTED
    )
    hard_anchor_count = evidence.separator_sequence.hard_count
    single_frame_physical_boundaries = bool(
        geometry.count == 1
        and sequence_boundary_supported
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and content_not_contradicted
    )
    geometry_led = bool(
        evidence.frame_topology.state == EvidenceState.SUPPORTED
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and (
            single_frame_physical_boundaries
            or (
                common
                and geometry.count > 1
                and hard_anchor_count >= 1
            )
        )
    )
    partial_occupancy_led = bool(
        geometry.strip_mode == "partial"
        and evidence.partial_edge_safety.state == EvidenceState.SUPPORTED
        and evidence.holder_occupancy.state == EvidenceState.SUPPORTED
        and common
    )
    return (
        BoundaryProofPath(
            "separator_led",
            EvidenceState.SUPPORTED
            if separator_led
            else EvidenceState.UNAVAILABLE,
            (
                "complete_hard_separator_sequence",
                "cross_axis_separator_pixel_paths",
                "frame_union_content_coverage",
            ),
        ),
        BoundaryProofPath(
            "geometry_led",
            EvidenceState.SUPPORTED
            if geometry_led
            else EvidenceState.UNAVAILABLE,
            (
                "physical_frame_dimensions",
                (
                    "calibrated_two_side_frame_boundaries"
                    if evidence.frame_dimensions.calibration_used
                    else "independent_two_side_frame_boundaries"
                    if single_frame_physical_boundaries
                    else "independent_separator_anchor"
                ),
            ),
        ),
        BoundaryProofPath(
            "partial_occupancy_led",
            EvidenceState.SUPPORTED
            if partial_occupancy_led
            else (
                EvidenceState.UNAVAILABLE
                if geometry.strip_mode == "partial"
                else EvidenceState.NOT_APPLICABLE
            ),
            (
                "partial_edge_content_preservation",
                "holder_occupancy",
                "resolved_frame_sequence",
            ),
        ),
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
    frame_sequence = frame_sequence_evidence(geometry)
    frame_topology = frame_topology_evidence(geometry.frames, geometry.count)
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
        occupancy,
    )
    preservation = content_preservation_evidence(
        content,
        alignment,
        partial_edge,
        coverage,
    )
    independence = evidence_independence_evidence(geometry)
    evidence = CandidateEvidence(
        frame_topology=frame_topology,
        frame_coverage=coverage,
        frame_sequence=frame_sequence,
        separator_sequence=sequence,
        frame_dimensions=frame_dimensions,
        frame_content=content,
        holder_texture=holder_texture,
        content_preservation=preservation,
        sequence_content_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    proof_paths = _boundary_proof_paths(candidate, evidence)
    diagnostics = list(candidate.build_diagnostics)
    diagnostics.extend(partial_edge.diagnostics)
    if alignment.overcontains_long_axis or alignment.overcontains_short_axis:
        diagnostics.append("sequence_span_overcontains_holder_area")
    if content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("frame_content_unavailable")
    if holder_texture.state == EvidenceState.CONTRADICTED:
        diagnostics.append("content_like_signal_in_holder_slack")
    gate = candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=evidence.frame_topology.state,
            content_preservation=evidence.content_preservation.state,
            photo_geometry=evidence.frame_dimensions.state,
            sequence_conservation=evidence.frame_sequence.conservation.state,
            evidence_independence=evidence.independence.state,
            proof_paths=proof_paths,
            diagnostics=tuple(diagnostics),
        )
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            gate=gate,
        ),
    )
