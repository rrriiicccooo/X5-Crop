from __future__ import annotations

from ....domain import EvidenceState, PixelInterval
from ...evidence.content.frame_support import FrameContentEvidence
from ...evidence.content.holder_texture import HolderTextureEvidence
from ...evidence.content.preservation import ContentPreservationEvidence
from ...evidence.frame_coverage import FrameCoverageEvidence
from ...evidence.frame_sequence import FrameSequenceEvidence
from ...evidence.frame_topology import FrameTopologyEvidence
from ...evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from ...evidence.partial_edge import PartialEdgeSafetyEvidence
from ...evidence.sequence_content_alignment import (
    SequenceContentAlignmentEvidence,
)
from ...physical.boundary import HolderOcclusionEvidence
from ...physical.model import ReviewOnlyGeometry
from ...physical.photo_size import FrameDimensionEvidence
from ...physical.spacing import SequenceConservationEvidence
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
from .evidence_independence import EvidenceIndependenceEvidence
from .quality import evidence_quality
from .separator_support import SeparatorSequenceEvidence


_REVIEW_ONLY_EVIDENCE_REASON = "review_only_geometry_not_measured"


def assess_review_only_candidate(
    candidate: BuiltCandidate,
) -> AssessedCandidate:
    geometry = candidate.geometry
    if not isinstance(geometry, ReviewOnlyGeometry):
        raise ValueError("review-only assessment requires review-only geometry")

    unavailable = EvidenceState.UNAVAILABLE
    zero = PixelInterval.exact(0.0)
    expected_boundaries = max(0, geometry.count - 1)
    nominal = geometry.frame_dimension_prior.frame_size_options_mm[0]
    topology = FrameTopologyEvidence(
        state=unavailable,
        expected_count=geometry.count,
        actual_count=0,
        count_matches=False,
        extent_valid=False,
        order_valid=False,
        overlap_absent=False,
        invalid_extent_indexes=(),
        order_invalid_indexes=(),
        overlap_pairs=(),
        boxes=(),
    )
    coverage = FrameCoverageEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        holder_long_axis_interval=(
            geometry.holder_span.box.left,
            geometry.holder_span.box.right,
        ),
        visible_sequence_interval=(
            geometry.visible_sequence_span.box.left,
            geometry.visible_sequence_span.box.right,
        ),
        frame_intervals=(),
        content_runs=(),
        uncovered_content=(),
        unexplained_content_region_count=0,
    )
    frame_sequence = FrameSequenceEvidence(
        holder_occlusion=HolderOcclusionEvidence.unavailable(),
        spacings=(),
        conservation=SequenceConservationEvidence(
            state=unavailable,
            reason=_REVIEW_ONLY_EVIDENCE_REASON,
            visible_length_px=zero,
            holder_occlusion_px=zero,
            frame_total_px=zero,
            spacing_total_px=zero,
            physical_sequence_px=zero,
        ),
    )
    separator_sequence = SeparatorSequenceEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        expected_count=expected_boundaries,
        hard_count=0,
        dimension_constrained_count=0,
        hard_boundary_indexes=(),
        missing_boundary_indexes=tuple(range(1, expected_boundaries + 1)),
        hard_tonal_evidence=(),
    )
    frame_dimensions = FrameDimensionEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        nominal_width_mm=float(nominal[0]),
        nominal_height_mm=float(nominal[1]),
        nominal_aspect=float(nominal[0]) / float(nominal[1]),
        photo_widths_px=(),
        photo_width_cv=None,
        separator_widths_px=(),
        separator_width_cv=None,
        observed_width_mm=None,
        observed_height_mm=None,
        observed_aspect=None,
        aspect_error_ratio=None,
        dimension_residual_max=None,
        calibration_used=False,
    )
    frame_content = FrameContentEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        threshold=None,
        median_mean=None,
        median_coverage=None,
        observations=(),
        composite="not_measured",
    )
    holder_texture = HolderTextureEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        regions=(),
        content_holder_mean_contrast=None,
        content_holder_coverage_contrast=None,
    )
    partial_edge = PartialEdgeSafetyEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        boundary_support=False,
        hard_separator_count=0,
        expected_separator_count=expected_boundaries,
        content_coverage_state=unavailable,
        holder_occupancy_state=unavailable,
        complete_underfilled_strip=False,
        diagnostics=(),
    )
    preservation = ContentPreservationEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        uncovered_content=(),
        boundary_contact_frame_indexes=(),
        partial_edge_state=unavailable,
    )
    alignment = SequenceContentAlignmentEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        visible_sequence_span=geometry.visible_sequence_span.box,
        content_span=None,
        content_outside_sides=(),
        overcontains_long_axis=False,
        overcontains_short_axis=False,
        leading_slack_px=0,
        trailing_slack_px=0,
        top_slack_px=0,
        bottom_slack_px=0,
    )
    completeness = StripCompletenessEvidence(
        frame_count_complete=False,
        frame_sequence_complete=False,
        count=geometry.count,
        nominal_count=geometry.count,
        valid_frame_count=0,
        expected_internal_boundary_count=expected_boundaries,
        resolved_boundary_count=0,
        independent_separator_count=0,
    )
    occupancy = HolderOccupancyEvidence(
        state=unavailable,
        strip_completeness=completeness,
        nominal_frame_total_mm=None,
        observed_sequence_span_px=float(
            geometry.visible_sequence_span.box.width
        ),
        leading_slack_px=0.0,
        trailing_slack_px=0.0,
        leading_slack_mm=None,
        trailing_slack_mm=None,
        holder_fill_ratio=0.0,
        occupancy_status="unknown",
        complete_underfilled_strip=False,
        content_support_available=False,
        frame_coverage_state=unavailable,
        photo_dimensions_stable=False,
        holder_span=geometry.holder_span,
        visible_sequence_span=geometry.visible_sequence_span,
        calibration_used=False,
    )
    independence = EvidenceIndependenceEvidence(
        state=unavailable,
        reason=_REVIEW_ONLY_EVIDENCE_REASON,
        sequence_root_measurement=geometry.sequence_provenance.root_measurement,
        supporting_root_measurements=(),
        cyclic_measurements=(),
    )
    evidence = CandidateEvidence(
        frame_topology=topology,
        frame_coverage=coverage,
        frame_sequence=frame_sequence,
        separator_sequence=separator_sequence,
        frame_dimensions=frame_dimensions,
        frame_content=frame_content,
        holder_texture=holder_texture,
        content_preservation=preservation,
        sequence_content_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial_edge,
        independence=independence,
    )
    proof_paths = tuple(
        BoundaryProofPath(code, EvidenceState.NOT_APPLICABLE, ())
        for code in (
            "separator_led",
            "geometry_led",
            "partial_occupancy_led",
        )
    )
    diagnostics = (*candidate.build_diagnostics, _REVIEW_ONLY_EVIDENCE_REASON)
    gate = candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=unavailable,
            content_preservation=unavailable,
            photo_geometry=unavailable,
            sequence_conservation=unavailable,
            evidence_independence=unavailable,
            proof_paths=proof_paths,
            diagnostics=diagnostics,
        )
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            quality=evidence_quality(
                evidence,
                proof_paths,
                residuals=geometry.residuals,
            ),
            gate=gate,
            diagnostics=tuple(sorted(set(diagnostics))),
        ),
    )
