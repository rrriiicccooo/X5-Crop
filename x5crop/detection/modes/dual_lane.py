from __future__ import annotations

from dataclasses import dataclass, replace
from math import prod
from typing import Callable

from ...cache.analysis import make_measurement_cache
from ...constants import CANDIDATE_SOURCE_DUAL_LANE
from ...domain import (
    Box,
    CropEnvelope,
    EvidenceState,
    FrameBoundary,
    HolderSpan,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)
from ...geometry.boxes import translate_box
from ...image.statistics import image_measurement_statistics
from ...units import ScanCalibration
from ..candidate.assessment.dual_lane import assess_dual_lane_candidate
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis
from ..candidate.proposal.hard_safety import hard_safety_candidate
from ..candidate.assessment.candidate import assess_candidate
from ..candidate.selection.choose import select_candidates
from ..candidate.selection.model import SelectionResult
from ..context import DetectionContext
from ..physical.model import (
    BoundaryAssignmentConsensus,
    DualLaneSolution,
    PhotoInterval,
    SequenceResiduals,
    SequenceSolution,
)
from ..physical.boundary import (
    HolderOcclusionEvidence,
    canvas_boundary_observations,
)
from ..physical.spacing import InterFrameSpacing
from .dual_lane_split import (
    DUAL_LANE_COUNT,
    LaneDividerProposal,
    lane_divider_proposals,
)


StandardDetector = Callable[[DetectionContext], SelectionResult]


@dataclass(frozen=True)
class _TranslatedLaneGeometry:
    photo_intervals: tuple[PhotoInterval, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorAssignment, ...]
    frame_boundaries: tuple[FrameBoundary, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]


def _offset_interval(interval: PixelInterval, offset: int) -> PixelInterval:
    return interval.plus(PixelInterval.exact(float(offset)))


def _translate_separator_observation(
    observation: SeparatorBandObservation,
    lane: Box,
) -> SeparatorBandObservation:
    return replace(
        observation,
        start=float(observation.start) + float(lane.left),
        end=float(observation.end) + float(lane.left),
        center=float(observation.center) + float(lane.left),
        lane_box=lane,
    )


def _translate_lane_geometry(
    solution: SequenceSolution,
    lane: Box,
    lane_index: int,
) -> _TranslatedLaneGeometry:
    translated_observations = tuple(
        _translate_separator_observation(observation, lane)
        for observation in solution.separator_observations
    )
    observation_by_id = {
        id(original): translated
        for original, translated in zip(
            solution.separator_observations,
            translated_observations,
            strict=True,
        )
    }

    def translated_observation(
        observation: SeparatorBandObservation,
    ) -> SeparatorBandObservation:
        return observation_by_id.get(
            id(observation),
            _translate_separator_observation(observation, lane),
        )

    translated_assignments = tuple(
        replace(
            assignment,
            observation=translated_observation(assignment.observation),
            position_constraint=replace(
                assignment.position_constraint,
                position=_offset_interval(
                    assignment.position_constraint.position,
                    lane.left,
                ),
            ),
        )
        for assignment in solution.separator_assignments
    )
    assignment_by_id = {
        id(original): translated
        for original, translated in zip(
            solution.separator_assignments,
            translated_assignments,
            strict=True,
        )
    }
    translated_boundaries = tuple(
        replace(
            boundary,
            position=_offset_interval(boundary.position, lane.left),
            assignment=(
                None
                if boundary.assignment is None
                else assignment_by_id[id(boundary.assignment)]
            ),
            dimension_constraint=(
                None
                if boundary.dimension_constraint is None
                else replace(
                    boundary.dimension_constraint,
                    position=_offset_interval(
                        boundary.dimension_constraint.position,
                        lane.left,
                    ),
                    focused_observation=(
                        None
                        if boundary.dimension_constraint.focused_observation is None
                        else translated_observation(
                            boundary.dimension_constraint.focused_observation
                        )
                    ),
                )
            ),
        )
        for boundary in solution.frame_boundaries
    )
    translated_intervals = tuple(
        replace(
            interval,
            start=_offset_interval(interval.start, lane.left),
            end=_offset_interval(interval.end, lane.left),
        )
        for interval in solution.photo_intervals
    )
    lane_spacings = tuple(
        replace(spacing, lane_index=lane_index)
        for spacing in solution.inter_frame_spacings
    )
    return _TranslatedLaneGeometry(
        photo_intervals=translated_intervals,
        separator_observations=translated_observations,
        separator_assignments=translated_assignments,
        frame_boundaries=translated_boundaries,
        inter_frame_spacings=lane_spacings,
    )


def _lane_calibration(context: DetectionContext) -> ScanCalibration:
    calibration = context.scan_calibration
    if context.request.layout == "horizontal":
        return calibration
    return ScanCalibration(
        x_px_per_mm=calibration.y_px_per_mm,
        y_px_per_mm=calibration.x_px_per_mm,
        source=calibration.source,
        trusted=calibration.trusted,
        warnings=calibration.warnings,
    )


def _lane_context(
    context: DetectionContext,
    lane: Box,
) -> DetectionContext:
    lane_configuration = context.lane_configuration
    if lane_configuration is None:
        raise ValueError("dual-lane context requires a resolved lane configuration")
    lane_gray = context.measurement_cache.gray_work[lane.top : lane.bottom, lane.left : lane.right]
    lane_request = replace(
        context.request,
        layout="horizontal",
        strip_mode="full",
        requested_count=lane_configuration.physical_spec.default_count,
    )
    cache = make_measurement_cache(
        lane_gray,
        "horizontal",
        lane_configuration.preprocess.content_evidence_image,
        image_measurement_statistics(
            lane_gray,
            lane_configuration.preprocess.image_statistics,
        ),
    )
    profile = replace(
        context.image_profile,
        shape=tuple(lane_gray.shape),
        axes="YX",
    )
    return DetectionContext(
        image_profile=profile,
        scan_calibration=_lane_calibration(context),
        request=lane_request,
        configuration=lane_configuration,
        lane_configuration=None,
        measurement_cache=cache,
    )


def _parent_candidate(
    context: DetectionContext,
    divider: LaneDividerProposal,
    lane_boxes: tuple[Box, Box],
    lanes: tuple[SelectionResult, SelectionResult],
    proposal_budget_exhausted: bool,
) -> BuiltCandidate:
    physical_spec = context.configuration.physical_spec
    lane_candidates = tuple(selection.selected for selection in lanes)
    lane_solutions = tuple(candidate.geometry for candidate in lane_candidates)
    if not all(isinstance(solution, SequenceSolution) for solution in lane_solutions):
        raise ValueError("dual-lane components require solved lane sequences")
    frames = tuple(
        translate_box(frame, lane.left, lane.top)
        for lane, candidate in zip(lane_boxes, lane_candidates)
        for frame in candidate.geometry.frames
    )
    film_boxes = tuple(
        translate_box(
            candidate.geometry.visible_sequence_span.box,
            lane.left,
            lane.top,
        )
        for lane, candidate in zip(lane_boxes, lane_candidates)
    )
    visible_sequence_span = Box(
        min(box.left for box in film_boxes),
        min(box.top for box in film_boxes),
        max(box.right for box in film_boxes),
        max(box.bottom for box in film_boxes),
    )
    crop_boxes = tuple(
        translate_box(candidate.geometry.crop_envelope.box, lane.left, lane.top)
        for lane, candidate in zip(lane_boxes, lane_candidates)
    )
    crop_envelope = Box(
        min(box.left for box in crop_boxes),
        min(box.top for box in crop_boxes),
        max(box.right for box in crop_boxes),
        max(box.bottom for box in crop_boxes),
    )
    translated = tuple(
        _translate_lane_geometry(solution, lane, lane_index)
        for lane_index, (solution, lane) in enumerate(
            zip(lane_solutions, lane_boxes, strict=True),
            start=1,
        )
    )
    photo_intervals = tuple(
        item for group in translated for item in group.photo_intervals
    )
    observations = tuple(
        item for group in translated for item in group.separator_observations
    )
    assignments = tuple(
        item for group in translated for item in group.separator_assignments
    )
    boundaries = tuple(
        item for group in translated for item in group.frame_boundaries
    )
    spacings = tuple(
        item for group in translated for item in group.inter_frame_spacings
    )
    count = sum(candidate.geometry.count for candidate in lane_candidates)
    lane_assignment_consensus = tuple(
        solution.assignment_consensus for solution in lane_solutions
    )
    assignments_resolved = all(
        consensus.state == EvidenceState.SUPPORTED
        for consensus in lane_assignment_consensus
    )
    work_height, work_width = context.measurement_cache.gray_work.shape
    return BuiltCandidate(
        geometry=DualLaneSolution(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode="full",
            count=count,
            holder_span=HolderSpan(
                Box(0, 0, work_width, work_height)
            ),
            visible_sequence_span=VisibleSequenceSpan(visible_sequence_span),
            crop_envelope=CropEnvelope(crop_envelope),
            photo_intervals=photo_intervals,
            frames=frames,
            separator_observations=observations,
            separator_assignments=assignments,
            frame_boundaries=boundaries,
            inter_frame_spacings=spacings,
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
            frame_dimension_prior=lane_candidates[0].geometry.frame_dimension_prior,
            residuals=SequenceResiduals(None, None, 0.0),
            assignment_consensus=BoundaryAssignmentConsensus(
                (
                    EvidenceState.SUPPORTED
                    if assignments_resolved
                    else EvidenceState.UNAVAILABLE
                ),
                (
                    "dual_lane_separator_assignments_agree"
                    if assignments_resolved
                    else "dual_lane_separator_assignments_unresolved"
                ),
                prod(
                    consensus.solution_count
                    for consensus in lane_assignment_consensus
                ),
                (),
            ),
            search_budget_exhausted=bool(
                proposal_budget_exhausted
                or any(solution.search_budget_exhausted for solution in lane_solutions)
            ),
            source=CANDIDATE_SOURCE_DUAL_LANE,
            automatic_processing_supported=divider.source != "center_safety",
            sequence_hypothesis_name="measured_lane_divider",
            sequence_hypothesis_strategy="dual_lane_sequence",
            sequence_provenance=MeasurementProvenance(
                root_measurement="holder_gutter_profile",
                source=divider.source,
                dependencies=("content_evidence", "holder_texture"),
            ),
            boundary_observations=canvas_boundary_observations(
                work_width,
                work_height,
            ),
            lane_solutions=lane_solutions,
            lane_boxes=lane_boxes,
            lane_crop_envelopes=tuple(
                CropEnvelope(box) for box in crop_boxes
            ),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode="full",
            source="format_default",
            allowed_by_physical_spec=count
            in physical_spec.allowed_counts,
        ),
        build_diagnostics=(
            ("center_safety_lane_divider",)
            if divider.source == "center_safety"
            else ()
        ),
    )


def choose_dual_lane_detection(
    context: DetectionContext,
    standard_detector: StandardDetector,
) -> SelectionResult:
    physical_spec = context.configuration.physical_spec
    if context.request.strip_mode != "full":
        raise ValueError("dual-lane detector is only valid for full mode")
    if physical_spec.lane_count != DUAL_LANE_COUNT:
        raise ValueError("dual-lane detector supports exactly two lanes")
    proposal_set = lane_divider_proposals(
        context.measurement_cache.content_evidence_float_work,
        context.configuration.candidate_plan.dual_lane_divider,
    )
    parent_candidates = []
    for proposal in proposal_set.proposals:
        lanes = proposal.lane_boxes(
            context.measurement_cache.gray_work.shape[1],
            context.measurement_cache.gray_work.shape[0],
        )
        if any(not lane.valid() for lane in lanes):
            continue
        lane_selections = tuple(
            standard_detector(_lane_context(context, lane)) for lane in lanes
        )
        built = _parent_candidate(
            context,
            proposal,
            lanes,
            lane_selections,
            proposal_set.budget_exhausted,
        )
        parent_candidates.append(
            assess_dual_lane_candidate(
                built,
                tuple(selection.selected for selection in lane_selections),
                lane_geometry_resolved=tuple(
                    selection.geometry_resolution.supported
                    for selection in lane_selections
                ),
            )
        )
    if not parent_candidates:
        parent_candidates.append(
            assess_candidate(
                hard_safety_candidate(
                    context,
                    physical_spec.default_count,
                ),
                context,
            )
        )
    return select_candidates(
        tuple(parent_candidates),
        larger_counts_evaluated=True,
    )
