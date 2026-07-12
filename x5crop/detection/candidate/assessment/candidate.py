from __future__ import annotations

from ...context import DetectionContext
from ....constants import CANDIDATE_SOURCE_FRAME_SEQUENCE
from ...evidence.content.frame_support import frame_content_evidence
from ...evidence.content.holder_texture import holder_texture_evidence
from ...evidence.content.preservation import content_preservation_evidence
from ...evidence.frame_coverage import frame_coverage_evidence
from ...evidence.frame_sequence import frame_sequence_evidence
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.sequence_content_alignment import sequence_content_alignment_evidence
from ...evidence.partial_edge import partial_edge_safety_evidence
from x5crop.domain import EvidenceState
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from .physical_evidence import measure_core_physical_evidence
from .candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from .evidence_independence import evidence_independence_evidence
from .quality import evidence_quality
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
            "holder_canvas",
            "safety_geometry_model",
            "review_only_mode",
        }
        and all(
            side in boundary_by_side
            and boundary_by_side[side].kind != "canvas_clip"
            for side in ("leading", "trailing")
        )
    )
    common = bool(
        sequence_boundary_supported
        and evidence.frame_topology.state == EvidenceState.SUPPORTED
        and evidence.frame_coverage.state == EvidenceState.SUPPORTED
        and evidence.content_preservation.state == EvidenceState.SUPPORTED
        and evidence.frame_sequence.conservation.state
        != EvidenceState.CONTRADICTED
        and evidence.independence.state
        in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
    )
    separator_led = bool(
        geometry.source == CANDIDATE_SOURCE_FRAME_SEQUENCE
        and geometry.count > 1
        and common
        and evidence.separator_sequence.state == EvidenceState.SUPPORTED
        and evidence.separator_continuity.state == EvidenceState.SUPPORTED
    )
    hard_anchor_count = evidence.separator_sequence.hard_count
    measured_single_frame_boundaries = {
        observation.side
        for observation in geometry.boundary_observations
        if observation.kind != "canvas_clip"
    }
    single_frame_physical_boundaries = bool(
        geometry.count == 1
        and sequence_boundary_supported
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and evidence.content_preservation.state == EvidenceState.SUPPORTED
        and (
            evidence.frame_dimensions.calibration_used
            or len(measured_single_frame_boundaries) >= 2
        )
    )
    geometry_led = bool(
        geometry.source == CANDIDATE_SOURCE_FRAME_SEQUENCE
        and evidence.frame_topology.state == EvidenceState.SUPPORTED
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
    count_hypothesis = candidate.count_hypothesis
    partial_occupancy_led = bool(
        geometry.source == CANDIDATE_SOURCE_FRAME_SEQUENCE
        and geometry.strip_mode == "partial"
        and count_hypothesis is not None
        and count_hypothesis.allowed_by_physical_spec
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
                "cross_axis_separator_continuity",
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
    frame_sequence = frame_sequence_evidence(geometry)
    core = measure_core_physical_evidence(
        context.measurement_cache.gray_work,
        candidate,
        physical_spec,
        context.scan_calibration,
        context.measurement_cache.image_statistics,
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
    sequence = separator_sequence_evidence(
        geometry,
        core.separator_continuity,
    )
    occupancy = holder_occupancy_evidence(
        layout=geometry.layout,
        strip_mode=geometry.strip_mode,
        count=geometry.count,
        holder_span=geometry.holder_span,
        visible_sequence_span=geometry.visible_sequence_span,
        frames=geometry.frames,
        frame_boundaries=geometry.frame_boundaries,
        separator_assignments=geometry.separator_assignments,
        physical_spec=physical_spec,
        content_support_available=content.support_available,
        frame_coverage=coverage,
        frame_dimensions=core.frame_dimensions,
        calibration=context.scan_calibration,
    )
    partial_edge = partial_edge_safety_evidence(
        geometry,
        coverage,
        core.frame_dimensions,
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
        frame_topology=core.frame_topology,
        frame_coverage=coverage,
        frame_sequence=frame_sequence,
        separator_sequence=sequence,
        separator_continuity=core.separator_continuity,
        frame_dimensions=core.frame_dimensions,
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
    quality = evidence_quality(
        evidence,
        proof_paths,
        residuals=geometry.residuals,
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            quality=quality,
            gate=gate,
            diagnostics=tuple(sorted(set(diagnostics))),
        ),
    )
