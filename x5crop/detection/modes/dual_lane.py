from __future__ import annotations

from dataclasses import replace
from typing import Callable

from ...cache.analysis import make_measurement_cache
from ...domain import (
    Box,
    CropEnvelope,
    EvidenceState,
    HolderSpan,
    VisibleSequenceSpan,
)
from ...geometry.boxes import translate_box
from ...geometry.layout import HORIZONTAL, is_horizontal_layout
from ...image.statistics import image_measurement_statistics
from ...units import ScanCalibrationResolution, transposed_scan_calibration
from ..candidate.composition.dual_lane import compose_dual_lane_candidate
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis, CountHypothesisSource
from ..candidate.assessment.review_only import assess_review_only_candidate
from ..candidate.selection.choose import select_candidates
from ..candidate.selection.model import SelectionResult
from ..context import DetectionContext
from .review_only import unresolved_dual_lane_candidate
from ..physical.model import (
    combined_assignment_consensus,
    combined_sequence_residuals,
    DualLaneSolution,
    SequenceSolution,
)
from ..physical.lane_divider import (
    DUAL_LANE_COUNT,
    LaneDividerEvidence,
    measure_lane_dividers,
)


StandardDetector = Callable[[DetectionContext], SelectionResult]


def _lane_calibration(context: DetectionContext) -> ScanCalibrationResolution:
    calibration = context.scan_calibration
    if is_horizontal_layout(context.request.layout):
        return calibration
    return transposed_scan_calibration(calibration)


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
        layout=HORIZONTAL,
        strip_mode="full",
        requested_count=lane_configuration.physical_spec.default_count,
    )
    cache = make_measurement_cache(
        lane_gray,
        HORIZONTAL,
        lane_configuration.preprocess.content_evidence_image,
        image_measurement_statistics(
            lane_gray,
            lane_configuration.preprocess.image_statistics,
        ),
        context.measurement_cache.lookup_statistics,
    )
    return DetectionContext(
        scan_calibration=_lane_calibration(context),
        request=lane_request,
        configuration=lane_configuration,
        lane_configuration=None,
        measurement_cache=cache,
        execution_statistics=context.execution_statistics,
    )


def _parent_candidate(
    context: DetectionContext,
    divider: LaneDividerEvidence,
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
        for lane, candidate in zip(lane_boxes, lane_candidates, strict=True)
        for frame in candidate.geometry.frames
    )
    film_boxes = tuple(
        translate_box(
            candidate.geometry.visible_sequence_span.box,
            lane.left,
            lane.top,
        )
        for lane, candidate in zip(lane_boxes, lane_candidates, strict=True)
    )
    visible_sequence_span = Box(
        min(box.left for box in film_boxes),
        min(box.top for box in film_boxes),
        max(box.right for box in film_boxes),
        max(box.bottom for box in film_boxes),
    )
    crop_boxes = tuple(
        translate_box(candidate.geometry.crop_envelope.box, lane.left, lane.top)
        for lane, candidate in zip(lane_boxes, lane_candidates, strict=True)
    )
    crop_envelope = Box(
        min(box.left for box in crop_boxes),
        min(box.top for box in crop_boxes),
        max(box.right for box in crop_boxes),
        max(box.bottom for box in crop_boxes),
    )
    count = sum(candidate.geometry.count for candidate in lane_candidates)
    if count not in physical_spec.allowed_counts:
        raise ValueError("dual-lane total count must be physically allowed")
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
            frames=frames,
            residuals=combined_sequence_residuals(lane_solutions),
            assignment_consensus=combined_assignment_consensus(lane_solutions),
            search_budget_exhausted=bool(
                proposal_budget_exhausted
                or any(solution.search_budget_exhausted for solution in lane_solutions)
            ),
            lane_divider=divider,
            lane_solutions=lane_solutions,
            lane_boxes=lane_boxes,
            lane_crop_envelopes=tuple(
                CropEnvelope(box) for box in crop_boxes
            ),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode="full",
            source=CountHypothesisSource.FORMAT_DEFAULT,
        ),
        build_diagnostics=(
            ("lane_divider_evidence_unavailable",)
            if divider.state != EvidenceState.SUPPORTED
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
    divider_evidence = measure_lane_dividers(
        context.measurement_cache.content_evidence_float_work,
        context.configuration.candidate_plan.dual_lane_divider,
    )
    parent_candidates = []
    for divider in divider_evidence.candidates:
        lanes = divider.lane_boxes(
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
            divider,
            lanes,
            lane_selections,
            divider_evidence.budget_exhausted,
        )
        parent_candidates.append(
            compose_dual_lane_candidate(
                built,
                lane_selections,
            )
        )
        context.execution_statistics.record_assessed_candidate()
    if not parent_candidates:
        parent_candidates.append(
            assess_review_only_candidate(
                unresolved_dual_lane_candidate(
                    context,
                    "lane_divider_unavailable",
                )
            )
        )
        context.execution_statistics.record_assessed_candidate()
    return select_candidates(
        tuple(parent_candidates),
        larger_counts_evaluated=True,
    )
