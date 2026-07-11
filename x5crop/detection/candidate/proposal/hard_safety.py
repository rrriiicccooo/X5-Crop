from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, MeasurementProvenance
from ...context import DetectionContext
from ...physical.boundary import canvas_boundary_observations
from ...physical.boundary import HolderOcclusionEvidence
from ...physical.photo_size import frame_dimension_estimate
from ...physical.separator.assignment import (
    build_frame_boundaries,
    frames_from_boundaries,
)
from x5crop.domain import CropEnvelope, HolderSpan, VisibleSequenceSpan
from ..model import BuiltCandidate
from ..plan.count_hypotheses import CountHypothesis
from ...geometry import CandidateGeometry


def hard_safety_candidate(
    context: DetectionContext,
    count: int,
) -> BuiltCandidate:
    physical_spec = context.policy.physical_spec
    work_height, work_width = context.measurement_cache.gray_work.shape
    count = max(1, int(count))
    span = Box(0, 0, work_width, work_height)
    visible_span = VisibleSequenceSpan(span)
    dimensions = frame_dimension_estimate(
        visible_span,
        physical_spec,
        context.scan_calibration,
        context.policy.separator.frame_dimension_estimate,
        layout=context.request.layout,
    )
    boundary_result = build_frame_boundaries(
        (),
        (),
        visible_span,
        count,
        dimensions,
        HolderOcclusionEvidence.unavailable(),
    )
    frames = frames_from_boundaries(
        visible_span,
        boundary_result.boundaries,
        count,
    )
    hypothesis = CountHypothesis(
        count=count,
        strip_mode=context.request.strip_mode,
        source="hard_safety",
        allowed_by_physical_spec=count in physical_spec.allowed_counts,
    )
    return BuiltCandidate(
        geometry=CandidateGeometry(
            format_id=physical_spec.format_id,
            layout=context.request.layout,
            strip_mode=context.request.strip_mode,
            count=count,
            holder_span=HolderSpan(span),
            visible_sequence_span=visible_span,
            crop_envelope=CropEnvelope(span),
            frames=frames,
            separator_observations=(),
            separator_assignments=(),
            frame_boundaries=boundary_result.boundaries,
            frame_dimension_estimate=dimensions,
            source=CANDIDATE_SOURCE_HARD_SAFETY,
            automatic_processing_supported=False,
            sequence_hypothesis_name="full_canvas_safety",
            sequence_hypothesis_strategy="safety_canvas",
            sequence_provenance=MeasurementProvenance(
                root_measurement="safety_geometry_model",
                source="full_canvas_safety",
                dependencies=("canvas", "count"),
            ),
            boundary_observations=canvas_boundary_observations(
                work_width,
                work_height,
            ),
        ),
        count_hypothesis=hypothesis,
        build_diagnostics=(
            "no_physical_candidate",
            "automatic_processing_not_supported",
        ),
    )
