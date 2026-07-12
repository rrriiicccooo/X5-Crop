from __future__ import annotations

from dataclasses import replace

from ...evidence.content.frame_support import (
    FrameContentEvidence,
    FrameContentObservation,
)
from ...evidence.content.holder_texture import HolderTextureEvidence
from ...evidence.content.preservation import ContentPreservationEvidence
from ...evidence.frame_coverage import FrameCoverageEvidence
from ...evidence.frame_sequence import FrameSequenceEvidence
from ...evidence.frame_topology import FrameTopologyEvidence
from ...evidence.holder_occupancy import (
    HolderOccupancyEvidence,
    StripCompletenessEvidence,
)
from ...evidence.sequence_content_alignment import SequenceContentAlignmentEvidence
from ...evidence.partial_edge import PartialEdgeSafetyEvidence
from x5crop.domain import EvidenceState, FrameBoundaryReference
from ...physical.photo_size import FrameDimensionEvidence
from x5crop.domain import PixelInterval
from ...physical.spacing import SequenceConservationEvidence
from ...physical.model import DualLaneSolution
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
from .separator_support import SeparatorSequenceEvidence


def _combined_state(states: tuple[EvidenceState, ...]) -> EvidenceState:
    if any(state == EvidenceState.CONTRADICTED for state in states):
        return EvidenceState.CONTRADICTED
    if states and all(state == EvidenceState.SUPPORTED for state in states):
        return EvidenceState.SUPPORTED
    return EvidenceState.UNAVAILABLE


def assess_dual_lane_candidate(
    candidate: BuiltCandidate,
    lanes: tuple[AssessedCandidate, ...],
    *,
    lane_geometry_resolved: tuple[bool, ...],
) -> AssessedCandidate:
    geometry = candidate.geometry
    if not isinstance(geometry, DualLaneSolution):
        raise ValueError("dual-lane assessment requires dual-lane geometry")
    if len(lane_geometry_resolved) != len(lanes):
        raise ValueError("dual-lane assessment requires one resolution per lane")
    topology_state = _combined_state(
        tuple(lane.assessment.evidence.frame_topology.state for lane in lanes)
    )
    topology = FrameTopologyEvidence(
        state=topology_state,
        measurement_scope="lane_composition",
        expected_count=geometry.count,
        actual_count=len(geometry.frames),
        count_matches=len(geometry.frames) == geometry.count,
        extent_valid=all(frame.valid() for frame in geometry.frames),
        order_valid=topology_state == EvidenceState.SUPPORTED,
        overlap_absent=topology_state == EvidenceState.SUPPORTED,
        invalid_extent_indexes=(),
        order_invalid_indexes=(),
        overlap_pairs=(),
        boxes=geometry.frames,
    )
    coverage_state = _combined_state(
        tuple(lane.assessment.evidence.frame_coverage.state for lane in lanes)
    )
    coverage = FrameCoverageEvidence(
        state=coverage_state,
        reason=(
            "all_lane_content_covered"
            if coverage_state == EvidenceState.SUPPORTED
            else "lane_content_coverage_unresolved"
        ),
        holder_long_axis_interval=(
            geometry.holder_span.box.left,
            geometry.holder_span.box.right,
        ),
        visible_sequence_interval=(
            geometry.visible_sequence_span.box.left,
            geometry.visible_sequence_span.box.right,
        ),
        frame_intervals=tuple(
            interval
            for lane in lanes
            for interval in lane.assessment.evidence.frame_coverage.frame_intervals
        ),
        content_runs=tuple(
            interval
            for lane in lanes
            for interval in lane.assessment.evidence.frame_coverage.content_runs
        ),
        uncovered_content=tuple(
            interval
            for lane in lanes
            for interval in lane.assessment.evidence.frame_coverage.uncovered_content
        ),
        unexplained_content_region_count=sum(
            lane.assessment.evidence.frame_coverage.unexplained_content_region_count
            for lane in lanes
        ),
    )
    expected_separators = sum(
        lane.assessment.evidence.separator_sequence.expected_count for lane in lanes
    )
    hard_boundaries = tuple(
        FrameBoundaryReference(lane_index, reference.boundary_index)
        for lane_index, lane in enumerate(lanes, start=1)
        for reference in lane.assessment.evidence.separator_sequence.hard_boundaries
    )
    missing_boundaries = tuple(
        FrameBoundaryReference(lane_index, reference.boundary_index)
        for lane_index, lane in enumerate(lanes, start=1)
        for reference in lane.assessment.evidence.separator_sequence.missing_boundaries
    )
    sequence = SeparatorSequenceEvidence(
        expected_count=expected_separators,
        hard_count=len(hard_boundaries),
        dimension_constrained_count=sum(
            lane.assessment.evidence.separator_sequence.dimension_constrained_count
            for lane in lanes
        ),
        hard_boundaries=hard_boundaries,
        missing_boundaries=missing_boundaries,
        hard_tonal_evidence=tuple(
            tonal_evidence
            for lane in lanes
            for tonal_evidence in lane.assessment.evidence.separator_sequence.hard_tonal_evidence
        ),
    )
    width_intervals = tuple(
        interval
        for lane in lanes
        for interval in lane.assessment.evidence.frame_dimensions.photo_width_intervals_px
    )
    separator_widths = tuple(
        value
        for lane in lanes
        for value in lane.assessment.evidence.frame_dimensions.separator_widths_px
    )
    nominal = lanes[0].assessment.evidence.frame_dimensions
    dimensions = FrameDimensionEvidence(
        frame_width_mm=nominal.frame_width_mm,
        frame_height_mm=nominal.frame_height_mm,
        frame_width_prior_px=nominal.frame_width_prior_px,
        photo_width_intervals_px=width_intervals,
        separator_widths_px=separator_widths,
        observed_width_mm=None,
        observed_height_mm=None,
        observed_aspect=None,
        aspect_error_ratio=None,
        calibration_used=False,
    )
    frame_observations: list[FrameContentObservation] = []
    frame_index = 1
    for lane in lanes:
        for observation in lane.assessment.evidence.frame_content.observations:
            frame_observations.append(replace(observation, index=frame_index))
            frame_index += 1
    frame_content = FrameContentEvidence(
        state=_combined_state(
            tuple(lane.assessment.evidence.frame_content.state for lane in lanes)
        ),
        reason="dual_lane_frame_content",
        threshold=None,
        median_mean=(
            sum(
                observation.mean for observation in frame_observations
            )
            / len(frame_observations)
            if frame_observations
            else None
        ),
        median_coverage=(
            sum(
                observation.coverage for observation in frame_observations
            )
            / len(frame_observations)
            if frame_observations
            else None
        ),
        observations=tuple(frame_observations),
        composite="dual_lane_components",
    )
    holder_texture_states = tuple(
        lane.assessment.evidence.holder_texture.state for lane in lanes
    )
    holder_mean_contrasts = tuple(
        value
        for lane in lanes
        if (
            value := lane.assessment.evidence.holder_texture.content_holder_mean_contrast
        )
        is not None
    )
    holder_coverage_contrasts = tuple(
        value
        for lane in lanes
        if (
            value := lane.assessment.evidence.holder_texture.content_holder_coverage_contrast
        )
        is not None
    )
    holder_texture = HolderTextureEvidence(
        state=_combined_state(holder_texture_states),
        reason="dual_lane_holder_texture",
        regions=tuple(
            region
            for lane in lanes
            for region in lane.assessment.evidence.holder_texture.regions
        ),
        content_holder_mean_contrast=(
            min(holder_mean_contrasts) if holder_mean_contrasts else None
        ),
        content_holder_coverage_contrast=(
            min(holder_coverage_contrasts)
            if holder_coverage_contrasts
            else None
        ),
    )
    preservation_state = _combined_state(
        tuple(
            lane.assessment.evidence.content_preservation.state for lane in lanes
        )
    )
    boundary_contact_frame_indexes: list[int] = []
    frame_offset = 0
    for lane in lanes:
        boundary_contact_frame_indexes.extend(
            frame_offset + index
            for index in lane.assessment.evidence.content_preservation.boundary_contact_frame_indexes
        )
        frame_offset += lane.geometry.count
    preservation = ContentPreservationEvidence(
        state=preservation_state,
        reason="dual_lane_content_preservation",
        uncovered_content=coverage.uncovered_content,
        boundary_contact_frame_indexes=tuple(boundary_contact_frame_indexes),
        partial_edge_state=EvidenceState.NOT_APPLICABLE,
    )
    alignment = SequenceContentAlignmentEvidence(
        state=_combined_state(
            tuple(lane.assessment.evidence.sequence_content_alignment.state for lane in lanes)
        ),
        reason="dual_lane_sequence_content_alignment",
        visible_sequence_span=geometry.visible_sequence_span.box,
        content_span=None,
        content_outside_sides=tuple(
            side
            for lane in lanes
            for side in lane.assessment.evidence.sequence_content_alignment.content_outside_sides
        ),
        overcontains_long_axis=any(
            lane.assessment.evidence.sequence_content_alignment.overcontains_long_axis
            for lane in lanes
        ),
        overcontains_short_axis=any(
            lane.assessment.evidence.sequence_content_alignment.overcontains_short_axis
            for lane in lanes
        ),
        leading_slack_px=0,
        trailing_slack_px=0,
        top_slack_px=0,
        bottom_slack_px=0,
    )
    completeness = StripCompletenessEvidence(
        frame_count_complete=True,
        frame_sequence_complete=topology.state == EvidenceState.SUPPORTED,
        count=geometry.count,
        nominal_count=geometry.count,
        valid_frame_count=len(geometry.frames),
        expected_internal_boundary_count=expected_separators,
        resolved_boundary_count=sum(
            len(lane.geometry.frame_boundaries) for lane in lanes
        ),
        independent_separator_count=sum(
            lane.assessment.evidence.separator_sequence.hard_count
            for lane in lanes
        ),
    )
    occupancy = HolderOccupancyEvidence(
        state=EvidenceState.SUPPORTED,
        strip_completeness=completeness,
        nominal_frame_total_mm=None,
        observed_sequence_span_px=float(geometry.visible_sequence_span.box.width),
        leading_slack_px=0.0,
        trailing_slack_px=0.0,
        leading_slack_mm=None,
        trailing_slack_mm=None,
        holder_fill_ratio=1.0,
        occupancy_status="filled",
        complete_underfilled_strip=False,
        content_support_available=frame_content.support_available,
        frame_coverage_state=coverage.state,
        photo_dimensions_stable=dimensions.state == EvidenceState.SUPPORTED,
        holder_span=geometry.holder_span,
        visible_sequence_span=geometry.visible_sequence_span,
        calibration_used=dimensions.calibration_used,
    )
    partial = PartialEdgeSafetyEvidence(
        EvidenceState.NOT_APPLICABLE,
        "not_partial",
        False,
        sequence.hard_count,
        sequence.expected_count,
        coverage.state,
        occupancy.state,
        False,
        (),
    )
    independence = EvidenceIndependenceEvidence(
        state=_combined_state(
            tuple(lane.assessment.evidence.independence.state for lane in lanes)
        ),
        reason="dual_lane_component_independence",
        sequence_root_measurement=geometry.sequence_provenance.root_measurement,
        supporting_root_measurements=tuple(
            f"lane_{lane_index}:{root}"
            for lane_index, lane in enumerate(lanes, start=1)
            for root in lane.assessment.evidence.independence.supporting_root_measurements
        ),
        cyclic_measurements=tuple(
            f"lane_{lane_index}:{root}"
            for lane_index, lane in enumerate(lanes, start=1)
            if lane.assessment.evidence.independence.state
            == EvidenceState.CONTRADICTED
            for root in (
                lane.assessment.evidence.independence.cyclic_measurements
                or (
                    lane.assessment.evidence.independence.sequence_root_measurement,
                )
            )
        ),
    )
    evidence = CandidateEvidence(
        frame_topology=topology,
        frame_coverage=coverage,
        frame_sequence=FrameSequenceEvidence(
            conservation=SequenceConservationEvidence(
                EvidenceState.NOT_APPLICABLE,
                "dual_lane_components_own_sequence_conservation",
                PixelInterval.exact(float(geometry.visible_sequence_span.box.width)),
                PixelInterval.zero(),
                PixelInterval.zero(),
                PixelInterval.zero(),
                PixelInterval.zero(),
            ),
        ),
        separator_sequence=sequence,
        frame_dimensions=dimensions,
        frame_content=frame_content,
        holder_texture=holder_texture,
        content_preservation=preservation,
        sequence_content_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial,
        independence=independence,
    )
    components_pass = bool(
        all(lane.assessment.gate.passed for lane in lanes)
        and all(lane_geometry_resolved)
        and geometry.lane_divider.state == EvidenceState.SUPPORTED
    )
    gate = candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=topology.state,
            content_preservation=preservation.state,
            photo_geometry=dimensions.state,
            sequence_conservation=EvidenceState.NOT_APPLICABLE,
            evidence_independence=independence.state,
            proof_paths=(
                BoundaryProofPath(
                    "mode_composition",
                    EvidenceState.SUPPORTED
                    if components_pass
                    else EvidenceState.CONTRADICTED,
                    (
                        "two_independently_assessed_lanes",
                        "resolved_lane_geometry",
                        "supported_lane_divider",
                    ),
                ),
            ),
            diagnostics=candidate.build_diagnostics,
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
