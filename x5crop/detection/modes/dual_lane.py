from __future__ import annotations

from dataclasses import replace
from typing import Callable

from ...cache.analysis import make_measurement_cache
from ...constants import CANDIDATE_SOURCE_DUAL_LANE
from ...domain import Box, MeasurementProvenance
from ...geometry.boxes import translate_box
from ...units import ScanCalibration
from ..candidate.assessment.dual_lane import assess_dual_lane_candidate
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis
from ..candidate.proposal.hard_safety import hard_safety_candidate
from ..candidate.assessment.candidate import assess_candidate
from ..candidate.selection.choose import select_candidates
from ..candidate.selection.model import SelectionResult
from ..context import DetectionContext
from ..physical.model import SequenceResiduals, SequenceSolution
from ..physical.boundary import HolderOcclusionEvidence
from ..physical.boundary import canvas_boundary_observations
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from .dual_lane_split import LaneDividerProposal, lane_divider_proposals


StandardDetector = Callable[[DetectionContext], SelectionResult]


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
    lane_policy = context.lane_policy
    if lane_policy is None:
        raise ValueError("dual-lane context requires a resolved lane policy")
    lane_gray = context.measurement_cache.gray_work[lane.top : lane.bottom, lane.left : lane.right]
    lane_request = replace(
        context.request,
        layout="horizontal",
        strip_mode="full",
        requested_count=lane_policy.physical_spec.default_count,
    )
    cache = make_measurement_cache(
        lane_gray,
        "horizontal",
        lane_policy.preprocess.content_evidence_image,
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
        policy=lane_policy,
        lane_policy=None,
        measurement_cache=cache,
    )


def _parent_candidate(
    context: DetectionContext,
    divider: LaneDividerProposal,
    lane_boxes: tuple[Box, Box],
    lanes: tuple[SelectionResult, SelectionResult],
) -> BuiltCandidate:
    physical_spec = context.policy.physical_spec
    lane_candidates = tuple(selection.selected for selection in lanes)
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
    observations = []
    for lane, candidate in zip(lane_boxes, lane_candidates):
        for observation in candidate.geometry.separator_observations:
            observations.append(
                replace(
                    observation,
                    start=float(observation.start) + float(lane.left),
                    end=float(observation.end) + float(lane.left),
                    center=float(observation.center) + float(lane.left),
                    lane_box=lane,
                )
            )
    count = sum(candidate.geometry.count for candidate in lane_candidates)
    work_height, work_width = context.measurement_cache.gray_work.shape
    return BuiltCandidate(
        geometry=SequenceSolution(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode="full",
            count=count,
            holder_span=HolderSpan(
                Box(0, 0, work_width, work_height)
            ),
            visible_sequence_span=VisibleSequenceSpan(visible_sequence_span),
            crop_envelope=CropEnvelope(crop_envelope),
            photo_intervals=(),
            frames=frames,
            separator_observations=tuple(observations),
            separator_assignments=(),
            frame_boundaries=(),
            inter_frame_relations=(),
            holder_occlusion=HolderOcclusionEvidence.not_applicable(),
            frame_dimension_prior=lane_candidates[0].geometry.frame_dimension_prior,
            residuals=SequenceResiduals(None, None, 0.0),
            search_exhausted=False,
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
            lane_boxes=lane_boxes,
            lane_crop_envelopes=tuple(
                CropEnvelope(box) for box in crop_boxes
            ),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode="full",
            source=divider.source,
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
    physical_spec = context.policy.physical_spec
    if context.request.strip_mode != "full":
        raise ValueError("dual-lane detector is only valid for full mode")
    if physical_spec.lane_count != 2:
        raise ValueError("dual-lane detector supports exactly two lanes")
    proposals = lane_divider_proposals(
        context.measurement_cache.content_evidence_float_work,
        context.policy.candidate_plan.dual_lane_divider,
    )
    parent_candidates = []
    for proposal in proposals:
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
        )
        parent_candidates.append(
            assess_dual_lane_candidate(
                built,
                tuple(selection.selected for selection in lane_selections),
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
