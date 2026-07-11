from __future__ import annotations

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import Box, MeasurementProvenance
from ..candidate.model import BuiltCandidate
from ..candidate.plan.count_hypotheses import CountHypothesis
from ..context import DetectionContext
from ..geometry import CandidateGeometry
from ..physical.boundary import canvas_boundary_observations
from ..physical.spans import CropEnvelope, HolderSpan, VisibleSequenceSpan


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
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=HolderSpan(span),
            visible_sequence_span=VisibleSequenceSpan(span),
            crop_envelope=CropEnvelope(span),
            frames=(),
            separators=(),
            origin=0.0,
            pitch=float(width) / float(max(1, count)),
            offset_fraction=0.0,
            source=CANDIDATE_SOURCE_REVIEW_ONLY,
            automatic_processing_supported=False,
            contract="review_only_mode",
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
            offsets=(),
            placement_source="not_applicable",
            source="mode_contract",
            allowed_by_physical_spec=True,
        ),
        build_diagnostics=(
            "dual_lane_partial_not_supported",
            "automatic_processing_not_supported",
        ),
    )
