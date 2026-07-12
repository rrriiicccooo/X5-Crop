from __future__ import annotations

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import Box, MeasurementProvenance
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis
from ..context import DetectionContext
from ..physical.model import SequenceResiduals, SequenceSolution
from ..physical.boundary import HolderOcclusionEvidence
from ..physical.boundary import canvas_boundary_observations
from ..physical.photo_size import frame_dimension_prior
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan


def review_only_candidate(context: DetectionContext) -> BuiltCandidate:
    physical_spec = context.policy.physical_spec
    if (
        physical_spec.physical_layout != "dual_lane"
        or context.request.strip_mode != "partial"
    ):
        raise ValueError("review-only mode requires dual-lane partial input")
    height, width = context.measurement_cache.gray_work.shape
    span = Box(0, 0, width, height)
    count = physical_spec.default_count
    visible_span = VisibleSequenceSpan(span)
    dimensions = frame_dimension_prior(
        visible_span,
        physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    )
    return BuiltCandidate(
        geometry=SequenceSolution(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=HolderSpan(span),
            visible_sequence_span=visible_span,
            crop_envelope=CropEnvelope(span),
            photo_intervals=(),
            frames=(),
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=(),
            inter_frame_relations=(),
            holder_occlusion=HolderOcclusionEvidence.unavailable(),
            frame_dimension_prior=dimensions,
            residuals=SequenceResiduals(None, None, 0.0),
            search_budget_exhausted=False,
            source=CANDIDATE_SOURCE_REVIEW_ONLY,
            automatic_processing_supported=False,
            sequence_hypothesis_name="review_only_canvas",
            sequence_hypothesis_strategy="review_only_canvas",
            sequence_provenance=MeasurementProvenance(
                root_measurement="review_only_mode",
                source="review_only_canvas",
                dependencies=("canvas",),
            ),
            boundary_observations=canvas_boundary_observations(width, height),
        ),
        count_hypothesis=CountHypothesis(
            count=count,
            strip_mode=context.request.strip_mode,
            source="mode_contract",
            allowed_by_physical_spec=True,
        ),
        build_diagnostics=(
            "dual_lane_partial_not_supported",
            "automatic_processing_not_supported",
        ),
    )
