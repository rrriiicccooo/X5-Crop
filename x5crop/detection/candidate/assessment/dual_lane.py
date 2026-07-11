from __future__ import annotations

from dataclasses import replace

from ....geometry.gap_geometry import width_cv
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
from ...evidence.outer_alignment import OuterAlignmentEvidence
from ...evidence.partial_edge import PartialEdgeSafetyEvidence
from ...evidence.separator_continuity import SeparatorContinuityEvidence
from ...evidence.state import EvidenceState
from ...physical.photo_size import FrameDimensionEvidence
from ...physical.boundary import HolderOcclusionEvidence
from ...physical.intervals import PixelInterval
from ...physical.spacing import SequenceConservationEvidence
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    CandidateScores,
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
) -> AssessedCandidate:
    geometry = candidate.geometry
    topology_state = _combined_state(
        tuple(lane.assessment.evidence.frame_topology.state for lane in lanes)
    )
    topology = FrameTopologyEvidence(
        state=topology_state,
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
        holder_interval=(
            geometry.holder_span.box.left,
            geometry.holder_span.box.right,
        ),
        film_interval=(geometry.visible_sequence_span.box.left, geometry.visible_sequence_span.box.right),
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
    hard_indexes = tuple(
        range(
            1,
            1
            + sum(
                lane.assessment.evidence.separator_sequence.hard_count
                for lane in lanes
            ),
        )
    )
    sequence = SeparatorSequenceEvidence(
        state=_combined_state(
            tuple(
                lane.assessment.evidence.separator_sequence.state
                for lane in lanes
            )
        ),
        reason="dual_lane_separator_sequence",
        expected_count=expected_separators,
        hard_count=len(hard_indexes),
        model_count=sum(
            lane.assessment.evidence.separator_sequence.model_count for lane in lanes
        ),
        hard_indexes=hard_indexes,
        missing_indexes=(),
        hard_scores=tuple(
            score
            for lane in lanes
            for score in lane.assessment.evidence.separator_sequence.hard_scores
        ),
    )
    continuity = SeparatorContinuityEvidence(
        state=_combined_state(
            tuple(
                lane.assessment.evidence.separator_continuity.state
                for lane in lanes
            )
        ),
        reason="dual_lane_separator_continuity",
        records=tuple(
            record
            for lane in lanes
            for record in lane.assessment.evidence.separator_continuity.records
        ),
        observations=geometry.separators,
        minimum_coverage_ratio=min(
            lane.assessment.evidence.separator_continuity.minimum_coverage_ratio
            for lane in lanes
        ),
        minimum_continuity_ratio=min(
            lane.assessment.evidence.separator_continuity.minimum_continuity_ratio
            for lane in lanes
        ),
    )
    dimension_states = tuple(
        lane.assessment.evidence.frame_dimensions.state for lane in lanes
    )
    widths = tuple(
        value
        for lane in lanes
        for value in lane.assessment.evidence.frame_dimensions.photo_widths_px
    )
    separator_widths = tuple(
        value
        for lane in lanes
        for value in lane.assessment.evidence.frame_dimensions.separator_widths_px
    )
    nominal = lanes[0].assessment.evidence.frame_dimensions
    dimensions = FrameDimensionEvidence(
        state=_combined_state(dimension_states),
        reason="dual_lane_frame_dimensions",
        nominal_width_mm=nominal.nominal_width_mm,
        nominal_height_mm=nominal.nominal_height_mm,
        nominal_aspect=nominal.nominal_aspect,
        photo_widths_px=widths,
        photo_width_cv=width_cv(widths),
        separator_widths_px=separator_widths,
        separator_width_cv=width_cv(separator_widths),
        observed_width_mm=None,
        observed_height_mm=None,
        observed_aspect=None,
        aspect_error_ratio=max(
            (
                value
                for lane in lanes
                if (
                    value := lane.assessment.evidence.frame_dimensions.aspect_error_ratio
                )
                is not None
            ),
            default=None,
        ),
        maximum_dimension_error_ratio=max(
            (
                value
                for lane in lanes
                if (
                    value := lane.assessment.evidence.frame_dimensions.maximum_dimension_error_ratio
                )
                is not None
            ),
            default=None,
        ),
        calibration_used=all(
            lane.assessment.evidence.frame_dimensions.calibration_used
            for lane in lanes
        ),
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
    preservation = ContentPreservationEvidence(
        state=preservation_state,
        reason="dual_lane_content_preservation",
        uncovered_content=coverage.uncovered_content,
        boundary_contact_frame_indexes=tuple(
            index
            for lane in lanes
            for index in lane.assessment.evidence.content_preservation.boundary_contact_frame_indexes
        ),
        confirmed_outer_undercrop_sides=tuple(
            side
            for lane in lanes
            for side in lane.assessment.evidence.content_preservation.confirmed_outer_undercrop_sides
        ),
        partial_edge_state=EvidenceState.NOT_APPLICABLE,
    )
    alignment = OuterAlignmentEvidence(
        state=_combined_state(
            tuple(lane.assessment.evidence.outer_alignment.state for lane in lanes)
        ),
        reason="dual_lane_outer_alignment",
        visible_sequence_span=geometry.visible_sequence_span.box,
        content_span=None,
        content_measurement_sources=("lane_components",),
        confirmed_undercrop_sides=preservation.confirmed_outer_undercrop_sides,
        unconfirmed_undercrop_sides=(),
        overcontains_long_axis=any(
            lane.assessment.evidence.outer_alignment.overcontains_long_axis
            for lane in lanes
        ),
        overcontains_short_axis=any(
            lane.assessment.evidence.outer_alignment.overcontains_short_axis
            for lane in lanes
        ),
        leading_slack_px=0,
        trailing_slack_px=0,
        top_slack_px=0,
        bottom_slack_px=0,
        border_tonal_fraction=(),
    )
    completeness = StripCompletenessEvidence(
        frame_count_complete=True,
        frame_sequence_complete=topology.state == EvidenceState.SUPPORTED,
        count=geometry.count,
        nominal_count=geometry.count,
        valid_frame_count=len(geometry.frames),
        expected_separator_count=expected_separators,
        observed_separator_count=len(geometry.separators),
    )
    occupancy = HolderOccupancyEvidence(
        state=EvidenceState.SUPPORTED,
        strip_completeness=completeness,
        expected_film_span_mm=None,
        observed_film_span_px=float(geometry.visible_sequence_span.box.width),
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
        outer_root_measurement=geometry.sequence_provenance.root_measurement,
        separator_root_measurements=tuple(
            root
            for lane in lanes
            for root in lane.assessment.evidence.independence.separator_root_measurements
        ),
        cyclic_measurements=(),
    )
    evidence = CandidateEvidence(
        frame_topology=topology,
        frame_coverage=coverage,
        frame_sequence=FrameSequenceEvidence(
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
            spacings=(),
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
        separator_continuity=continuity,
        frame_dimensions=dimensions,
        frame_content=frame_content,
        holder_texture=holder_texture,
        content_preservation=preservation,
        outer_alignment=alignment,
        holder_occupancy=occupancy,
        partial_edge_safety=partial,
        independence=independence,
    )
    components_pass = all(lane.assessment.gate.passed for lane in lanes)
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
                    ("two_independently_assessed_lanes",),
                ),
            ),
            diagnostics=candidate.build_diagnostics,
        )
    )
    scores = CandidateScores(
        confidence=min(
            lane.assessment.scores.confidence for lane in lanes
        ),
        base=min(lane.assessment.scores.base for lane in lanes),
        geometry=min(lane.assessment.scores.geometry for lane in lanes),
        separator=min(lane.assessment.scores.separator for lane in lanes),
        content=min(lane.assessment.scores.content for lane in lanes),
        joint=min(lane.assessment.scores.joint for lane in lanes),
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=evidence,
            scores=scores,
            gate=gate,
            diagnostics=candidate.build_diagnostics,
        ),
    )
