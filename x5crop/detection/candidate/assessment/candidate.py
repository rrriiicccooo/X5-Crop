from __future__ import annotations

from dataclasses import replace

from ...context import DetectionContext
from ...evidence.content.frame_support import frame_content_evidence
from ...evidence.content.holder_texture import holder_texture_evidence
from ...evidence.content.preservation import content_preservation_evidence
from ...evidence.frame_coverage import frame_coverage_evidence
from ...evidence.frame_sequence import frame_sequence_evidence
from ...evidence.holder_occupancy import holder_occupancy_evidence
from ...evidence.outer_alignment import outer_content_alignment_evidence
from ...evidence.partial_edge import partial_edge_safety_evidence
from ...evidence.state import EvidenceState
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from .base_scoring import base_physical_assessment
from .candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from .evidence_independence import evidence_independence_evidence
from .scoring import candidate_scores
from .separator_support import separator_sequence_evidence


def _boundary_proof_paths(
    candidate: BuiltCandidate,
    evidence: CandidateEvidence,
) -> tuple[BoundaryProofPath, ...]:
    geometry = candidate.geometry
    common = bool(
        evidence.frame_topology.state == EvidenceState.SUPPORTED
        and evidence.frame_coverage.state == EvidenceState.SUPPORTED
        and evidence.content_preservation.state == EvidenceState.SUPPORTED
        and evidence.frame_sequence.conservation.state
        != EvidenceState.CONTRADICTED
        and evidence.independence.state
        in {EvidenceState.SUPPORTED, EvidenceState.NOT_APPLICABLE}
    )
    separator_led = bool(
        geometry.source == "separator"
        and geometry.count > 1
        and common
        and evidence.separator_sequence.state == EvidenceState.SUPPORTED
        and evidence.separator_continuity.state == EvidenceState.SUPPORTED
    )
    hard_anchor_count = evidence.separator_sequence.hard_count
    single_frame_boundary_anchors = set(
        geometry.outer_provenance.boundary_anchors
    )
    single_frame_physical_boundaries = bool(
        geometry.count == 1
        and evidence.frame_dimensions.state == EvidenceState.SUPPORTED
        and geometry.outer_provenance.root_measurement != "content_guidance"
        and evidence.content_preservation.state == EvidenceState.SUPPORTED
        and (
            evidence.frame_dimensions.calibration_used
            or len(single_frame_boundary_anchors) >= 2
        )
    )
    geometry_led = bool(
        geometry.source == "separator"
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
        geometry.source == "separator"
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
    physical_spec = context.policy.physical_spec
    if candidate.geometry.format_id != physical_spec.format_id:
        raise ValueError("candidate and detection context format do not match")
    base = base_physical_assessment(
        context.measurement_cache.gray_work,
        candidate,
        physical_spec,
        context.scan_calibration,
        context.policy.scoring,
        context.policy.separator.hard_gap_trust,
    )
    geometry = replace(
        candidate.geometry,
        separators=base.separator_continuity.observations,
    )
    candidate = replace(candidate, geometry=geometry)
    coverage = frame_coverage_evidence(
        geometry.holder_span,
        geometry.film_span,
        geometry.work_frames,
        physical_spec,
        context.measurement_cache,
        context.policy.content,
    )
    frame_sequence = frame_sequence_evidence(geometry, physical_spec)
    content = frame_content_evidence(
        geometry,
        context.measurement_cache,
        context.policy.content,
    )
    holder_texture = holder_texture_evidence(
        geometry,
        context.measurement_cache,
        content,
        context.policy.content.evidence,
    )
    alignment = outer_content_alignment_evidence(
        geometry,
        context.measurement_cache,
        context.policy.outer.alignment_evidence,
    )
    sequence = separator_sequence_evidence(
        geometry,
        base.separator_continuity,
    )
    occupancy = holder_occupancy_evidence(
        layout=geometry.layout,
        strip_mode=geometry.strip_mode,
        count=geometry.count,
        holder_span=geometry.holder_span,
        film_span=geometry.film_span,
        work_frames=geometry.work_frames,
        separators=geometry.separators,
        physical_spec=physical_spec,
        content_support_available=content.support_available,
        frame_coverage=coverage,
        frame_dimensions=base.frame_dimensions,
        calibration=context.scan_calibration,
    )
    partial_edge = partial_edge_safety_evidence(
        geometry,
        coverage,
        base.frame_dimensions,
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
        frame_topology=base.frame_topology,
        frame_coverage=coverage,
        frame_sequence=frame_sequence,
        separator_sequence=sequence,
        separator_continuity=base.separator_continuity,
        frame_dimensions=base.frame_dimensions,
        frame_content=content,
        holder_texture=holder_texture,
        content_preservation=preservation,
        outer_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    proof_paths = _boundary_proof_paths(candidate, evidence)
    diagnostics = list(candidate.build_diagnostics)
    diagnostics.extend(partial_edge.diagnostics)
    if alignment.overcontains_long_axis or alignment.overcontains_short_axis:
        diagnostics.append("film_span_overcontains_holder_area")
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
    scores = candidate_scores(
        evidence,
        geometry.source,
        base.confidence,
        context.policy.scoring,
        context.policy.content.support,
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            scores=scores,
            gate=gate,
            diagnostics=tuple(sorted(set(diagnostics))),
        ),
    )
